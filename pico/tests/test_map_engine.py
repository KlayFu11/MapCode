import subprocess
from pathlib import Path

import pytest

from pico.features.map_engine.engine import MapEngine
from pico.features.map_engine.engine import MapEngineIndexNotReady


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
