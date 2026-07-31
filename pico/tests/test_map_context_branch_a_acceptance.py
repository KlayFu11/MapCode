import json
from types import SimpleNamespace
from unittest.mock import ANY

import pytest

from pico import Pico, SessionStore, WorkspaceContext
from pico.features.map_engine.models import PromptAnalysis
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
        self.context = None

    def analyze_turn(self, task_state, user_message):
        self.calls.append(("analyze_turn", user_message))
        return self.analysis

    def prepare_specific(self, task_state, analysis):
        self.calls.append(("prepare_specific", analysis))
        self.context = SimpleNamespace(
            branch="specific",
            stage="execution",
            active_result=SimpleNamespace(
                repo_map_text="src/auth.py: AuthService",
                focus_fnames=analysis.mentioned_files,
            ),
            selection_decision=None,
        )
        return self.context

    def finalize_prompt_context(self, task_state, result, repo_map_render):
        self.calls.append(("finalize_prompt_context", repo_map_render))
        return result


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
    assert build_contexts == [coordinator.context, coordinator.context]
    assert coordinator.context.active_result.focus_fnames == analysis.mentioned_files
    trace_events = [
        json.loads(line)["event"]
        for line in (agent.current_run_dir / "trace.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert trace_events.index("run_started") < trace_events.index("prompt_built")


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
