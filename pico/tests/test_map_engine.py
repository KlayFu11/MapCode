import subprocess
import shutil
from pathlib import Path

import pytest

from pico.features.map_engine.config import BROAD_MAP_BUDGET_TOKENS
from pico.features.map_engine.config import FOCUSED_MAP_BUDGET_TOKENS
from pico.features.map_engine.engine import MapEngine
from pico.features.map_engine.engine import MapEngineIndexNotReady

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "map_engine"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )


def _write(repo: Path, relative_path: str, content: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_fixture_repo(tmp_path: Path, fixture_name: str) -> Path:
    repo = tmp_path / fixture_name
    shutil.copytree(FIXTURE_ROOT / fixture_name, repo)
    _git(repo, "init")
    _git(repo, "config", "user.email", "mapcode@example.test")
    _git(repo, "config", "user.name", "MapCode Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", f"{fixture_name} fixture")
    return repo


@pytest.fixture
def map_engine_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "mapcode@example.test")
    _git(tmp_path, "config", "user.name", "MapCode Test")
    _write(
        tmp_path,
        "app.py",
        "from pkg.service import Service\n\n"
        "def run():\n"
        "    return Service().handle()\n",
    )
    _write(
        tmp_path,
        "pkg/service.py",
        "class Service:\n"
        "    def handle(self):\n"
        "        return helper()\n\n"
        "def helper():\n"
        "    return 'ok'\n",
    )
    _write(
        tmp_path,
        "pkg/standalone.py",
        "def standalone():\n"
        "    return 'standalone'\n",
    )
    _write(tmp_path, "README.md", "# ignored by MapEngine\n")
    _git(tmp_path, "add", "app.py", "pkg/service.py", "pkg/standalone.py", "README.md")
    _git(tmp_path, "commit", "-m", "initial fixture")
    return tmp_path


