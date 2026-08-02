"""Fixed, model-free retrieval fixture contracts for the v1 evaluation stage."""

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from pico.core.map_selector import build_selector_request
from pico.core.map_selector import parse_selector_output
from pico.evaluation.evaluator import run_fixed_retrieval_eval
from pico.evaluation.retrieval_metrics import collect_retrieval_case_metrics
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
    assert catalog_case["test_path"] == "tests/auth.py"
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


def test_retrieval_metrics_projects_path_ident_branch_a_evidence(
    ground_truth: dict[str, object],
):
    case = _case(ground_truth, "path_ident_only_pico")
    evidence = {
        "analysis": {
            "branch": "specific",
            "mentioned_files": [],
            "effective_symbol_hits": [],
            "path_ident_hits": ["PICO"],
            "path_ident_hit_files": {
                "PICO": [
                    "pico/isolated.py",
                    "pico/runtime.py",
                    "pico/tools.py",
                ]
            },
        },
        "active_result": {
            "mode": "focused",
            "focus_fnames": [],
            "rendered_files": ["pico/runtime.py", "pico/tools.py"],
            "evidence": {
                "ranking": {
                    "focus_personalization_files": [],
                    "path_personalization_files": [
                        "pico/runtime.py",
                        "pico/tools.py",
                    ],
                    "personalization_files": [
                        "pico/runtime.py",
                        "pico/tools.py",
                    ],
                },
                "rendering": {
                    "target_tokens": 4096,
                    "target_chars": 16384,
                    "used_chars": 112,
                    "estimated_tokens": 28,
                    "focus_truncated": False,
                },
                "rendered_files": [
                    {
                        "path": "pico/runtime.py",
                        "top_rank_contributors": [
                            {
                                "source_path": "pico/tools.py",
                                "identifier": "PICO",
                                "weight_multiplier": 75.0,
                                "weight_reason_codes": ["prompt_ident_boost"],
                            }
                        ],
                    }
                ],
            },
        },
    }
    trace_events = [
        {"event": "tool_executed", "name": "list_files", "args": {"path": "."}},
        {"event": "tool_executed", "name": "read_file", "args": {"path": "pico/runtime.py"}},
        {"event": "tool_executed", "name": "read_file", "args": {"path": "pico/isolated.py"}},
    ]

    metrics = collect_retrieval_case_metrics(case, evidence, trace_events)

    assert metrics.effective_file_hit is None
    assert metrics.effective_symbol_hit is None
    assert metrics.effective_path_ident_hit is True
    assert metrics.path_ident_branch_a is True
    assert metrics.path_ident_raw_ident == "PICO"
    assert metrics.path_ident_full_hit_files == (
        "pico/isolated.py",
        "pico/runtime.py",
        "pico/tools.py",
    )
    assert metrics.focus_files == ()
    assert metrics.focus_personalization_files == ()
    assert metrics.path_personalization_files == (
        "pico/runtime.py",
        "pico/tools.py",
    )
    assert metrics.personalization_files == metrics.path_personalization_files
    assert metrics.path_ground_truth_personalization_hit is True
    assert metrics.path_ground_truth_rendered_hit is True
    assert metrics.focus_path_isolated is True
    assert metrics.rendered_files == ("pico/runtime.py", "pico/tools.py")
    assert metrics.rendered_file_hit is True
    assert metrics.first_read_path == "pico/runtime.py"
    assert metrics.first_read_hit is True
    assert metrics.focused_rendering is not None
    assert metrics.focused_rendering.target_tokens == 4096
    assert metrics.focused_rendering.target_chars == 16384
    assert metrics.focused_rendering.used_chars == 112
    assert metrics.focused_rendering.estimated_tokens == 28
    assert metrics.focused_rendering.focus_truncated is False
    assert metrics.broad_rendering is None
    assert metrics.top_contributors[0].weight_multiplier == 75.0
    assert metrics.top_contributors[0].reason_codes == ("prompt_ident_boost",)


