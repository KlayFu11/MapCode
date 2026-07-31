from dataclasses import FrozenInstanceError

import pytest

from pico.core.map_context import (
    MapContextResult,
    MapEvidenceArtifact,
    MapResultEvidence,
)
from pico.core.map_selector import SelectionDecision, SelectorResult
from pico.features.map_engine.models import (
    CacheEvidence,
    MapContextEvidence,
    MapResult,
    PromptAnalysis,
    RankingEvidence,
    RenderingEvidence,
)


def _analysis(branch: str = "specific") -> PromptAnalysis:
    return PromptAnalysis(
        branch=branch,
        mentioned_files=("pico/core/runtime.py",) if branch == "specific" else (),
        mentioned_idents=("Runtime",),
        effective_symbol_hits=("Runtime",) if branch == "specific" else (),
        path_ident_hits=(),
        path_ident_hit_files={},
    )


def _ranking(focus_fnames: tuple[str, ...]) -> RankingEvidence:
    return RankingEvidence(
        policy_version="mapcode-pagerank-v1",
        algorithm="personalized_pagerank" if focus_fnames else "pagerank",
        focus_fnames=focus_fnames,
        ident_boost_inputs=("Runtime",),
        focus_personalization_files=focus_fnames,
        path_personalization_files=(),
        personalization_files=focus_fnames,
        top_ranked_files=("pico/core/runtime.py",),
    )


def _rendering() -> RenderingEvidence:
    return RenderingEvidence(
        target_tokens=4_096,
        target_chars=16_384,
        used_chars=512,
        estimated_tokens=128,
        budget_reduction_applied=False,
        focus_truncated=False,
    )


def _cache() -> CacheEvidence:
    return CacheEvidence(
        read_status="hit",
        write_status="not_needed",
        reused_files=("pico/core/runtime.py",),
        parsed_files=(),
        skipped_files=(),
    )