def test_offline_fixture_demonstrates_map_engine_public_facade(tmp_path: Path):
    repo = _copy_fixture_repo(tmp_path, "offline_demo")
    engine = MapEngine(repo)

    first_status = engine.ensure_index()
    broad_analysis = engine.analyze("Explain the authorization flow.")
    broad = engine.generate_broad(broad_analysis)
    catalog = engine.build_selector_catalog()
    focused_analysis = engine.analyze(
        "Review app.py and PKG load_user_profile _private_token JWTAuth."
    )
    focused = engine.generate_focused(
        focused_analysis,
        focus_fnames=focused_analysis.mentioned_files,
    )
    symbol_analysis = engine.analyze("Explain JWTAuth.")
    symbol_focused = engine.generate_focused(
        symbol_analysis,
        focus_fnames=symbol_analysis.mentioned_files,
    )
    path_analysis = engine.analyze("Explain PKG package.")
    path_focused = engine.generate_focused(
        path_analysis,
        focus_fnames=path_analysis.mentioned_files,
    )
    cached_status = MapEngine(repo).ensure_index()

    assert first_status.file_count == 5
    assert first_status.cache_status.read_status == "miss"
    assert first_status.cache_status.write_status == "written"
    assert broad_analysis.branch == "fuzzy"
    assert broad.mode == "broad"
    assert broad.evidence.rendering.target_tokens == BROAD_MAP_BUDGET_TOKENS
    assert broad.evidence.ranking.focus_fnames == ()
    assert broad.evidence.ranking.personalization_files == ()
    assert catalog.index_snapshot_id == first_status.index_snapshot_id
    assert catalog.candidate_paths == (
        "app.py",
        "pkg/auth.py",
        "pkg/private_tools.py",
        "pkg/service.py",
        "pkg/standalone.py",
    )
    assert cached_status.index_snapshot_id == first_status.index_snapshot_id
    assert cached_status.cache_status.read_status == "hit"
    assert cached_status.cache_status.write_status == "not_needed"

    assert focused_analysis.branch == "specific"
    assert focused_analysis.mentioned_files == ("app.py",)
    assert focused_analysis.effective_symbol_hits == (
        "load_user_profile",
        "_private_token",
        "JWTAuth",
    )
    assert focused_analysis.path_ident_hits == ("app", "PKG")
    assert focused_analysis.path_ident_hit_files["app"] == ("app.py",)
    assert focused_analysis.path_ident_hit_files["PKG"] == (
        "pkg/auth.py",
        "pkg/private_tools.py",
        "pkg/service.py",
        "pkg/standalone.py",
    )
    assert focused.mode == "focused"
    assert focused.focus_fnames == ("app.py",)
    assert focused.evidence.rendering.target_tokens == FOCUSED_MAP_BUDGET_TOKENS
    assert focused.evidence.ranking.focus_personalization_files == ("app.py",)
    assert focused.evidence.ranking.path_personalization_files == (
        "app.py",
        "pkg/auth.py",
        "pkg/private_tools.py",
        "pkg/service.py",
    )
    assert "pkg/standalone.py" not in focused.evidence.ranking.path_personalization_files
    assert focused.evidence.ranking.personalization_files == (
        "app.py",
        "pkg/auth.py",
        "pkg/private_tools.py",
        "pkg/service.py",
    )
    assert _contributor_codes(focused, "pkg/service.py", "app.py", "load_user_profile") == (
        "prompt_ident_boost",
        "structured_ident_boost",
        "focus_outbound_boost",
    )
    assert _contributor_codes(
        focused,
        "pkg/private_tools.py",
        "pkg/auth.py",
        "_private_token",
    ) == (
        "prompt_ident_boost",
        "structured_ident_boost",
        "private_ident_penalty",
    )

    assert symbol_analysis.mentioned_idents == ("Explain", "JWTAuth")
    assert symbol_analysis.effective_symbol_hits == ("JWTAuth",)
    assert symbol_focused.mode == "focused"
    assert symbol_focused.focus_fnames == ()
    assert symbol_focused.evidence.ranking.personalization_files == ()
    assert symbol_focused.evidence.ranking.algorithm == "pagerank"
    auth_evidence = _rendered_file(symbol_focused, "pkg/auth.py")
    assert auth_evidence.prompt_symbol_hits == ("JWTAuth",)
    assert "class JWTAuth" in symbol_focused.repo_map_text

    assert path_analysis.mentioned_files == ()
    assert path_analysis.effective_symbol_hits == ()
    assert path_analysis.path_ident_hits == ("PKG",)
    assert path_focused.mode == "focused"
    assert path_focused.focus_fnames == ()
    assert path_focused.evidence.ranking.algorithm == "personalized_pagerank"
    assert path_focused.evidence.ranking.focus_personalization_files == ()
    assert path_focused.evidence.ranking.path_personalization_files == (
        "pkg/auth.py",
        "pkg/private_tools.py",
        "pkg/service.py",
    )
    assert path_focused.evidence.ranking.personalization_files == (
        "pkg/auth.py",
        "pkg/private_tools.py",
        "pkg/service.py",
    )
    assert _rendered_file(path_focused, "pkg/auth.py").prompt_path_ident_hits == (
        "PKG",
    )


def test_offline_fixture_demonstrates_stable_fallback(tmp_path: Path):
    repo = _copy_fixture_repo(tmp_path, "stable_fallback")
    engine = MapEngine(repo)
    engine.ensure_index()

    analysis = engine.analyze("Explain unknown behavior.")
    result = engine.generate_broad(analysis)

    assert analysis.branch == "fuzzy"
    assert result.mode == "broad"
    assert result.evidence.ranking.algorithm == "stable_path_fallback"
    assert result.evidence.ranking.top_ranked_files == ("alpha.py", "zeta.py")
    assert result.rendered_files == ("alpha.py", "zeta.py")
    assert result.repo_map_text.index("alpha.py:") < result.repo_map_text.index(
        "zeta.py:"
    )


def test_public_methods_require_ready_index(map_engine_repo: Path):
    engine = MapEngine(map_engine_repo)

    with pytest.raises(MapEngineIndexNotReady):
        engine.analyze("Explain Service")
    with pytest.raises(MapEngineIndexNotReady):
        engine.generate_broad(_fuzzy_analysis())
    with pytest.raises(MapEngineIndexNotReady):
        engine.generate_focused(_fuzzy_analysis(), focus_fnames=())
    with pytest.raises(MapEngineIndexNotReady):
        engine.build_selector_catalog()