def test_retrieval_metrics_distinguishes_hits_misses_and_broad_rendering(
    ground_truth: dict[str, object],
):
    file_case = _case(ground_truth, "file_specific_auth_py")
    symbol_case = _case(ground_truth, "symbol_only_jwt_auth")
    file_evidence = {
        "analysis": {
            "branch": "specific",
            "mentioned_files": ["src/auth.py"],
            "effective_symbol_hits": [],
            "path_ident_hits": [],
            "path_ident_hit_files": {},
        },
        "active_result": {
            "mode": "focused",
            "focus_fnames": ["src/auth.py"],
            "rendered_files": ["src/auth.py"],
            "evidence": {
                "ranking": {
                    "focus_personalization_files": ["src/auth.py"],
                    "path_personalization_files": [],
                    "personalization_files": ["src/auth.py"],
                },
                "rendering": {
                    "target_tokens": 4096,
                    "target_chars": 16384,
                    "used_chars": 40,
                    "estimated_tokens": 10,
                    "focus_truncated": False,
                },
            },
        },
    }
    symbol_evidence = {
        "analysis": {
            "branch": "specific",
            "mentioned_files": [],
            "effective_symbol_hits": ["OtherAuth"],
            "path_ident_hits": [],
            "path_ident_hit_files": {},
        },
        "active_result": {
            "mode": "focused",
            "focus_fnames": [],
            "rendered_files": ["src/other.py"],
            "evidence": {"ranking": {}},
        },
        "broad_result": {
            "mode": "broad",
            "rendered_files": ["src/auth.py"],
            "evidence": {
                "rendering": {
                    "target_tokens": 8192,
                    "target_chars": 32768,
                    "used_chars": 80,
                    "estimated_tokens": 20,
                    "focus_truncated": False,
                }
            },
        },
    }

    file_metrics = collect_retrieval_case_metrics(
        file_case,
        file_evidence,
        [{"event": "tool_executed", "name": "read_file", "args": {"path": "src/auth.py"}}],
    )
    symbol_metrics = collect_retrieval_case_metrics(
        symbol_case,
        symbol_evidence,
        [{"event": "tool_executed", "name": "read_file", "args": {"path": "src/other.py"}}],
    )

    assert file_metrics.effective_file_hit is True
    assert file_metrics.effective_symbol_hit is None
    assert file_metrics.rendered_file_hit is True
    assert file_metrics.first_read_hit is True
    assert symbol_metrics.effective_file_hit is None
    assert symbol_metrics.effective_symbol_hit is False
    assert symbol_metrics.rendered_file_hit is False
    assert symbol_metrics.first_read_hit is False
    assert symbol_metrics.focused_rendering is None
    assert symbol_metrics.broad_rendering is not None
    assert symbol_metrics.broad_rendering.target_tokens == 8192
    assert symbol_metrics.broad_rendering.target_chars == 32768
    assert symbol_metrics.broad_rendering.used_chars == 80
    assert symbol_metrics.broad_rendering.estimated_tokens == 20
    assert symbol_metrics.broad_rendering.focus_truncated is False


