"""Fixed, model-free retrieval fixture contracts for the v1 evaluation stage."""

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from pico.core.map_selector import build_selector_request
from pico.core.map_selector import parse_selector_output
from pico.features.map_engine import selector_catalog
from pico.features.map_engine.engine import MapEngine
from pico.features.map_engine.source_files import list_python_source_files


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "map_engine_eval"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )


@pytest.fixture
def eval_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "map_engine_eval"
    shutil.copytree(FIXTURE_ROOT, repo)
    _git(repo, "init")
    _git(repo, "config", "user.email", "mapcode@example.test")
    _git(repo, "config", "user.name", "MapCode Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixed retrieval fixture")
    return repo


@pytest.fixture
def ground_truth(eval_repo: Path) -> dict[str, object]:
    return json.loads((eval_repo / "ground_truth.json").read_text(encoding="utf-8"))


def _case(ground_truth: dict[str, object], case_id: str) -> dict[str, object]:
    cases = ground_truth["cases"]
    assert isinstance(cases, list)
    return next(case for case in cases if case["case_id"] == case_id)


def test_fixed_fixture_is_a_committed_git_repo_and_skips_static_ground_truth(
    eval_repo: Path,
):
    assert subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=eval_repo,
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    ).stdout == ""

    selection = list_python_source_files(eval_repo)
    status = MapEngine(eval_repo).ensure_index()

    assert status.file_count == 7
    assert [(skipped.path, skipped.reason) for skipped in selection.skipped_files] == [
        ("ground_truth.json", "non_python"),
    ]


def test_ground_truth_cases_are_static_and_cover_required_retrieval_inputs(
    ground_truth: dict[str, object],
):
    assert ground_truth["schema_version"] == "mapcode.retrieval-ground-truth.v1"
    assert [case["case_id"] for case in ground_truth["cases"]] == [
        "jwt_auth_baseline",
        "file_specific_auth_py",
        "symbol_only_jwt_auth",
        "path_ident_only_pico",
        "fuzzy_no_signal",
        "selector_catalog_visibility",
        "selector_request_over_budget",
        "selector_failure",
    ]
    assert _case(ground_truth, "jwt_auth_baseline")["request"] == (
        "fix token validation in JWTAuth"
    )
    assert _case(ground_truth, "jwt_auth_baseline")[
        "ground_truth_files"
    ] == ["src/auth.py"]
    file_specific_case = _case(ground_truth, "file_specific_auth_py")
    assert file_specific_case["request"] == "fix authentication in src/auth.py"
    assert file_specific_case["ground_truth_files"] == ["src/auth.py"]
    assert file_specific_case["expected_branch"] == "specific"
    catalog_case = _case(ground_truth, "selector_catalog_visibility")
    assert catalog_case["preferred_source_path"] == "src/auth.py"
    assert catalog_case["test_path"] == "tests/test_auth.py"
    assert catalog_case["candidate_only_path"] == "src/zz_hidden_adapter.py"


def test_fixed_fixture_separates_file_symbol_path_ident_and_fuzzy_branches(
    eval_repo: Path,
    ground_truth: dict[str, object],
):
    engine = MapEngine(eval_repo)
    engine.ensure_index()

    baseline_case = _case(ground_truth, "jwt_auth_baseline")
    baseline_analysis = engine.analyze(str(baseline_case["request"]))
    baseline_result = engine.generate_focused(
        baseline_analysis,
        focus_fnames=baseline_analysis.mentioned_files,
    )
    assert baseline_analysis.branch == "specific"
    assert baseline_analysis.effective_symbol_hits == ("JWTAuth",)
    assert "src/auth.py" in baseline_result.rendered_files

    file_case = _case(ground_truth, "file_specific_auth_py")
    file_analysis = engine.analyze(str(file_case["request"]))
    file_result = engine.generate_focused(
        file_analysis,
        focus_fnames=file_analysis.mentioned_files,
    )
    assert file_analysis.branch == "specific"
    assert file_analysis.mentioned_files == ("src/auth.py",)
    assert "src/auth.py" in file_result.rendered_files

    symbol_case = _case(ground_truth, "symbol_only_jwt_auth")
    symbol_analysis = engine.analyze(str(symbol_case["request"]))
    symbol_result = engine.generate_focused(
        symbol_analysis,
        focus_fnames=symbol_analysis.mentioned_files,
    )
    assert symbol_analysis.mentioned_files == ()
    assert symbol_analysis.effective_symbol_hits == ("JWTAuth",)
    assert symbol_result.focus_fnames == ()

    path_case = _case(ground_truth, "path_ident_only_pico")
    path_analysis = engine.analyze(str(path_case["request"]))
    path_result = engine.generate_focused(
        path_analysis,
        focus_fnames=path_analysis.mentioned_files,
    )
    assert path_analysis.mentioned_files == ()
    assert path_analysis.effective_symbol_hits == ()
    assert path_analysis.path_ident_hits == ("PICO",)
    assert path_analysis.path_ident_hit_files["PICO"] == (
        "pico/isolated.py",
        "pico/runtime.py",
        "pico/tools.py",
    )
    assert path_result.focus_fnames == ()
    assert path_result.evidence.ranking.path_personalization_files == (
        "pico/runtime.py",
        "pico/tools.py",
    )

    fuzzy_case = _case(ground_truth, "fuzzy_no_signal")
    fuzzy_analysis = engine.analyze(str(fuzzy_case["request"]))
    assert fuzzy_analysis.branch == "fuzzy"
    assert fuzzy_analysis.mentioned_files == ()
    assert fuzzy_analysis.effective_symbol_hits == ()
    assert fuzzy_analysis.path_ident_hits == ()


def test_selector_visible_paths_reject_hidden_catalog_candidates(
    eval_repo: Path,
    ground_truth: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
):
    engine = MapEngine(eval_repo)
    engine.ensure_index()
    fuzzy_analysis = engine.analyze("Explain the deployment story.")
    broad = engine.generate_broad(fuzzy_analysis)
    monkeypatch.setattr(selector_catalog, "SELECTOR_CATALOG_MAX_FILES", 2)
    catalog = engine.build_selector_catalog()
    catalog_case = _case(ground_truth, "selector_catalog_visibility")
    source_path = str(catalog_case["preferred_source_path"])
    test_path = str(catalog_case["test_path"])
    hidden_path = str(catalog_case["candidate_only_path"])
    visible_broad = replace(
        broad,
        repo_map_text=f"{source_path}:",
        rendered_files=(source_path,),
    )

    request = build_selector_request(
        str(catalog_case["request"]),
        visible_broad,
        catalog,
    )
    parsed = parse_selector_output(
        json.dumps(
            {
                "suggested_files": [source_path, test_path, hidden_path],
                "reasoning": "fixture-only visible-path check",
            }
        ),
        frozenset(request.visible_paths),
    )

    assert source_path in catalog.candidate_paths
    assert test_path in catalog.candidate_paths
    assert hidden_path in catalog.candidate_paths
    assert hidden_path not in catalog.rendered_paths
    assert source_path in request.visible_paths
    assert test_path not in request.visible_paths
    assert hidden_path not in request.visible_paths
    assert "Prefer implementation/source files over test files" in request.system_prompt
    assert parsed.suggested_files == (source_path,)
    assert parsed.invalid_files == (test_path, hidden_path)