def _rendered_file(result, path: str):
    matches = [
        evidence
        for evidence in result.evidence.rendered_files
        if evidence.path == path
    ]
    assert len(matches) == 1
    return matches[0]


def _contributor_codes(
    result,
    target_path: str,
    source_path: str,
    identifier: str,
) -> tuple[str, ...]:
    target = _rendered_file(result, target_path)
    matches = [
        contributor
        for contributor in target.top_rank_contributors
        if contributor.source_path == source_path
        and contributor.identifier == identifier
    ]
    assert len(matches) == 1
    return matches[0].weight_reason_codes


def test_ensure_index_builds_once_and_returns_snapshot_status(
    map_engine_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import pico.features.map_engine.engine as engine_module

    build_calls = []
    original_build_symbol_index = engine_module.build_symbol_index

    def counting_build_symbol_index(repo_root, source_paths):
        build_calls.append((Path(repo_root), tuple(source_paths)))
        return original_build_symbol_index(repo_root, source_paths)

    monkeypatch.setattr(
        engine_module,
        "build_symbol_index",
        counting_build_symbol_index,
    )
    engine = MapEngine(map_engine_repo)

    first_status = engine.ensure_index()
    second_status = engine.ensure_index()
    analysis = engine.analyze("Explain Service in pkg/")
    focused = engine.generate_focused(analysis, focus_fnames=analysis.mentioned_files)
    broad = engine.generate_broad(_fuzzy_analysis())
    catalog = engine.build_selector_catalog()

    assert first_status is second_status
    assert len(build_calls) == 1
    assert build_calls[0][0] == map_engine_repo
    assert build_calls[0][1] == ("app.py", "pkg/service.py", "pkg/standalone.py")
    assert first_status.index_snapshot_id == focused.evidence.index_snapshot_id
    assert first_status.index_snapshot_id == broad.evidence.index_snapshot_id
    assert first_status.index_snapshot_id == catalog.index_snapshot_id
    assert first_status.file_count == 3
    assert first_status.definition_count >= 4
    assert first_status.reference_count >= 3


def test_path_ident_only_specific_generates_focused_map_without_focus_files(
    map_engine_repo: Path,
):
    engine = MapEngine(map_engine_repo)
    status = engine.ensure_index()

    analysis = engine.analyze("Explain pkg package")
    result = engine.generate_focused(analysis, focus_fnames=analysis.mentioned_files)

    assert analysis.branch == "specific"
    assert analysis.mentioned_files == ()
    assert analysis.effective_symbol_hits == ()
    assert analysis.path_ident_hits == ("pkg",)
    assert result.mode == "focused"
    assert result.focus_fnames == ()
    assert result.evidence.index_snapshot_id == status.index_snapshot_id
    assert result.evidence.ranking.path_personalization_files == (
        "pkg/service.py",
    )
    assert result.evidence.ranking.personalization_files == ("pkg/service.py",)
    assert result.evidence.ranking.algorithm == "personalized_pagerank"
    assert "pkg/service.py:" in result.repo_map_text


def test_broad_catalog_and_confirmed_focus_reuse_same_snapshot(map_engine_repo: Path):
    engine = MapEngine(map_engine_repo)
    engine.ensure_index()
    analysis = engine.analyze("Explain unknown behavior")

    broad = engine.generate_broad(analysis)
    catalog = engine.build_selector_catalog()
    focused = engine.generate_focused(analysis, focus_fnames=("pkg/service.py",))

    assert analysis.branch == "fuzzy"
    assert broad.mode == "broad"
    assert focused.mode == "focused"
    assert broad.evidence.index_snapshot_id == catalog.index_snapshot_id
    assert focused.evidence.index_snapshot_id == catalog.index_snapshot_id
    assert catalog.candidate_paths == ("app.py", "pkg/service.py", "pkg/standalone.py")
    assert focused.focus_fnames == ("pkg/service.py",)
    assert focused.evidence.ranking.focus_personalization_files == ("pkg/service.py",)


def _fuzzy_analysis():
    from pico.features.map_engine.models import PromptAnalysis

    return PromptAnalysis(
        branch="fuzzy",
        mentioned_files=(),
        mentioned_idents=("unknown",),
        effective_symbol_hits=(),
        path_ident_hits=(),
        path_ident_hit_files={},
    )
