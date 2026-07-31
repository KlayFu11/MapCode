import json
from types import SimpleNamespace
from unittest.mock import ANY

import pytest

from pico import Pico, SessionStore, WorkspaceContext
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
    assert agent.current_map_context is coordinator.finalized_context
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
