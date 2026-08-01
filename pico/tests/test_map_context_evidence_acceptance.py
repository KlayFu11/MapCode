import json
import os
import subprocess
from dataclasses import replace
from unittest.mock import patch

from pico import Pico, SessionStore, WorkspaceContext
from pico.core.map_context_prompt import REPO_MAP_NAVIGATION_CONTRACT, RepoMapSectionRender
from pico.core.run_store import RunStore
from pico.testing import ScriptedModelClient


def _git(repo, *args):
    subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=True,
        timeout=5,
    )


def _runtime(tmp_path, run_store=None):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text(
        "class AuthService:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "mapcode@example.test")
    _git(tmp_path, "config", "user.name", "MapCode Test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "fixture")
    return Pico(
        model_client=ScriptedModelClient(
            [
                '<tool name="list_files" path="."></tool>',
                "<final>Done.</final>",
            ]
        ),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".pico" / "sessions"),
        run_store=run_store,
        approval_policy="auto",
        feature_flags={"map_engine": True},
    )


class _RecordingCoordinator:
    def __init__(self, delegate):
        self.delegate = delegate
        self.finalize_calls = []

    def analyze_turn(self, task_state, user_message):
        return self.delegate.analyze_turn(task_state, user_message)

    def prepare_specific(self, task_state, analysis):
        return self.delegate.prepare_specific(task_state, analysis)

    def finalize_prompt_context(self, task_state, result, repo_map_render):
        self.finalize_calls.append((task_state, result, repo_map_render))
        return self.delegate.finalize_prompt_context(
            task_state,
            result,
            repo_map_render,
        )


def test_first_main_build_persists_complete_repo_map_evidence_before_prompt_event(
    tmp_path,
):
    agent = _runtime(tmp_path)
    coordinator = _RecordingCoordinator(agent.map_context_coordinator)
    agent.map_context_coordinator = coordinator
    build_results = []
    original_build = agent._build_prompt_and_metadata

    def record_main_build(user_message, *, purpose):
        result = original_build(user_message, purpose=purpose)
        if purpose == "main_model":
            build_results.append(result)
        return result

    agent._build_prompt_and_metadata = record_main_build

    assert agent.engine.ask("Inspect src/auth.py.") == "Done."

    assert len(build_results) == 2
    assert len(coordinator.finalize_calls) == 1
    _, prepared, rendered = coordinator.finalize_calls[0]
    assert rendered is build_results[0].repo_map_render
    assert rendered.section_rendered is True

    artifacts_dir = agent.current_run_dir / "artifacts"
    repo_map_path = artifacts_dir / "repo-map-001.txt"
    evidence_path = artifacts_dir / "map-evidence-001.json"
    assert repo_map_path.read_text(encoding="utf-8") == rendered.section_text
    assert build_results[1].repo_map_render.section_text == rendered.section_text
    assert [path.name for path in artifacts_dir.glob("repo-map-*.txt")] == [
        "repo-map-001.txt"
    ]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert set(evidence) == {
        "schema_version",
        "map_context_id",
        "run_id",
        "branch",
        "stage",
        "index_snapshot_id",
        "analysis",
        "broad_result",
        "active_result",
        "selection_decision",
        "prompt_injection",
        "repo_map_artifact_path",
    }
    assert evidence["schema_version"] == "mapcode.map-evidence.v1"
    assert evidence["map_context_id"] == prepared.map_context_id
    assert evidence["run_id"] == agent.current_task_state.run_id
    assert evidence["branch"] == prepared.branch
    assert evidence["stage"] == prepared.stage
    assert evidence["index_snapshot_id"] == (
        prepared.active_result.evidence.index_snapshot_id
    )
    assert evidence["analysis"] == {
        "branch": prepared.active_result.evidence.analysis.branch,
        "mentioned_files": list(
            prepared.active_result.evidence.analysis.mentioned_files
        ),
        "mentioned_idents": list(
            prepared.active_result.evidence.analysis.mentioned_idents
        ),
        "effective_symbol_hits": list(
            prepared.active_result.evidence.analysis.effective_symbol_hits
        ),
        "path_ident_hits": list(
            prepared.active_result.evidence.analysis.path_ident_hits
        ),
        "path_ident_hit_files": {
            ident: list(paths)
            for ident, paths in prepared.active_result.evidence.analysis.path_ident_hit_files.items()
        },
    }
    active_evidence = evidence["active_result"]["evidence"]
    assert active_evidence["schema_version"] == "mapcode.map-engine.v1"
    assert active_evidence["index_snapshot_id"] == evidence["index_snapshot_id"]
    assert active_evidence["analysis"] == evidence["analysis"]
    ranking = prepared.active_result.evidence.ranking
    assert active_evidence["ranking"] == {
        "policy_version": ranking.policy_version,
        "algorithm": ranking.algorithm,
        "focus_fnames": list(ranking.focus_fnames),
        "ident_boost_inputs": list(ranking.ident_boost_inputs),
        "focus_personalization_files": list(ranking.focus_personalization_files),
        "path_personalization_files": list(ranking.path_personalization_files),
        "personalization_files": list(ranking.personalization_files),
        "top_ranked_files": list(ranking.top_ranked_files),
    }
    assert active_evidence["rendering"] == {
        "target_tokens": prepared.active_result.evidence.rendering.target_tokens,
        "target_chars": prepared.active_result.evidence.rendering.target_chars,
        "used_chars": prepared.active_result.evidence.rendering.used_chars,
        "estimated_tokens": prepared.active_result.evidence.rendering.estimated_tokens,
        "budget_reduction_applied": prepared.active_result.evidence.rendering.budget_reduction_applied,
        "focus_truncated": prepared.active_result.evidence.rendering.focus_truncated,
    }
    assert evidence["active_result"]["rendered_files"] == list(
        prepared.active_result.rendered_files
    )
    assert evidence["active_result"]["rendered_symbols"] == list(
        prepared.active_result.rendered_symbols
    )
    assert [
        {
            "path": item["path"],
            "prompt_path_ident_hits": item["prompt_path_ident_hits"],
            "top_rank_contributors": item["top_rank_contributors"],
        }
        for item in active_evidence["rendered_files"]
    ] == [
        {
            "path": item.path,
            "prompt_path_ident_hits": list(item.prompt_path_ident_hits),
            "top_rank_contributors": [
                {
                    "source_path": contributor.source_path,
                    "identifier": contributor.identifier,
                    "weighted_edge": contributor.weighted_edge,
                    "weight_multiplier": contributor.weight_multiplier,
                    "weight_reason_codes": list(contributor.weight_reason_codes),
                }
                for contributor in item.top_rank_contributors
            ],
        }
        for item in prepared.active_result.evidence.rendered_files
    ]
    assert [
        {
            "path": item["path"],
            "prompt_path_ident_hits": item["prompt_path_ident_hits"],
            "omission_reason": item["omission_reason"],
        }
        for item in active_evidence["omitted_files"]
    ] == [
        {
            "path": item.path,
            "prompt_path_ident_hits": list(item.prompt_path_ident_hits),
            "omission_reason": item.omission_reason,
        }
        for item in prepared.active_result.evidence.omitted_files
    ]
    assert evidence["broad_result"] is None
    assert evidence["selection_decision"] is None
    assert evidence["prompt_injection"] == {
        "section_rendered": rendered.section_rendered,
        "contract_rendered": rendered.contract_rendered,
        "fallback_notice_rendered": rendered.fallback_notice_rendered,
        "map_body_raw_chars": rendered.map_body_raw_chars,
        "map_body_rendered_chars": rendered.map_body_rendered_chars,
        "section_rendered_chars": rendered.section_rendered_chars,
        "section_rendered_hash": rendered.section_rendered_hash,
        "base_prompt_reduction_applied": rendered.base_prompt_reduction_applied,
        "omission_reason": rendered.omission_reason,
    }
    assert evidence["repo_map_artifact_path"].endswith("repo-map-001.txt")
    assert "evidence_artifact_path" not in evidence
    assert "repo_map_text" not in evidence["active_result"]
    serialized_evidence = json.dumps(evidence, sort_keys=True)
    assert REPO_MAP_NAVIGATION_CONTRACT not in serialized_evidence
    assert "[Selector Candidate Catalog]" not in serialized_evidence
    assert "candidate_paths" not in serialized_evidence

    trace_rows = [
        json.loads(line)
        for line in (agent.current_run_dir / "trace.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    trace_events = [row["event"] for row in trace_rows]
    assert trace_events.index("map_generated") < trace_events.index("prompt_built")
    assert trace_events.index("prompt_built") < trace_events.index("model_requested")

    ranked = next(row for row in trace_rows if row["event"] == "map_context_ranked")
    selected = next(
        row for row in trace_rows if row["event"] == "map_context_selected"
    )
    prompt_built = next(row for row in trace_rows if row["event"] == "prompt_built")
    metadata = build_results[0].metadata
    assert ranked["index_snapshot_id"] == evidence["index_snapshot_id"]
    assert selected["rendered_files"] == evidence["active_result"]["rendered_files"]
    assert prompt_built["repo_map_render"] == metadata["map_context"]
    assert prompt_built["request_budget"] == {
        key: metadata[key]
        for key in (
            "model_input_budget_tokens",
            "prompt_safety_margin_tokens",
            "active_repo_map_reservation_tokens",
            "base_prompt_budget_tokens",
            "estimated_request_tokens",
            "request_over_budget",
            "model_request_budget_source",
            "base_prompt_over_budget_with_repo_map_reservation",
        )
    }
    assert "repo_map_text" not in prompt_built["repo_map_render"]
    assert "sections" not in prompt_built["request_budget"]

    report = json.loads(
        (agent.current_run_dir / "report.json").read_text(encoding="utf-8")
    )
    assert report["map_context"] == agent.current_task_state.map_context_summary
    assert report["map_context"]["budget_reduction_applied"] is False
    assert report["map_context"]["base_prompt_reduction_applied"] is False
    assert report["map_context"]["omission_reason"] is None
    assert report["model_calls"] == {
        "main_model_calls": agent.current_task_state.main_model_calls,
        "selector_model_calls": 0,
        "total_model_calls": agent.current_task_state.main_model_calls,
    }
    assert report["request_budget"] == {
        "model_input_budget_tokens": agent.model_request_budget.model_input_budget_tokens,
        "prompt_safety_margin_tokens": agent.model_request_budget.prompt_safety_margin_tokens,
        "model_request_budget_source": agent.model_request_budget.source,
        "budget_reduction_applied": False,
        "base_prompt_reduction_applied": False,
        "omission_reason": None,
        "request_over_budget": False,
    }
    serialized_report = json.dumps(report, sort_keys=True)
    assert REPO_MAP_NAVIGATION_CONTRACT not in serialized_report
    assert "candidate_paths" not in serialized_report


def test_omitted_first_main_build_persists_empty_repo_map_evidence_before_fallback(
    tmp_path,
):
    agent = _runtime(tmp_path)
    coordinator = _RecordingCoordinator(agent.map_context_coordinator)
    agent.map_context_coordinator = coordinator
    build_results = []
    original_build = agent._build_prompt_and_metadata

    def force_first_main_render_omitted(user_message, *, purpose):
        result = original_build(user_message, purpose=purpose)
        if purpose != "main_model":
            return result
        if not build_results:
            original_render = result.repo_map_render
            assert original_render is not None
            omitted_render = RepoMapSectionRender.omitted(
                "base_prompt_cannot_fit_with_repo_map_reservation",
                map_body_raw_chars=original_render.map_body_raw_chars,
                base_prompt_reduction_applied=original_render.base_prompt_reduction_applied,
            )
            metadata = dict(result.metadata)
            metadata["map_context"] = {
                "section_rendered": omitted_render.section_rendered,
                "contract_rendered": omitted_render.contract_rendered,
                "fallback_notice_rendered": omitted_render.fallback_notice_rendered,
                "map_body_raw_chars": omitted_render.map_body_raw_chars,
                "map_body_rendered_chars": omitted_render.map_body_rendered_chars,
                "section_rendered_chars": omitted_render.section_rendered_chars,
                "section_rendered_hash": omitted_render.section_rendered_hash,
                "base_prompt_reduction_applied": omitted_render.base_prompt_reduction_applied,
                "omission_reason": omitted_render.omission_reason,
            }
            result = replace(
                result,
                metadata=metadata,
                repo_map_render=omitted_render,
            )
        build_results.append(result)
        return result

    agent._build_prompt_and_metadata = force_first_main_render_omitted

    assert agent.engine.ask("Inspect src/auth.py.") == "Done."

    assert len(build_results) == 3
    assert len(coordinator.finalize_calls) == 1
    _, _, rendered = coordinator.finalize_calls[0]
    assert rendered is build_results[0].repo_map_render
    assert rendered.section_text == ""
    assert build_results[1].repo_map_render is None
    assert build_results[2].repo_map_render is None

    artifacts_dir = agent.current_run_dir / "artifacts"
    repo_map_path = artifacts_dir / "repo-map-001.txt"
    evidence_path = artifacts_dir / "map-evidence-001.json"
    assert repo_map_path.read_text(encoding="utf-8") == ""
    assert [path.name for path in artifacts_dir.glob("repo-map-*.txt")] == [
        "repo-map-001.txt"
    ]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["prompt_injection"]["section_rendered"] is False
    assert (
        evidence["prompt_injection"]["omission_reason"]
        == "base_prompt_cannot_fit_with_repo_map_reservation"
    )
    assert agent.current_task_state.selector_model_calls == 0
    assert all(
        REPO_MAP_NAVIGATION_CONTRACT not in prompt
        for prompt in agent.model_client.prompts
    )

    trace_events = [
        json.loads(line)["event"]
        for line in (agent.current_run_dir / "trace.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert trace_events.count("map_generated") == 1
    assert "map_context_failed" not in trace_events

    report = json.loads(
        (agent.current_run_dir / "report.json").read_text(encoding="utf-8")
    )
    assert report["map_context"]["enabled"] is True
    assert report["request_budget"]["omission_reason"] == (
        "base_prompt_cannot_fit_with_repo_map_reservation"
    )
    assert report["request_budget"]["base_prompt_reduction_applied"] is False


def test_fuzzy_selection_evidence_keeps_broad_and_focused_facts_without_catalog_text(
    tmp_path,
):
    agent = _runtime(tmp_path)
    agent.model_client = ScriptedModelClient(
        [
            json.dumps(
                {
                    "suggested_files": ["src/auth.py"],
                    "reasoning": "Authentication is the relevant source module.",
                }
            ),
            "<final>Done.</final>",
        ]
    )
    agent.ask_user_callback = lambda _question, _choices: "接受全部建议"

    assert agent.engine.ask("Explain the repository architecture.") == "Done."

    evidence = json.loads(
        (agent.current_run_dir / "artifacts" / "map-evidence-001.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence["branch"] == "fuzzy"
    assert evidence["stage"] == "execution"
    assert evidence["broad_result"] is not None
    assert evidence["broad_result"]["mode"] == "broad"
    assert evidence["active_result"]["mode"] == "focused"
    assert evidence["broad_result"]["evidence"]["index_snapshot_id"] == evidence[
        "index_snapshot_id"
    ]
    assert evidence["active_result"]["evidence"]["index_snapshot_id"] == evidence[
        "index_snapshot_id"
    ]
    assert evidence["broad_result"]["evidence"]["analysis"] == evidence["analysis"]
    assert evidence["active_result"]["evidence"]["analysis"] == evidence["analysis"]
    assert evidence["selection_decision"] == {
        "selector_result": {
            "suggested_files": ["src/auth.py"],
            "invalid_files": [],
            "excess_files": [],
            "reasoning": "Authentication is the relevant source module.",
            "parse_error": None,
        },
        "confirmed_files": ["src/auth.py"],
        "fallback_mode": "none",
        "fallback_reason": None,
    }
    assert evidence["active_result"]["focus_fnames"] == evidence[
        "selection_decision"
    ]["confirmed_files"]
    serialized_evidence = json.dumps(evidence, sort_keys=True)
    assert "[Broad Repo Map]" not in serialized_evidence
    assert "[Selector Candidate Catalog]" not in serialized_evidence
    assert "candidate_paths" not in serialized_evidence
    assert "evidence_artifact_path" not in evidence


def test_fuzzy_one_shot_fallback_evidence_reuses_the_broad_result(tmp_path):
    agent = _runtime(tmp_path)
    agent.model_client = ScriptedModelClient(["<final>Done.</final>"])

    assert agent.engine.ask("Explain the repository architecture.") == "Done."

    evidence = json.loads(
        (agent.current_run_dir / "artifacts" / "map-evidence-001.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence["branch"] == "fuzzy"
    assert evidence["stage"] == "fallback"
    assert evidence["active_result"] == evidence["broad_result"]
    assert evidence["selection_decision"] == {
        "selector_result": None,
        "confirmed_files": [],
        "fallback_mode": "broad_map",
        "fallback_reason": "one_shot_no_confirm",
    }
    assert "repo_map_text" not in json.dumps(evidence, sort_keys=True)
    assert "evidence_artifact_path" not in evidence


def test_runtime_reporter_events_precede_the_main_model_and_hide_when_disabled(
    tmp_path,
):
    agent = _runtime(tmp_path)

    events = list(agent.engine.run_turn("Inspect src/auth.py."))
    event_types = [event["type"] for event in events]
    assert event_types.index("index_ready") < event_types.index("map_context_ready")
    assert event_types.index("map_context_ready") < event_types.index("model_requested")
    ready_event = next(event for event in events if event["type"] == "map_context_ready")
    assert ready_event["payload"]["evidence_artifact_path"].endswith(
        "map-evidence-001.json"
    )

    agent.feature_flags["map_engine"] = False
    disabled_events = list(agent.engine.run_turn("Inspect src/auth.py."))
    assert not {
        "index_ready",
        "broad_ready",
        "map_context_ready",
        "map_context_failed",
    }.intersection(event["type"] for event in disabled_events)


def test_runtime_emits_reporter_failure_from_existing_map_context_error(tmp_path):
    agent = _runtime(tmp_path)

    class FailingCoordinator:
        def analyze_turn(self, _task_state, _user_message):
            raise OSError("index storage unavailable")

    agent.map_context_coordinator = FailingCoordinator()
    events = list(agent.engine.run_turn("Inspect src/auth.py."))

    failure = next(event for event in events if event["type"] == "map_context_failed")
    assert failure["payload"] == {
        "error_type": "OSError",
        "fallback": "without_repo_map",
    }


def test_map_context_run_redacts_secret_from_all_persisted_evidence_layers(
    tmp_path,
):
    secret = "mapcode-evidence-secret-123"
    with patch.dict(os.environ, {"OPENAI_API_KEY": secret}, clear=False):
        run_store = RunStore(tmp_path / ".pico" / "runs")
        agent = _runtime(tmp_path, run_store=run_store)
        agent.model_client = ScriptedModelClient(["<final>Done.</final>"])
        events = list(
            agent.engine.run_turn(
                f"Inspect src/auth.py using token {secret}."
            )
        )

    assert run_store.redactor == agent.redact_artifact
    run_dir = agent.current_run_dir
    persisted_texts = {
        "trace": (run_dir / "trace.jsonl").read_text(encoding="utf-8"),
        "task_state": (run_dir / "task_state.json").read_text(encoding="utf-8"),
        "report": (run_dir / "report.json").read_text(encoding="utf-8"),
        "repo_map": (run_dir / "artifacts" / "repo-map-001.txt").read_text(
            encoding="utf-8"
        ),
        "map_evidence": (
            run_dir / "artifacts" / "map-evidence-001.json"
        ).read_text(encoding="utf-8"),
        "reporter": json.dumps(events, sort_keys=True),
    }

    assert all(secret not in text for text in persisted_texts.values())
    assert "<redacted>" in persisted_texts["trace"]
    assert "<redacted>" in persisted_texts["task_state"]
    assert "<redacted>" in persisted_texts["report"]
    assert any(secret in prompt for prompt in agent.model_client.prompts)
