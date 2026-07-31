import json
import shutil
import subprocess
from pathlib import Path

from pico import Pico, SessionStore, WorkspaceContext
from pico.core.map_selector import build_selector_request
from pico.core.model_request_budget import (
    MODEL_REQUEST_TOKEN_ESTIMATION_METHOD,
    ModelRequestBudget,
)
from pico.features.map_engine.engine import MapEngine
from pico.features.map_engine.models import PromptAnalysis
from pico.testing import ScriptedModelClient


OFFLINE_DEMO_FIXTURE = Path(__file__).parent / "fixtures" / "map_engine" / "offline_demo"


def _git(repo, *args):
    subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=True,
        timeout=5,
    )


def _copy_offline_demo_repo(tmp_path):
    repo = tmp_path / "offline_demo"
    shutil.copytree(OFFLINE_DEMO_FIXTURE, repo)
    _git(repo, "init")
    _git(repo, "config", "user.email", "mapcode@example.test")
    _git(repo, "config", "user.name", "MapCode Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "offline demo fixture")
    return repo


def _analysis(*, branch, mentioned_files=(), effective_symbol_hits=(), path_ident_hits=()):
    return PromptAnalysis(
        branch=branch,
        mentioned_files=mentioned_files,
        mentioned_idents=effective_symbol_hits + path_ident_hits,
        effective_symbol_hits=effective_symbol_hits,
        path_ident_hits=path_ident_hits,
        path_ident_hit_files={ident: () for ident in path_ident_hits},
    )


class _RecordingBudget:
    def __init__(self, budget, selector_prompt):
        self._budget = budget
        self.selector_prompt = selector_prompt
        self.checked_prompts = []

    def __getattr__(self, name):
        return getattr(self._budget, name)

    def request_over_budget(self, text):
        self.checked_prompts.append(text)
        return text == self.selector_prompt


class _RecordingCoordinator:
    def __init__(self, coordinator, analysis):
        self._coordinator = coordinator
        self.analysis = analysis
        self.broad_result = None
        self.selector_catalog = None
        self.selector_catalog_broad = None
        self.decision = None
        self.prepared_context = None
        self.calls = []

    def __getattr__(self, name):
        return getattr(self._coordinator, name)

    def analyze_turn(self, task_state, user_message):
        self.calls.append("analyze_turn")
        self._coordinator.analyze_turn(task_state, user_message)
        return self.analysis

    def prepare_specific(self, task_state, analysis):
        self.calls.append("prepare_specific")
        return self._coordinator.prepare_specific(task_state, analysis)

    def prepare_broad(self, task_state, analysis):
        self.calls.append("prepare_broad")
        self.broad_result = self._coordinator.prepare_broad(task_state, analysis)
        return self.broad_result

    def build_selector_catalog(self, task_state, broad_result):
        self.calls.append("build_selector_catalog")
        self.selector_catalog_broad = broad_result
        self.selector_catalog = self._coordinator.build_selector_catalog(
            task_state,
            broad_result,
        )
        return self.selector_catalog

    def prepare_fuzzy(self, task_state, broad_result, decision):
        self.calls.append("prepare_fuzzy")
        self.decision = decision
        self.prepared_context = self._coordinator.prepare_fuzzy(
            task_state,
            broad_result,
            decision,
        )
        return self.prepared_context


class _RoleRecordingModelClient(ScriptedModelClient):
    def __init__(self, outputs):
        super().__init__(outputs)
        self.calls = []

    def complete(self, prompt, max_new_tokens, **kwargs):
        self.calls.append((prompt, max_new_tokens, dict(kwargs)))
        return super().complete(prompt, max_new_tokens, **kwargs)


def _agent(repo, outputs):
    return Pico(
        model_client=ScriptedModelClient(outputs),
        workspace=WorkspaceContext.build(repo),
        session_store=SessionStore(repo / ".pico" / "sessions"),
        approval_policy="auto",
        feature_flags={"map_engine": True},
    )


def test_fuzzy_selector_budget_fallback_reuses_broad_snapshot_without_selector_call(
    tmp_path,
):
    repo = _copy_offline_demo_repo(tmp_path)
    analysis = _analysis(branch="fuzzy")
    expected_engine = MapEngine(repo)
    expected_engine.ensure_index()
    expected_broad = expected_engine.generate_broad(analysis)
    expected_catalog = expected_engine.build_selector_catalog()
    expected_request = build_selector_request(
        "Explain the repository architecture.",
        expected_broad,
        expected_catalog,
    )
    agent = _agent(repo, ["<final>Broad fallback is ready.</final>"])
    coordinator = _RecordingCoordinator(agent.map_context_coordinator, analysis)
    agent.map_context_coordinator = coordinator
    agent.model_request_budget = _RecordingBudget(
        ModelRequestBudget(
            provider="test",
            model="test-model",
            model_input_budget_tokens=32_768,
            prompt_safety_margin_tokens=1_024,
            estimation_method=MODEL_REQUEST_TOKEN_ESTIMATION_METHOD,
            source="explicit",
        ),
        expected_request.system_prompt + expected_request.user_prompt,
    )

    events = list(agent.engine.run_turn("Explain the repository architecture."))

    assert coordinator.calls == [
        "analyze_turn",
        "prepare_broad",
        "build_selector_catalog",
        "prepare_fuzzy",
    ]
    assert coordinator.selector_catalog_broad is coordinator.broad_result
    assert (
        coordinator.broad_result.evidence.index_snapshot_id
        == coordinator.selector_catalog.index_snapshot_id
    )
    assert coordinator.decision.selector_result is None
    assert coordinator.decision.fallback_reason == "selector_request_over_budget"
    assert coordinator.prepared_context.active_result is coordinator.broad_result
    assert agent.model_request_budget.checked_prompts[0] == (
        expected_request.system_prompt + expected_request.user_prompt
    )
    assert agent.current_task_state.selector_model_calls == 0
    assert agent.current_task_state.map_context_summary["selector_model_calls"] == 0
    assert [event["type"] for event in events].index("broad_ready") < [
        event["type"] for event in events
    ].index("model_requested")
    broad_ready = next(event for event in events if event["type"] == "broad_ready")
    assert broad_ready["payload"]["branch"] == "fuzzy"
    assert broad_ready["payload"]["map_budget_tokens"] == 8_192
    assert "evidence_artifact_path" not in broad_ready["payload"]
    trace_events = [
        json.loads(line)["event"]
        for line in (agent.current_run_dir / "trace.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert "map_selector_requested" not in trace_events
    assert agent.model_client.prompts and len(agent.model_client.prompts) == 1


def test_branch_a_signal_does_not_prepare_broad_or_selector_catalog(tmp_path):
    repo = _copy_offline_demo_repo(tmp_path)
    agent = _agent(repo, ["<final>Focused map is ready.</final>"])
    coordinator = _RecordingCoordinator(
        agent.map_context_coordinator,
        _analysis(branch="specific", mentioned_files=("pkg/auth.py",)),
    )
    agent.map_context_coordinator = coordinator

    events = list(agent.engine.run_turn("Explain pkg/auth.py."))

    assert coordinator.calls == ["analyze_turn", "prepare_specific"]
    assert "broad_ready" not in [event["type"] for event in events]
    assert agent.current_task_state.selector_model_calls == 0


def test_fuzzy_selector_uses_separate_provider_roles_and_traces_before_main_model(
    tmp_path,
):
    repo = _copy_offline_demo_repo(tmp_path)
    model_client = _RoleRecordingModelClient(
        [
            json.dumps(
                {
                    "suggested_files": ["pkg/service.py"],
                    "reasoning": "Service code is relevant.",
                }
            ),
            "<final>Selector call completed.</final>",
        ]
    )
    agent = Pico(
        model_client=model_client,
        workspace=WorkspaceContext.build(repo),
        session_store=SessionStore(repo / ".pico" / "sessions"),
        approval_policy="auto",
        feature_flags={"map_engine": True},
    )
    coordinator = _RecordingCoordinator(agent.map_context_coordinator, _analysis(branch="fuzzy"))
    agent.map_context_coordinator = coordinator

    events = list(agent.engine.run_turn("Explain the repository architecture."))

    expected_request = build_selector_request(
        "Explain the repository architecture.",
        coordinator.broad_result,
        coordinator.selector_catalog,
    )
    assert coordinator.calls == [
        "analyze_turn",
        "prepare_broad",
        "build_selector_catalog",
    ]
    assert len(model_client.calls) == 2
    selector_call, main_call = model_client.calls
    assert selector_call == (
        expected_request.user_prompt,
        agent.max_new_tokens,
        {"system_prompt": expected_request.system_prompt},
    )
    assert "system_prompt" not in main_call[2]
    assert agent.current_task_state.attempts == 1
    assert agent.current_task_state.main_model_calls == 1
    assert agent.current_task_state.selector_model_calls == 1
    assert [event["type"] for event in events].index("broad_ready") < [
        event["type"] for event in events
    ].index("model_requested")

    trace_rows = [
        json.loads(line)
        for line in (agent.current_run_dir / "trace.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    selector_trace_index = next(
        index
        for index, row in enumerate(trace_rows)
        if row["event"] == "map_selector_requested"
    )
    model_requested_index = next(
        index
        for index, row in enumerate(trace_rows)
        if row["event"] == "model_requested"
    )
    assert selector_trace_index < model_requested_index
    assert {
        key: trace_rows[selector_trace_index][key]
        for key in (
            "index_snapshot_id",
            "candidate_path_count",
            "rendered_path_count",
            "input_chars",
            "call_number",
        )
    } == {
        "index_snapshot_id": coordinator.broad_result.evidence.index_snapshot_id,
        "candidate_path_count": len(coordinator.selector_catalog.candidate_paths),
        "rendered_path_count": len(coordinator.selector_catalog.rendered_paths),
        "input_chars": len(
            expected_request.system_prompt + expected_request.user_prompt
        ),
        "call_number": 1,
    }