def _map_result(
    mode: str = "focused",
    branch: str = "specific",
    snapshot: str = "sha256:abc123",
    focus_fnames: tuple[str, ...] = ("pico/core/runtime.py",),
) -> MapResult:
    evidence = MapContextEvidence(
        schema_version="mapcode.map-engine.v1",
        index_snapshot_id=snapshot,
        analysis=_analysis(branch),
        ranking=_ranking(focus_fnames),
        rendering=_rendering(),
        rendered_files=(),
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


def _selector_result() -> SelectorResult:
    return SelectorResult(
        suggested_files=("pico/core/runtime.py",),
        invalid_files=(),
        excess_files=(),
        reasoning="Runtime is the best focus.",
        parse_error=None,
    )


def test_map_result_evidence_copies_structured_fields_without_repo_map_text():
    result = _map_result()
    evidence = MapResultEvidence.from_map_result(result)

    assert evidence.mode == "focused"
    assert evidence.focus_fnames == ("pico/core/runtime.py",)
    assert evidence.rendered_files == ("pico/core/runtime.py",)
    assert evidence.rendered_symbols == ("Runtime",)
    assert evidence.evidence == result.evidence
    assert not hasattr(evidence, "repo_map_text")


def test_branch_a_prepared_map_context_has_no_selector_or_artifacts():
    active = _map_result()
    context = MapContextResult(
        map_context_id="mapctx_abc",
        branch="specific",
        stage="execution",
        active_result=active,
        broad_result=None,
        selection_decision=None,
        selector_model_calls=0,
        prompt_injection=None,
        repo_map_artifact_path=None,
        evidence_artifact_path=None,
    )

    assert context.branch == "specific"
    assert context.stage == "execution"
    assert context.active_result == active
    assert context.broad_result is None
    assert context.selection_decision is None

    with pytest.raises(FrozenInstanceError):
        context.stage = "fallback"


def test_branch_b_confirmed_context_keeps_broad_result_and_selector_snapshot():
    broad = _map_result(
        mode="broad",
        branch="fuzzy",
        focus_fnames=(),
    )
    active = _map_result(branch="fuzzy")
    decision = SelectionDecision.from_single_choice(_selector_result(), "接受全部建议")

    context = MapContextResult(
        map_context_id="mapctx_abc",
        branch="fuzzy",
        stage="execution",
        active_result=active,
        broad_result=broad,
        selection_decision=decision,
        selector_model_calls=1,
        prompt_injection=None,
        repo_map_artifact_path=None,
        evidence_artifact_path=None,
    )

    assert context.broad_result == broad
    assert context.selection_decision == decision
    assert context.selector_model_calls == 1


@pytest.mark.parametrize(
    ("stage", "active", "match"),
    (
        (
            "fallback",
            _map_result(branch="fuzzy"),
            "confirmed selection must use execution stage",
        ),
        (
            "execution",
            _map_result(mode="broad", branch="fuzzy", focus_fnames=()),
            "confirmed selection must use focused active_result",
        ),
        (
            "execution",
            _map_result(
                branch="fuzzy",
                focus_fnames=("pico/core/task_state.py",),
            ),
            "focused active_result must match confirmed_files",
        ),
    ),
)
def test_branch_b_confirmed_context_requires_focused_execution_state(
    stage, active, match
):
    broad = _map_result(
        mode="broad",
        branch="fuzzy",
        focus_fnames=(),
    )
    decision = SelectionDecision.from_single_choice(
        _selector_result(), "接受全部建议"
    )

    with pytest.raises(ValueError, match=match):
        MapContextResult(
            map_context_id="mapctx_confirmed",
            branch="fuzzy",
            stage=stage,
            active_result=active,
            broad_result=broad,
            selection_decision=decision,
            selector_model_calls=1,
            prompt_injection=None,
            repo_map_artifact_path=None,
            evidence_artifact_path=None,
        )


def test_branch_b_broad_fallback_reuses_active_broad_result():
    broad = _map_result(
        mode="broad",
        branch="fuzzy",
        focus_fnames=(),
    )
    decision = SelectionDecision.broad_fallback("selector_request_over_budget")

    context = MapContextResult(
        map_context_id="mapctx_fallback",
        branch="fuzzy",
        stage="fallback",
        active_result=broad,
        broad_result=broad,
        selection_decision=decision,
        selector_model_calls=0,
        prompt_injection=None,
        repo_map_artifact_path=None,
        evidence_artifact_path=None,
    )

    assert context.active_result.mode == "broad"
    assert context.broad_result == context.active_result
    assert context.selection_decision.fallback_mode == "broad_map"


def test_map_context_requires_same_snapshot_for_branch_b_results():
    broad = _map_result(
        mode="broad",
        branch="fuzzy",
        snapshot="sha256:broad",
        focus_fnames=(),
    )
    active = _map_result(branch="fuzzy", snapshot="sha256:focused")
    decision = SelectionDecision.from_single_choice(_selector_result(), "接受全部建议")

    with pytest.raises(ValueError, match="index_snapshot_id"):
        MapContextResult(
            map_context_id="mapctx_mismatch",
            branch="fuzzy",
            stage="execution",
            active_result=active,
            broad_result=broad,
            selection_decision=decision,
            selector_model_calls=1,
            prompt_injection=None,
            repo_map_artifact_path=None,
            evidence_artifact_path=None,
        )


def test_finalized_map_context_requires_all_prompt_and_artifact_fields():
    active = _map_result()
    prompt_injection = object()

    prepared = MapContextResult(
        map_context_id="mapctx_final",
        branch="specific",
        stage="execution",
        active_result=active,
        broad_result=None,
        selection_decision=None,
        selector_model_calls=0,
        prompt_injection=None,
        repo_map_artifact_path=None,
        evidence_artifact_path=None,
    )

    finalized = MapContextResult(
        map_context_id="mapctx_final",
        branch="specific",
        stage="execution",
        active_result=active,
        broad_result=None,
        selection_decision=None,
        selector_model_calls=0,
        prompt_injection=prompt_injection,
        repo_map_artifact_path="repo-map-001.txt",
        evidence_artifact_path="map-evidence-001.json",
    )

    assert prepared is not finalized
    assert prepared.map_context_id == finalized.map_context_id
    assert prepared.prompt_injection is None
    assert prepared.repo_map_artifact_path is None
    assert prepared.evidence_artifact_path is None
    assert finalized.prompt_injection is prompt_injection
    assert finalized.repo_map_artifact_path == "repo-map-001.txt"
    assert finalized.evidence_artifact_path == "map-evidence-001.json"

    with pytest.raises(FrozenInstanceError):
        finalized.map_context_id = "mapctx_changed"


def test_map_evidence_artifact_is_run_level_envelope_without_self_path():
    active = _map_result()
    result_evidence = MapResultEvidence.from_map_result(active)
    prompt_injection = object()
    artifact = MapEvidenceArtifact(
        schema_version="mapcode.map-evidence.v1",
        map_context_id="mapctx_final",
        run_id="run_123",
        branch="specific",
        stage="execution",
        index_snapshot_id="sha256:abc123",
        analysis=active.evidence.analysis,
        broad_result=None,
        active_result=result_evidence,
        selection_decision=None,
        prompt_injection=prompt_injection,
        repo_map_artifact_path="repo-map-001.txt",
    )

    assert artifact.run_id == "run_123"
    assert artifact.active_result == result_evidence
    assert artifact.prompt_injection is prompt_injection
    assert not hasattr(artifact, "evidence_artifact_path")
    assert not hasattr(artifact.active_result, "repo_map_text")


@pytest.mark.parametrize(
    ("changes", "match"),
    (
        (
            {"schema_version": "mapcode.map-engine.v1"},
            "schema_version",
        ),
        ({"map_context_id": "invalid"}, "map_context_id"),
        ({"run_id": ""}, "run_id"),
        ({"repo_map_artifact_path": ""}, "repo_map_artifact_path"),
    ),
)
def test_map_evidence_artifact_validates_run_envelope_identity(changes, match):
    active = _map_result()
    values = {
        "schema_version": "mapcode.map-evidence.v1",
        "map_context_id": "mapctx_final",
        "run_id": "run_123",
        "branch": "specific",
        "stage": "execution",
        "index_snapshot_id": "sha256:abc123",
        "analysis": active.evidence.analysis,
        "broad_result": None,
        "active_result": MapResultEvidence.from_map_result(active),
        "selection_decision": None,
        "prompt_injection": object(),
        "repo_map_artifact_path": "repo-map-001.txt",
    }
    values.update(changes)

    with pytest.raises(ValueError, match=match):
        MapEvidenceArtifact(**values)


def test_map_evidence_artifact_validates_branch_b_fallback_identity():
    broad = _map_result(mode="broad", branch="fuzzy", focus_fnames=())
    active = _map_result(branch="fuzzy")
    decision = SelectionDecision.broad_fallback("selector_request_over_budget")
    values = {
        "schema_version": "mapcode.map-evidence.v1",
        "map_context_id": "mapctx_fallback",
        "run_id": "run_123",
        "branch": "fuzzy",
        "stage": "fallback",
        "index_snapshot_id": broad.evidence.index_snapshot_id,
        "analysis": broad.evidence.analysis,
        "broad_result": MapResultEvidence.from_map_result(broad),
        "active_result": MapResultEvidence.from_map_result(active),
        "selection_decision": decision,
        "prompt_injection": object(),
        "repo_map_artifact_path": "repo-map-001.txt",
    }

    with pytest.raises(ValueError, match="active_result must reuse broad_result"):
        MapEvidenceArtifact(**values)
