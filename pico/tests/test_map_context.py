import json
from pathlib import Path

from pico.core.map_context import MapContextCoordinator
from pico.core.map_context_prompt import (
    RepoMapSectionRender,
    hash_repo_map_section_text,
)
from pico.core.map_selector import SelectionDecision, SelectorResult
from pico.core.model_request_budget import ModelRequestBudget
from pico.core.runtime import Pico
from pico.core.session_store import SessionStore
from pico.core.task_state import TaskState
from pico.core.workspace import WorkspaceContext
from pico.features.map_engine.engine import MapEngine
from pico.features.map_engine.models import (
    CacheEvidence,
    IndexStatus,
    MapContextEvidence,
    MapResult,
    PromptAnalysis,
    RankContributorEvidence,
    RankingEvidence,
    RenderedFileEvidence,
    RenderingEvidence,
    SelectorCandidateCatalog,
)
from pico.testing import ScriptedModelClient


def _workspace(tmp_path: Path):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return WorkspaceContext.build(tmp_path)


def _runtime(tmp_path: Path, **kwargs) -> Pico:
    return Pico(
        model_client=ScriptedModelClient([]),
        workspace=_workspace(tmp_path),
        session_store=SessionStore(tmp_path / ".pico" / "sessions"),
        approval_policy="auto",
        **kwargs,
    )


def test_runtime_starts_with_map_engine_disabled_and_no_current_map(tmp_path):
    agent = _runtime(tmp_path)

    assert agent.feature_enabled("map_engine") is False
    assert agent.map_engine is None
    assert agent.map_context_coordinator is None
    assert agent.current_map_context is None
    assert isinstance(agent.model_request_budget, ModelRequestBudget)


def test_runtime_enabled_map_engine_assembles_objects_without_eager_index(
    tmp_path,
    monkeypatch,
):
    def fail_if_indexed(self):
        raise AssertionError("runtime startup must not build a MapEngine index")

    monkeypatch.setattr(MapEngine, "ensure_index", fail_if_indexed)

    agent = _runtime(tmp_path, feature_flags={"map_engine": True})

    assert agent.feature_enabled("map_engine") is True
    assert isinstance(agent.map_engine, MapEngine)
    assert isinstance(agent.map_context_coordinator, MapContextCoordinator)
    assert agent.map_context_coordinator.runtime is agent
    assert agent.map_context_coordinator.map_engine is agent.map_engine
    assert agent.map_context_coordinator.run_store is agent.run_store
    assert agent.current_map_context is None
    assert getattr(agent.map_engine, "_symbol_index") is None


def test_coordinator_analyzes_turn_and_emits_index_and_path_ident_trace(tmp_path):
    agent = _runtime(tmp_path)
    task_state = _start_map_run(agent)
    fake_engine = _FakeMapEngine()
    coordinator = MapContextCoordinator(agent, fake_engine, agent.run_store)

    analysis = coordinator.analyze_turn(task_state, "Explain PICO Runtime")

    assert analysis is fake_engine.specific_analysis
    assert fake_engine.calls == [
        ("ensure_index",),
        ("analyze", "Explain PICO Runtime"),
    ]
    events = _trace_events(agent, task_state)
    index_event = _event(events, "map_index_status")
    analyzed_event = _event(events, "map_prompt_analyzed")
    assert index_event["index_snapshot_id"] == "sha256:adapter"
    assert index_event["cache_status"]["read_status"] == "hit"
    assert index_event["file_count"] == 2
    assert analyzed_event["branch"] == "specific"
    assert analyzed_event["path_ident_hits"] == ["PICO"]
    assert analyzed_event["path_ident_hit_files"] == {
        "PICO": ["pico/core/runtime.py", "pico/core/session.py"],
    }


