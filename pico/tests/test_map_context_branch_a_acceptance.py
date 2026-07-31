import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import ANY

import pytest

from pico import Pico, SessionStore, WorkspaceContext
from pico.core.map_context_prompt import (
    REPO_MAP_NAVIGATION_CONTRACT,
    RepoMapSectionRender,
)
from pico.features.map_engine.models import PromptAnalysis
from pico.providers import ProviderError
from pico.testing import ScriptedModelClient


def _runtime(tmp_path, outputs, **kwargs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    feature_flags = kwargs.pop("feature_flags", {"map_engine": True})
    return Pico(
        model_client=ScriptedModelClient(outputs),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".pico" / "sessions"),
        approval_policy="auto",
        feature_flags=feature_flags,
        **kwargs,
    )


def _analysis(*, mentioned_files=(), effective_symbol_hits=(), path_ident_hits=()):
    return PromptAnalysis(
        branch="specific",
        mentioned_files=mentioned_files,
        mentioned_idents=effective_symbol_hits + path_ident_hits,
        effective_symbol_hits=effective_symbol_hits,
        path_ident_hits=path_ident_hits,
        path_ident_hit_files={ident: () for ident in path_ident_hits},
    )


class _BranchACoordinator:
    def __init__(self, analysis):
        self.analysis = analysis
        self.calls = []
        self.prepared_context = None
        self.finalized_context = None

    def analyze_turn(self, task_state, user_message):
        self.calls.append(("analyze_turn", user_message))
        return self.analysis

    def prepare_specific(self, task_state, analysis):
        self.calls.append(("prepare_specific", analysis))
        self.prepared_context = SimpleNamespace(
            map_context_id="mapctx_stable",
            branch="specific",
            stage="execution",
            active_result=SimpleNamespace(
                repo_map_text="src/auth.py: AuthService",
                focus_fnames=analysis.mentioned_files,
            ),
            selection_decision=None,
            prompt_injection=None,
            repo_map_artifact_path=None,
            evidence_artifact_path=None,
        )
        return self.prepared_context

    def finalize_prompt_context(self, task_state, result, repo_map_render):
        self.calls.append(("finalize_prompt_context", repo_map_render))
        assert result is self.prepared_context
        self.finalized_context = SimpleNamespace(
            map_context_id=result.map_context_id,
            branch=result.branch,
            stage=result.stage,
            active_result=result.active_result,
            selection_decision=result.selection_decision,
            prompt_injection=SimpleNamespace(section_rendered=True),
            repo_map_artifact_path="repo-map-001.txt",
            evidence_artifact_path="map-evidence-001.json",
        )
        return self.finalized_context