def test_retrieval_metrics_projects_complete_selector_request_scalars(
    ground_truth: dict[str, object],
):
    case = _case(ground_truth, "selector_catalog_visibility")
    metrics = collect_retrieval_case_metrics(
        case,
        None,
        [
            {
                "event": "map_selector_requested",
                "input_chars": 2_049,
                "candidate_path_count": 9,
                "rendered_path_count": 4,
                "visible_path_count": 5,
                "definition_count": 18,
                "rendered_definition_count": 11,
                "catalog_truncated": True,
            },
            {
                "event": "map_selector_requested",
                "input_chars": 1_024,
                "candidate_path_count": 3,
                "rendered_path_count": 2,
                "visible_path_count": 2,
                "definition_count": 7,
                "rendered_definition_count": 5,
                "catalog_truncated": False,
            },
        ],
    )

    assert metrics.selector_request is not None
    assert metrics.selector_request.input_chars == 2_049
    assert metrics.selector_request.estimated_tokens == 513
    assert metrics.selector_request.candidate_path_count == 9
    assert metrics.selector_request.rendered_path_count == 4
    assert metrics.selector_request.visible_path_count == 5
    assert metrics.selector_request.definition_count == 18
    assert metrics.selector_request.rendered_definition_count == 11
    assert metrics.selector_request.catalog_truncated is True

    historical_metrics = collect_retrieval_case_metrics(
        case,
        None,
        [{"event": "map_selector_requested", "input_chars": 2_048}],
    )

    assert historical_metrics.selector_request is not None
    assert historical_metrics.selector_request.estimated_tokens == 512
    assert historical_metrics.selector_request.definition_count is None
    assert historical_metrics.selector_request.rendered_definition_count is None
    assert historical_metrics.selector_request.catalog_truncated is None

    malformed_metrics = collect_retrieval_case_metrics(
        case,
        None,
        [{"event": "map_selector_requested", "input_chars": None}],
    )

    assert malformed_metrics.selector_request is not None
    assert malformed_metrics.selector_request.input_chars is None
    assert malformed_metrics.selector_request.estimated_tokens is None


def test_retrieval_metrics_projects_selector_over_budget_broad_fallback(
    ground_truth: dict[str, object],
):
    case = _case(ground_truth, "selector_request_over_budget")
    metrics = collect_retrieval_case_metrics(
        case,
        {
            "branch": "fuzzy",
            "stage": "fallback",
            "selection_decision": {
                "fallback_mode": "broad_map",
                "fallback_reason": "selector_request_over_budget",
            },
        },
        [],
        {
            "model_calls": {"selector_model_calls": 0},
            "request_budget": {"request_over_budget": False},
        },
    )

    assert metrics.fallback_budget is not None
    assert metrics.fallback_budget.selector_model_calls == 0
    assert metrics.fallback_budget.selector_request_over_budget is True
    assert metrics.fallback_budget.broad_fallback is True
    assert metrics.fallback_budget.request_over_budget is False


def test_retrieval_metrics_projects_truncation_reduction_and_omission(
    ground_truth: dict[str, object],
):
    case = _case(ground_truth, "file_specific_auth_py")
    metrics = collect_retrieval_case_metrics(
        case,
        {
            "branch": "specific",
            "stage": "execution",
            "active_result": {
                "mode": "focused",
                "evidence": {"rendering": {"focus_truncated": True}},
            },
            "prompt_injection": {
                "base_prompt_reduction_applied": True,
                "section_rendered": False,
                "omission_reason": "base_prompt_floor",
            },
        },
        [],
        {
            "model_calls": {"selector_model_calls": 1},
            "request_budget": {"request_over_budget": False},
        },
    )

    assert metrics.fallback_budget is not None
    assert metrics.fallback_budget.focus_truncated is True
    assert metrics.fallback_budget.selector_model_calls == 1
    assert metrics.fallback_budget.selector_request_over_budget is None
    assert metrics.fallback_budget.broad_fallback is False
    assert metrics.fallback_budget.base_prompt_reduction_applied is True
    assert metrics.fallback_budget.repo_map_section_rendered is False
    assert metrics.fallback_budget.repo_map_omission_reason == "base_prompt_floor"
    assert metrics.fallback_budget.request_over_budget is False