def test_coordinator_prepares_specific_context_and_ranking_trace(tmp_path):
    agent = _runtime(tmp_path)
    task_state = _start_map_run(agent)
    fake_engine = _FakeMapEngine()
    coordinator = MapContextCoordinator(agent, fake_engine, agent.run_store)

    context = coordinator.prepare_specific(task_state, fake_engine.specific_analysis)

    assert fake_engine.calls == [
        ("generate_focused", ("pico/core/runtime.py",)),
    ]
    assert context.map_context_id.startswith("mapctx_")
    assert context.branch == "specific"
    assert context.stage == "execution"
    assert context.active_result is fake_engine.focused_result
    assert context.broad_result is None
    assert context.selection_decision is None
    assert context.selector_model_calls == 0
    assert context.prompt_injection is None
    assert task_state.map_context_summary == {
        "enabled": True,
        "map_context_id": context.map_context_id,
        "branch": "specific",
        "stage": "execution",
        "focus_fnames": ["pico/core/runtime.py"],
        "rendered_files": ["pico/core/runtime.py"],
        "index_snapshot_id": "sha256:adapter",
        "selector_model_calls": 0,
        "repo_map_artifact_path": "",
        "evidence_artifact_path": "",
    }
    events = _trace_events(agent, task_state)
    ranked_event = _event(events, "map_context_ranked")
    selected_event = _event(events, "map_context_selected")
    assert ranked_event["stage"] == "focused"
    assert ranked_event["algorithm"] == "personalized_pagerank"
    assert ranked_event["focus_personalization_files"] == ["pico/core/runtime.py"]
    assert ranked_event["path_personalization_files"] == ["pico/core/session.py"]
    assert ranked_event["top_rank_contributors"] == [
        {
            "path": "pico/core/runtime.py",
            "identifier": "Runtime",
            "weight_multiplier": 75.0,
            "weight_reason_codes": [
                "prompt_ident_boost",
                "structured_ident_boost",
                "focus_outbound_boost",
            ],
        }
    ]
    assert selected_event["rendered_files"] == ["pico/core/runtime.py"]
    assert selected_event["map_budget_tokens"] == 4096
    assert selected_event["omission_reason"] is None


def test_coordinator_reuses_snapshot_for_broad_catalog_and_fuzzy_context(tmp_path):
    agent = _runtime(tmp_path)
    task_state = _start_map_run(agent)
    fake_engine = _FakeMapEngine()
    coordinator = MapContextCoordinator(agent, fake_engine, agent.run_store)

    broad = coordinator.prepare_broad(task_state, fake_engine.fuzzy_analysis)
    catalog = coordinator.build_selector_catalog(task_state)
    task_state.record_selector_model_call()
    decision = SelectionDecision.from_single_choice(_selector_result(), "接受全部建议")
    context = coordinator.prepare_fuzzy(task_state, broad, decision)

    assert broad is fake_engine.broad_result
    assert catalog is fake_engine.selector_catalog
    assert context.branch == "fuzzy"
    assert context.stage == "execution"
    assert context.broad_result is broad
    assert context.active_result is fake_engine.focused_result
    assert context.selection_decision is decision
    assert context.selector_model_calls == 1
    assert context.active_result.evidence.index_snapshot_id == catalog.index_snapshot_id
    assert fake_engine.calls == [
        ("generate_broad",),
        ("build_selector_catalog",),
        ("generate_focused", ("pico/core/runtime.py",)),
    ]


def test_coordinator_fuzzy_broad_fallback_reuses_broad_result_without_selector_call(
    tmp_path,
):
    agent = _runtime(tmp_path)
    task_state = _start_map_run(agent)
    fake_engine = _FakeMapEngine()
    coordinator = MapContextCoordinator(agent, fake_engine, agent.run_store)
    decision = SelectionDecision.broad_fallback("selector_request_over_budget")

    context = coordinator.prepare_fuzzy(task_state, fake_engine.broad_result, decision)

    assert context.branch == "fuzzy"
    assert context.stage == "fallback"
    assert context.active_result is fake_engine.broad_result
    assert context.broad_result is fake_engine.broad_result
    assert context.selector_model_calls == 0
    assert fake_engine.calls == []