@pytest.mark.parametrize(
    "analysis",
    [
        _analysis(mentioned_files=("src/auth.py",)),
        _analysis(effective_symbol_hits=("AuthService",)),
        _analysis(path_ident_hits=("pico",)),
    ],
    ids=("file", "symbol", "path-ident"),
)
def test_branch_a_prepares_once_after_run_started_before_first_main_build(
    tmp_path, analysis
):
    agent = _runtime(
        tmp_path,
        [
            '<tool name="list_files" path="."></tool>',
            "<final>Done.</final>",
        ],
    )
    coordinator = _BranchACoordinator(analysis)
    agent.map_context_coordinator = coordinator
    build_contexts = []
    original_build = agent._build_prompt_and_metadata

    def record_main_build(user_message, *, purpose):
        if purpose == "main_model":
            build_contexts.append(agent.current_map_context)
        return original_build(user_message, purpose=purpose)

    agent._build_prompt_and_metadata = record_main_build

    list(agent.engine.run_turn("Explain the target."))

    assert coordinator.calls == [
        ("analyze_turn", "Explain the target."),
        ("prepare_specific", analysis),
        ("finalize_prompt_context", ANY),
    ]
    assert build_contexts == [coordinator.prepared_context, coordinator.finalized_context]
    assert coordinator.prepared_context is not coordinator.finalized_context
    assert (
        coordinator.prepared_context.map_context_id
        == coordinator.finalized_context.map_context_id
    )
    assert coordinator.prepared_context.active_result.focus_fnames == analysis.mentioned_files
    assert agent.current_map_context is None
    trace_events = [
        json.loads(line)["event"]
        for line in (agent.current_run_dir / "trace.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert trace_events.index("run_started") < trace_events.index("prompt_built")


def test_branch_a_tool_loop_and_provider_retry_reuse_finalized_map_context(tmp_path):
    agent = _runtime(
        tmp_path,
        [
            '<tool name="list_files" path="."></tool>',
            ProviderError(
                "empty provider response",
                code="empty_response",
            ),
            "<final>Recovered after retry.</final>",
        ],
    )
    analysis = _analysis(mentioned_files=("src/auth.py",))
    coordinator = _BranchACoordinator(analysis)
    agent.map_context_coordinator = coordinator
    build_contexts = []
    original_build = agent._build_prompt_and_metadata

    def record_main_build(user_message, *, purpose):
        if purpose == "main_model":
            build_contexts.append(agent.current_map_context)
        return original_build(user_message, purpose=purpose)

    agent._build_prompt_and_metadata = record_main_build

    events = list(agent.engine.run_turn("Inspect the auth implementation."))

    assert events[-2]["content"] == "Recovered after retry."
    assert [event["type"] for event in events if event["type"] == "tool_call"] == [
        "tool_call"
    ]
    assert [item["name"] for item in agent.session["history"] if item["role"] == "tool"] == [
        "list_files"
    ]
    assert coordinator.calls == [
        ("analyze_turn", "Inspect the auth implementation."),
        ("prepare_specific", analysis),
        ("finalize_prompt_context", ANY),
    ]
    assert build_contexts == [
        coordinator.prepared_context,
        coordinator.finalized_context,
        coordinator.finalized_context,
    ]

    trace_events = [
        json.loads(line)
        for line in (agent.current_run_dir / "trace.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    prompt_built_events = [
        event for event in trace_events if event["event"] == "prompt_built"
    ]
    assert len(prompt_built_events) == 3
    map_context_summaries = [
        event["prompt_metadata"]["map_context"] for event in prompt_built_events
    ]
    assert all(summary["section_rendered"] is True for summary in map_context_summaries)
    assert all(summary["omission_reason"] is None for summary in map_context_summaries)
    assert len({summary["section_rendered_hash"] for summary in map_context_summaries}) == 1
    assert len({summary["section_rendered_chars"] for summary in map_context_summaries}) == 1
    assert all(
        event["prompt_metadata"]["active_repo_map_reservation_tokens"] > 0
        and event["prompt_metadata"]["estimated_request_tokens"] > 0
        and event["prompt_metadata"]["request_over_budget"] is False
        for event in prompt_built_events
    )
    assert [event["event"] for event in trace_events].count("tool_executed") == 1
    retry_event = next(
        event for event in trace_events if event["event"] == "model_retry_scheduled"
    )
    assert retry_event["code"] == "empty_response"
    assert retry_event["retry_count"] == 1


@pytest.mark.parametrize(
    "exit_path",
    (
        "completed",
        "provider_failure",
        "stopped",
        "step_limit",
        "retry_limit",
        "over_budget",
    ),
)
def test_branch_a_clears_current_map_context_after_every_run_exit(tmp_path, exit_path):
    outputs = ["<final>Done.</final>"]
    runtime_kwargs = {}
    expected_status = "completed"
    expected_stop_reason = "final_answer_returned"

    if exit_path == "provider_failure":
        outputs = [ProviderError("rate limited", code="rate_limited")]
        expected_status = "failed"
        expected_stop_reason = "model_error"
    elif exit_path == "stopped":
        expected_status = "stopped"
        expected_stop_reason = "aborted"
    elif exit_path == "step_limit":
        outputs = [
            '<tool name="list_files" path="."></tool>',
            "I cannot summarize this run.",
        ]
        runtime_kwargs["max_steps"] = 1
        expected_status = "stopped"
        expected_stop_reason = "step_limit_reached"
    elif exit_path == "retry_limit":
        outputs = ["retry"] * 3
        runtime_kwargs["max_steps"] = 1
        expected_status = "stopped"
        expected_stop_reason = "retry_limit_reached"
    elif exit_path == "over_budget":
        expected_status = "stopped"
        expected_stop_reason = "request_over_budget"

    agent = _runtime(tmp_path, outputs, **runtime_kwargs)
    analysis = _analysis(mentioned_files=("src/auth.py",))
    coordinator = _BranchACoordinator(analysis)
    agent.map_context_coordinator = coordinator

    if exit_path == "stopped":
        agent.abort_requested = True
    elif exit_path == "over_budget":
        original_build = agent._build_prompt_and_metadata

        def build_over_budget(user_message, *, purpose):
            result = original_build(user_message, purpose=purpose)
            if purpose != "main_model":
                return result
            metadata = dict(result.metadata)
            metadata["request_over_budget"] = True
            return replace(result, metadata=metadata)

        agent._build_prompt_and_metadata = build_over_budget

    list(agent.engine.run_turn("Explain the target."))

    assert coordinator.prepared_context is not None
    if exit_path != "stopped":
        assert coordinator.finalized_context is not None
    assert agent.current_task_state.status == expected_status
    assert agent.current_task_state.stop_reason == expected_stop_reason
    assert agent.current_map_context is None


def test_branch_a_preparation_failure_emits_trace_and_continues_without_map(tmp_path):
    agent = _runtime(tmp_path, ["<final>Fallback response.</final>"])

    class _FailingCoordinator:
        def analyze_turn(self, task_state, user_message):
            raise RuntimeError("index unavailable")

    agent.map_context_coordinator = _FailingCoordinator()

    assert agent.engine.ask("Explain the target.") == "Fallback response."
    assert agent.current_map_context is None
    trace_events = [
        json.loads(line)
        for line in (agent.current_run_dir / "trace.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    failure = next(event for event in trace_events if event["event"] == "map_context_failed")
    assert failure["error_type"] == "RuntimeError"
    assert failure["fallback"] == "without_repo_map"
    assert "map_generated" not in [event["event"] for event in trace_events]
    assert all(
        REPO_MAP_NAVIGATION_CONTRACT not in prompt
        for prompt in agent.model_client.prompts
    )


def test_branch_a_artifact_failure_rebuilds_without_map_before_model_request(tmp_path):
    agent = _runtime(tmp_path, ["<final>Fallback response.</final>"])
    analysis = _analysis(mentioned_files=("src/auth.py",))
    coordinator = _BranchACoordinator(analysis)
    agent.map_context_coordinator = coordinator
    build_contexts = []
    build_prompts = []
    original_build = agent._build_prompt_and_metadata

    def record_main_build(user_message, *, purpose):
        result = original_build(user_message, purpose=purpose)
        if purpose == "main_model":
            build_contexts.append(agent.current_map_context)
            build_prompts.append(result.prompt)
        return result

    def fail_finalization(task_state, result, repo_map_render):
        coordinator.calls.append(("finalize_prompt_context", repo_map_render))
        assert result is coordinator.prepared_context
        raise OSError("artifact device unavailable")

    coordinator.finalize_prompt_context = fail_finalization
    agent._build_prompt_and_metadata = record_main_build

    assert agent.engine.ask("Explain the target.") == "Fallback response."

    assert coordinator.calls == [
        ("analyze_turn", "Explain the target."),
        ("prepare_specific", analysis),
        ("finalize_prompt_context", ANY),
    ]
    assert build_contexts == [coordinator.prepared_context, None]
    assert REPO_MAP_NAVIGATION_CONTRACT in build_prompts[0]
    assert REPO_MAP_NAVIGATION_CONTRACT not in build_prompts[1]
    assert agent.model_client.prompts == [build_prompts[1]]
    assert agent.current_map_context is None

    trace_events = [
        json.loads(line)
        for line in (agent.current_run_dir / "trace.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert [event["event"] for event in trace_events].count("prompt_built") == 1
    assert "map_generated" not in [event["event"] for event in trace_events]
    failure = next(event for event in trace_events if event["event"] == "map_context_failed")
    assert failure["error_type"] == "OSError"
    assert failure["fallback"] == "without_repo_map"


def test_branch_a_repo_map_omission_rebuilds_without_finalization_or_failure(tmp_path):
    agent = _runtime(tmp_path, ["<final>Fallback response.</final>"])
    analysis = _analysis(mentioned_files=("src/auth.py",))
    coordinator = _BranchACoordinator(analysis)
    agent.map_context_coordinator = coordinator
    build_contexts = []
    build_prompts = []
    original_build = agent._build_prompt_and_metadata

    def force_repo_map_omission(user_message, *, purpose):
        result = original_build(user_message, purpose=purpose)
        if purpose != "main_model":
            return result

        build_contexts.append(agent.current_map_context)
        build_prompts.append(result.prompt)
        if len(build_contexts) != 1:
            return result

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
        return replace(
            result,
            metadata=metadata,
            repo_map_render=omitted_render,
        )

    agent._build_prompt_and_metadata = force_repo_map_omission

    assert agent.engine.ask("Explain the target.") == "Fallback response."

    assert coordinator.calls == [
        ("analyze_turn", "Explain the target."),
        ("prepare_specific", analysis),
    ]
    assert build_contexts == [coordinator.prepared_context, None]
    assert REPO_MAP_NAVIGATION_CONTRACT in build_prompts[0]
    assert REPO_MAP_NAVIGATION_CONTRACT not in build_prompts[1]
    assert agent.model_client.prompts == [build_prompts[1]]
    assert agent.current_map_context is None

    trace_events = [
        json.loads(line)
        for line in (agent.current_run_dir / "trace.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert "map_context_failed" not in [event["event"] for event in trace_events]
    assert "map_generated" not in [event["event"] for event in trace_events]
    prompt_built = next(event for event in trace_events if event["event"] == "prompt_built")
    assert prompt_built["prompt_metadata"]["map_context"] == {
        "section_rendered": False,
        "contract_rendered": False,
        "fallback_notice_rendered": False,
        "map_body_raw_chars": len("src/auth.py: AuthService"),
        "map_body_rendered_chars": 0,
        "section_rendered_chars": 0,
        "section_rendered_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855",
        "base_prompt_reduction_applied": False,
        "omission_reason": "base_prompt_cannot_fit_with_repo_map_reservation",
    }


@pytest.mark.parametrize("feature_flags, coordinator", [({}, None), ({"map_engine": True}, None)])
def test_without_enabled_coordinator_keeps_the_existing_main_model_flow(
    tmp_path, feature_flags, coordinator
):
    agent = _runtime(
        tmp_path,
        ["<final>Unchanged.</final>"],
        feature_flags=feature_flags,
    )
    agent.map_context_coordinator = coordinator

    assert agent.engine.ask("Explain the target.") == "Unchanged."
    assert agent.current_map_context is None