def test_retrieval_metrics_projects_request_over_budget_without_map_evidence(
    ground_truth: dict[str, object],
):
    case = _case(ground_truth, "selector_request_over_budget")
    metrics = collect_retrieval_case_metrics(
        case,
        None,
        [],
        {"request_budget": {"request_over_budget": True}},
    )

    assert metrics.fallback_budget is not None
    assert metrics.fallback_budget.focus_truncated is None
    assert metrics.fallback_budget.selector_model_calls is None
    assert metrics.fallback_budget.selector_request_over_budget is None
    assert metrics.fallback_budget.broad_fallback is None
    assert metrics.fallback_budget.base_prompt_reduction_applied is None
    assert metrics.fallback_budget.repo_map_section_rendered is None
    assert metrics.fallback_budget.repo_map_omission_reason is None
    assert metrics.fallback_budget.request_over_budget is True


def test_retrieval_metrics_preserves_missing_and_not_applicable_semantics(
    ground_truth: dict[str, object],
):
    case = _case(ground_truth, "path_ident_only_pico")
    missing = collect_retrieval_case_metrics(case, None, [])

    assert missing.effective_file_hit is None
    assert missing.effective_symbol_hit is None
    assert missing.effective_path_ident_hit is None
    assert missing.path_ident_branch_a is None
    assert missing.path_ident_full_hit_files == ()
    assert missing.focus_files == ()
    assert missing.path_personalization_files == ()
    assert missing.rendered_files == ()
    assert missing.rendered_file_hit is None
    assert missing.first_read_path is None
    assert missing.first_read_hit is None
    assert missing.focused_rendering is None
    assert missing.broad_rendering is None
    assert missing.selector_request is None
    assert missing.fallback_budget is None
    assert missing.top_contributors == ()


def test_run_fixed_retrieval_eval_writes_ordered_runtime_evidence_artifact(
    tmp_path: Path,
):
    artifact_path = tmp_path / "artifacts" / "fixed-retrieval-eval.json"
    second_artifact_path = tmp_path / "artifacts" / "fixed-retrieval-eval-second.json"

    artifact = run_fixed_retrieval_eval(artifact_path=artifact_path)
    second_artifact = run_fixed_retrieval_eval(artifact_path=second_artifact_path)

    assert artifact_path.exists()
    assert json.loads(artifact_path.read_text(encoding="utf-8")) == artifact
    assert json.loads(second_artifact_path.read_text(encoding="utf-8")) == second_artifact
    assert artifact_path.read_text(encoding="utf-8") == second_artifact_path.read_text(
        encoding="utf-8"
    )
    assert artifact["schema_version"] == "mapcode.fixed-retrieval-eval.v1"
    assert artifact["artifact_type"] == "fixed-retrieval-eval"
    assert artifact["reproducibility"]["fixture"]["revision"] == "v1"
    assert artifact["reproducibility"]["fixture"]["snapshot_id"].startswith("sha256:")
    assert artifact["reproducibility"]["model_request_budget"]["source"] == "fallback"
    assert artifact["reproducibility"]["execution_budgets"]["max_steps"] == 1
    assert [case["case_id"] for case in artifact["cases"]] == [
        "jwt_auth_baseline",
        "file_specific_auth_py",
        "symbol_only_jwt_auth",
        "path_ident_only_pico",
        "fuzzy_no_signal",
        "selector_catalog_visibility",
        "selector_request_over_budget",
        "selector_failure",
    ]

    path_case = next(
        case for case in artifact["cases"] if case["case_id"] == "path_ident_only_pico"
    )
    assert path_case["sources"]["map_evidence"] == "run_artifact"
    assert path_case["sources"]["trace"] == "run_artifact"
    assert path_case["sources"]["report"] == "run_artifact"
    assert path_case["fixture"]["git_clean"] is True
    assert path_case["metrics"]["path_ident_branch_a"] is True
    assert path_case["metrics"]["focus_files"] == []
    assert path_case["metrics"]["focus_personalization_files"] == []
    assert path_case["metrics"]["fallback_budget"]["selector_model_calls"] == 0
    assert artifact["aggregate"]["effective_path_ident_hit_rate"] == 1.0
    assert artifact["aggregate"]["effective_path_ident_hit_observed_cases"] == 1