def test_coordinator_finalizes_prompt_context_and_writes_artifacts(tmp_path):
    agent = _runtime(tmp_path)
    task_state = _start_map_run(agent)
    fake_engine = _FakeMapEngine()
    coordinator = MapContextCoordinator(agent, fake_engine, agent.run_store)
    prepared = coordinator.prepare_specific(task_state, fake_engine.specific_analysis)
    render = _repo_map_render("[repo_map]\npico/core/runtime.py:\n  class Runtime\n")

    finalized = coordinator.finalize_prompt_context(task_state, prepared, render)

    assert finalized.map_context_id == prepared.map_context_id
    assert finalized.prompt_injection is not None
    assert finalized.repo_map_artifact_path.endswith("repo-map-001.txt")
    assert finalized.evidence_artifact_path.endswith("map-evidence-001.json")
    repo_map_path = tmp_path / finalized.repo_map_artifact_path
    evidence_path = tmp_path / finalized.evidence_artifact_path
    assert repo_map_path.read_text(encoding="utf-8") == render.section_text
    evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence_payload["schema_version"] == "mapcode.map-evidence.v1"
    assert evidence_payload["map_context_id"] == prepared.map_context_id
    assert evidence_payload["repo_map_artifact_path"] == finalized.repo_map_artifact_path
    assert "evidence_artifact_path" not in evidence_payload
    assert "repo_map_text" not in evidence_payload["active_result"]
    assert evidence_payload["prompt_injection"]["section_rendered_hash"] == (
        render.section_rendered_hash
    )
    assert task_state.map_context_summary["repo_map_artifact_path"] == (
        finalized.repo_map_artifact_path
    )
    assert task_state.map_context_summary["evidence_artifact_path"] == (
        finalized.evidence_artifact_path
    )
    generated_event = _event(_trace_events(agent, task_state), "map_generated")
    assert generated_event["artifact_paths"] == [
        finalized.repo_map_artifact_path,
        finalized.evidence_artifact_path,
    ]
    assert generated_event["section_rendered_hash"] == render.section_rendered_hash


def _start_map_run(agent: Pico) -> TaskState:
    task_state = TaskState.create(
        run_id="run_map_context",
        task_id="task_map_context",
        user_request="Explain PICO Runtime",
    )
    agent.current_task_state = task_state
    agent.current_turn_id = task_state.task_id
    agent.current_run_id = task_state.run_id
    agent.current_run_dir = agent.run_store.start_run(task_state)
    return task_state


def _trace_events(agent: Pico, task_state: TaskState) -> list[dict]:
    return [
        json.loads(line)
        for line in agent.run_store.trace_path(task_state).read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def _event(events: list[dict], event_name: str) -> dict:
    matches = [event for event in events if event["event"] == event_name]
    assert len(matches) == 1
    return matches[0]


def _selector_result() -> SelectorResult:
    return SelectorResult(
        suggested_files=("pico/core/runtime.py",),
        invalid_files=(),
        excess_files=(),
        reasoning="Runtime is the best focus.",
        parse_error=None,
    )


def _repo_map_render(section_text: str) -> RepoMapSectionRender:
    return RepoMapSectionRender(
        section_text=section_text,
        section_rendered=True,
        contract_rendered=True,
        fallback_notice_rendered=False,
        map_body_raw_chars=128,
        map_body_rendered_chars=64,
        section_rendered_chars=len(section_text),
        section_rendered_hash=hash_repo_map_section_text(section_text),
        base_prompt_reduction_applied=False,
        omission_reason=None,
    )


def _analysis(branch: str) -> PromptAnalysis:
    return PromptAnalysis(
        branch=branch,
        mentioned_files=("pico/core/runtime.py",) if branch == "specific" else (),
        mentioned_idents=("PICO", "Runtime"),
        effective_symbol_hits=("Runtime",) if branch == "specific" else (),
        path_ident_hits=("PICO",) if branch == "specific" else (),
        path_ident_hit_files={
            "PICO": ("pico/core/runtime.py", "pico/core/session.py"),
        }
        if branch == "specific"
        else {},
    )


def _cache() -> CacheEvidence:
    return CacheEvidence(
        read_status="hit",
        write_status="not_needed",
        reused_files=("pico/core/runtime.py",),
        parsed_files=(),
        skipped_files=(),
    )


def _index_status() -> IndexStatus:
    return IndexStatus(
        index_snapshot_id="sha256:adapter",
        cache_status=_cache(),
        file_count=2,
        definition_count=4,
        reference_count=3,
    )


def _ranking(
    *,
    focus_fnames: tuple[str, ...],
    path_personalization_files: tuple[str, ...],
) -> RankingEvidence:
    return RankingEvidence(
        policy_version="mapcode-pagerank-v1",
        algorithm="personalized_pagerank" if focus_fnames else "pagerank",
        focus_fnames=focus_fnames,
        ident_boost_inputs=("PICO", "Runtime"),
        focus_personalization_files=focus_fnames,
        path_personalization_files=path_personalization_files,
        personalization_files=focus_fnames + path_personalization_files,
        top_ranked_files=("pico/core/runtime.py",),
    )


def _rendering(target_tokens: int) -> RenderingEvidence:
    return RenderingEvidence(
        target_tokens=target_tokens,
        target_chars=target_tokens * 4,
        used_chars=512,
        estimated_tokens=128,
        budget_reduction_applied=False,
        focus_truncated=False,
    )


def _rendered_file() -> RenderedFileEvidence:
    contributor = RankContributorEvidence(
        source_path="pico/core/runtime.py",
        identifier="Runtime",
        weighted_edge=12.5,
        weight_multiplier=75.0,
        weight_reason_codes=(
            "prompt_ident_boost",
            "structured_ident_boost",
            "focus_outbound_boost",
        ),
    )
    return RenderedFileEvidence(
        path="pico/core/runtime.py",
        node_pagerank=0.25,
        pagerank_norm=1.0,
        definition_rank_sum=42.0,
        render_rank=1,
        reason_codes=("top_ranked",),
        prompt_symbol_hits=("Runtime",),
        prompt_path_ident_hits=("PICO",),
        rendered_symbols=("Runtime",),
        top_rank_contributors=(contributor,),
    )


def _map_result(
    *,
    mode: str,
    branch: str,
    focus_fnames: tuple[str, ...],
    target_tokens: int,
) -> MapResult:
    analysis = _analysis(branch)
    evidence = MapContextEvidence(
        schema_version="mapcode.map-engine.v1",
        index_snapshot_id="sha256:adapter",
        analysis=analysis,
        ranking=_ranking(
            focus_fnames=focus_fnames,
            path_personalization_files=("pico/core/session.py",)
            if focus_fnames
            else (),
        ),
        rendering=_rendering(target_tokens),
        rendered_files=(_rendered_file(),),
        omitted_files=(),
        cache_status=_cache(),
        duration_ms=7,
    )
    return MapResult(
        mode=mode,
        repo_map_text="pico/core/runtime.py:\n  class Runtime",
        focus_fnames=focus_fnames,
        rendered_files=("pico/core/runtime.py",),
        rendered_symbols=("Runtime",),
        evidence=evidence,
    )


class _FakeMapEngine:
    def __init__(self) -> None:
        self.calls = []
        self.specific_analysis = _analysis("specific")
        self.fuzzy_analysis = _analysis("fuzzy")
        self.focused_result = _map_result(
            mode="focused",
            branch="specific",
            focus_fnames=("pico/core/runtime.py",),
            target_tokens=4096,
        )
        self.broad_result = _map_result(
            mode="broad",
            branch="fuzzy",
            focus_fnames=(),
            target_tokens=8192,
        )
        self.selector_catalog = SelectorCandidateCatalog(
            index_snapshot_id="sha256:adapter",
            candidate_paths=("pico/core/runtime.py", "pico/core/session.py"),
            rendered_paths=("pico/core/runtime.py",),
            rendered_text="pico/core/runtime.py:\n  class Runtime",
            file_count=2,
            definition_count=4,
            rendered_file_count=1,
            rendered_definition_count=1,
            estimated_tokens=12,
            truncated=True,
        )

    def ensure_index(self):
        self.calls.append(("ensure_index",))
        return _index_status()

    def analyze(self, prompt: str):
        self.calls.append(("analyze", prompt))
        return self.specific_analysis

    def generate_focused(self, analysis: PromptAnalysis, focus_fnames: tuple[str, ...]):
        self.calls.append(("generate_focused", focus_fnames))
        return self.focused_result

    def generate_broad(self, analysis: PromptAnalysis):
        self.calls.append(("generate_broad",))
        return self.broad_result

    def build_selector_catalog(self):
        self.calls.append(("build_selector_catalog",))
        return self.selector_catalog
