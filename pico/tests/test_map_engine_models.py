from dataclasses import FrozenInstanceError
from typing import get_args

import pytest

from pico.features.map_engine.models import (
    CacheEvidence,
    DefinitionRecord,
    FileRecord,
    IndexStatus,
    MapContextEvidence,
    MapResult,
    OmittedFileEvidence,
    PromptAnalysis,
    RankContributorEvidence,
    RankingEvidence,
    ReferenceRecord,
    RenderedFileEvidence,
    RenderingEvidence,
    SelectorCandidateCatalog,
)


def test_definition_record_matches_symbol_index_contract():
    record = DefinitionRecord(
        name="JWTAuth",
        path="pico/auth.py",
        line=0,
        kind="class",
    )

    assert record.name == "JWTAuth"
    assert record.path == "pico/auth.py"
    assert record.line == 0
    assert record.kind == "class"


def test_reference_record_matches_symbol_index_contract():
    record = ReferenceRecord(
        name="JWTAuth",
        path="pico/api.py",
        line=12,
    )

    assert record.name == "JWTAuth"
    assert record.path == "pico/api.py"
    assert record.line == 12


def test_file_record_matches_symbol_index_contract():
    record = FileRecord(
        path="pico/auth.py",
        mtime_ns=1_725_000_000,
        size=4_096,
        parser_version="mapcode-python-tags-v1",
        query_version="mapcode-python-query-v1",
        schema_version="mapcode.map-engine.v1",
    )

    assert record.path == "pico/auth.py"
    assert record.mtime_ns == 1_725_000_000
    assert record.size == 4_096
    assert record.parser_version == "mapcode-python-tags-v1"
    assert record.query_version == "mapcode-python-query-v1"
    assert record.schema_version == "mapcode.map-engine.v1"


def test_records_are_immutable_value_objects():
    left = DefinitionRecord(
        name="build_index",
        path="pico/features/map_engine/symbol_index.py",
        line=7,
        kind="function",
    )
    right = DefinitionRecord(
        name="build_index",
        path="pico/features/map_engine/symbol_index.py",
        line=7,
        kind="function",
    )

    assert left == right

    with pytest.raises(FrozenInstanceError):
        left.line = 8


def test_line_fields_are_zero_based():
    definition = DefinitionRecord(
        name="first_symbol",
        path="pico/first.py",
        line=0,
        kind="function",
    )
    reference = ReferenceRecord(
        name="first_symbol",
        path="pico/second.py",
        line=0,
    )

    assert definition.line == 0
    assert reference.line == 0


def test_paths_are_repo_relative_strings():
    definition = DefinitionRecord(
        name="Settings",
        path="pico/config/settings.py",
        line=4,
        kind="class",
    )
    file_record = FileRecord(
        path="pico/config/settings.py",
        mtime_ns=10,
        size=200,
        parser_version="mapcode-python-tags-v1",
        query_version="mapcode-python-query-v1",
        schema_version="mapcode.map-engine.v1",
    )

    assert definition.path == "pico/config/settings.py"
    assert file_record.path == "pico/config/settings.py"
    assert not definition.path.startswith("/")
    assert not file_record.path.startswith("/")


def test_rank_contributor_evidence_tracks_multiplier_audit_fields():
    contributor = RankContributorEvidence(
        source_path="pico/tools/registry.py",
        identifier="ToolRegistry",
        weighted_edge=12.5,
        weight_multiplier=500.0,
        weight_reason_codes=("prompt_ident", "structured_ident", "focus_outbound"),
    )

    assert contributor.source_path == "pico/tools/registry.py"
    assert contributor.identifier == "ToolRegistry"
    assert contributor.weighted_edge == 12.5
    assert contributor.weight_multiplier == 500.0
    assert contributor.weight_reason_codes == (
        "prompt_ident",
        "structured_ident",
        "focus_outbound",
    )


def test_rendered_file_evidence_keeps_file_level_rank_and_path_ident_audit():
    contributor = RankContributorEvidence(
        source_path="pico/core/engine.py",
        identifier="Runtime",
        weighted_edge=3.0,
        weight_multiplier=10.0,
        weight_reason_codes=("prompt_ident",),
    )
    evidence = RenderedFileEvidence(
        path="pico/core/runtime.py",
        node_pagerank=0.25,
        pagerank_norm=1.0,
        definition_rank_sum=42.0,
        render_rank=1,
        reason_codes=("path_ident_match", "top_ranked"),
        prompt_symbol_hits=("Runtime",),
        prompt_path_ident_hits=("Pico", "core"),
        rendered_symbols=("Runtime", "run_turn"),
        top_rank_contributors=(contributor,),
    )

    assert evidence.path == "pico/core/runtime.py"
    assert evidence.render_rank == 1
    assert evidence.prompt_path_ident_hits == ("Pico", "core")
    assert evidence.rendered_symbols == ("Runtime", "run_turn")
    assert evidence.top_rank_contributors == (contributor,)


def test_omitted_file_evidence_keeps_omission_reason_and_rank_audit():
    contributor = RankContributorEvidence(
        source_path="pico/core/context_manager.py",
        identifier="ContextManager",
        weighted_edge=1.5,
        weight_multiplier=1.0,
        weight_reason_codes=(),
    )
    evidence = OmittedFileEvidence(
        path="pico/core/context_manager.py",
        node_pagerank=0.02,
        pagerank_norm=0.08,
        definition_rank_sum=4.0,
        omission_reason="map_budget_exhausted",
        reason_codes=("budget_omitted", "path_ident_match"),
        prompt_symbol_hits=("ContextManager",),
        prompt_path_ident_hits=("context",),
        top_rank_contributors=(contributor,),
    )

    assert evidence.omission_reason == "map_budget_exhausted"
    assert evidence.prompt_path_ident_hits == ("context",)
    assert evidence.top_rank_contributors == (contributor,)


def test_ranking_evidence_separates_focus_and_path_personalization():
    evidence = RankingEvidence(
        policy_version="mapcode-pagerank-v1",
        algorithm="personalized_pagerank",
        focus_fnames=("pico/core/engine.py", "pico/core/runtime.py"),
        ident_boost_inputs=("Engine", "pico"),
        focus_personalization_files=("pico/core/engine.py",),
        path_personalization_files=("pico/core/runtime.py", "pico/tools/registry.py"),
        personalization_files=(
            "pico/core/engine.py",
            "pico/core/runtime.py",
            "pico/tools/registry.py",
        ),
        top_ranked_files=("pico/core/runtime.py", "pico/core/engine.py"),
    )

    assert evidence.focus_fnames == ("pico/core/engine.py", "pico/core/runtime.py")
    assert evidence.focus_personalization_files == ("pico/core/engine.py",)
    assert evidence.path_personalization_files == (
        "pico/core/runtime.py",
        "pico/tools/registry.py",
    )
    assert evidence.personalization_files == (
        "pico/core/engine.py",
        "pico/core/runtime.py",
        "pico/tools/registry.py",
    )


def test_evidence_literal_fields_match_spec_ranges():
    assert get_args(RankingEvidence.__annotations__["algorithm"]) == (
        "pagerank",
        "personalized_pagerank",
        "stable_path_fallback",
    )
    assert get_args(CacheEvidence.__annotations__["read_status"]) == (
        "hit",
        "miss",
        "read_failed",
    )
    assert get_args(CacheEvidence.__annotations__["write_status"]) == (
        "not_needed",
        "written",
        "write_failed",
    )


def test_rendering_evidence_tracks_map_engine_budget_fields():
    evidence = RenderingEvidence(
        target_tokens=4_096,
        target_chars=16_384,
        used_chars=12_345,
        estimated_tokens=3_087,
        budget_reduction_applied=True,
        focus_truncated=False,
    )

    assert evidence.target_tokens == 4_096
    assert evidence.target_chars == 16_384
    assert evidence.used_chars == 12_345
    assert evidence.estimated_tokens == 3_087
    assert evidence.budget_reduction_applied is True
    assert evidence.focus_truncated is False
    assert not hasattr(evidence, "base_prompt_reduction_applied")


def test_cache_evidence_and_index_status_contract():
    cache = CacheEvidence(
        read_status="hit",
        write_status="not_needed",
        reused_files=("pico/core/runtime.py",),
        parsed_files=("pico/core/engine.py",),
        skipped_files=("pico/core/missing.py",),
    )
    status = IndexStatus(
        index_snapshot_id="sha256:abc123",
        cache_status=cache,
        file_count=2,
        definition_count=10,
        reference_count=20,
    )

    assert status.index_snapshot_id == "sha256:abc123"
    assert status.cache_status == cache
    assert status.file_count == 2
    assert status.definition_count == 10
    assert status.reference_count == 20


def test_evidence_records_are_immutable_value_objects():
    evidence = RenderingEvidence(
        target_tokens=8_192,
        target_chars=32_768,
        used_chars=100,
        estimated_tokens=25,
        budget_reduction_applied=False,
        focus_truncated=False,
    )

    with pytest.raises(FrozenInstanceError):
        evidence.used_chars = 200


def test_prompt_analysis_preserves_path_ident_mapping_contract():
    analysis = PromptAnalysis(
        branch="specific",
        mentioned_files=("pico/core/runtime.py",),
        mentioned_idents=("Pico", "Runtime"),
        effective_symbol_hits=("Runtime",),
        path_ident_hits=("Pico", "Runtime"),
        path_ident_hit_files={
            "Pico": ("pico/core/runtime.py", "pico/tools/registry.py"),
            "Runtime": ("pico/core/runtime.py",),
        },
    )

    assert analysis.branch == "specific"
    assert analysis.mentioned_files == ("pico/core/runtime.py",)
    assert analysis.mentioned_idents == ("Pico", "Runtime")
    assert analysis.effective_symbol_hits == ("Runtime",)
    assert tuple(analysis.path_ident_hit_files.keys()) == analysis.path_ident_hits
    assert analysis.path_ident_hit_files["Pico"] == (
        "pico/core/runtime.py",
        "pico/tools/registry.py",
    )

    with pytest.raises(TypeError):
        analysis.path_ident_hit_files["Pico"] = ("pico/core/engine.py",)


def test_prompt_analysis_validates_path_ident_key_order():
    with pytest.raises(ValueError, match="path_ident_hit_files keys"):
        PromptAnalysis(
            branch="specific",
            mentioned_files=(),
            mentioned_idents=("Pico", "Runtime"),
            effective_symbol_hits=(),
            path_ident_hits=("Pico", "Runtime"),
            path_ident_hit_files={
                "Runtime": ("pico/core/runtime.py",),
                "Pico": ("pico/core/runtime.py", "pico/tools/registry.py"),
            },
        )


def test_prompt_analysis_validates_sorted_path_ident_values():
    with pytest.raises(ValueError, match="path_ident_hit_files values"):
        PromptAnalysis(
            branch="specific",
            mentioned_files=(),
            mentioned_idents=("Pico",),
            effective_symbol_hits=(),
            path_ident_hits=("Pico",),
            path_ident_hit_files={
                "Pico": ("pico/tools/registry.py", "pico/core/runtime.py"),
            },
        )


def test_prompt_analysis_literal_fields_match_spec_ranges():
    assert get_args(PromptAnalysis.__annotations__["branch"]) == (
        "specific",
        "fuzzy",
    )


def _analysis() -> PromptAnalysis:
    return PromptAnalysis(
        branch="specific",
        mentioned_files=("pico/core/runtime.py",),
        mentioned_idents=("Runtime", "pico"),
        effective_symbol_hits=("Runtime",),
        path_ident_hits=("pico",),
        path_ident_hit_files={"pico": ("pico/core/runtime.py",)},
    )


def _ranking(focus_fnames: tuple[str, ...]) -> RankingEvidence:
    return RankingEvidence(
        policy_version="mapcode-pagerank-v1",
        algorithm="personalized_pagerank",
        focus_fnames=focus_fnames,
        ident_boost_inputs=("Runtime", "pico"),
        focus_personalization_files=focus_fnames,
        path_personalization_files=("pico/core/runtime.py",),
        personalization_files=focus_fnames,
        top_ranked_files=("pico/core/runtime.py",),
    )


def _rendering() -> RenderingEvidence:
    return RenderingEvidence(
        target_tokens=4_096,
        target_chars=16_384,
        used_chars=1_024,
        estimated_tokens=256,
        budget_reduction_applied=False,
        focus_truncated=False,
    )


def _cache() -> CacheEvidence:
    return CacheEvidence(
        read_status="miss",
        write_status="written",
        reused_files=(),
        parsed_files=("pico/core/runtime.py",),
        skipped_files=(),
    )


def _map_context_evidence(focus_fnames: tuple[str, ...]) -> MapContextEvidence:
    rendered = RenderedFileEvidence(
        path="pico/core/runtime.py",
        node_pagerank=0.3,
        pagerank_norm=1.0,
        definition_rank_sum=10.0,
        render_rank=1,
        reason_codes=("path_ident_match",),
        prompt_symbol_hits=("Runtime",),
        prompt_path_ident_hits=("pico",),
        rendered_symbols=("Runtime",),
        top_rank_contributors=(),
    )

    return MapContextEvidence(
        schema_version="mapcode.map-engine.v1",
        index_snapshot_id="sha256:abc123",
        analysis=_analysis(),
        ranking=_ranking(focus_fnames),
        rendering=_rendering(),
        rendered_files=(rendered,),
        omitted_files=(),
        cache_status=_cache(),
        duration_ms=12,
    )


def test_map_context_evidence_contains_only_map_engine_facts():
    evidence = _map_context_evidence(("pico/core/runtime.py",))

    assert evidence.schema_version == "mapcode.map-engine.v1"
    assert evidence.index_snapshot_id == "sha256:abc123"
    assert evidence.analysis.branch == "specific"
    assert evidence.ranking.algorithm == "personalized_pagerank"
    assert evidence.rendering.target_tokens == 4_096
    assert evidence.rendered_files[0].path == "pico/core/runtime.py"
    assert evidence.omitted_files == ()
    assert evidence.cache_status.read_status == "miss"
    assert evidence.duration_ms == 12
    assert not hasattr(evidence, "selector_result")
    assert not hasattr(evidence, "run_id")
    assert not hasattr(evidence, "artifact_path")
    assert not hasattr(evidence, "terminal_text")


def test_map_result_matches_main_map_engine_output_contract():
    evidence = _map_context_evidence(("pico/core/runtime.py",))
    result = MapResult(
        mode="focused",
        repo_map_text="pico/core/runtime.py:\n  class Runtime",
        focus_fnames=("pico/core/runtime.py",),
        rendered_files=("pico/core/runtime.py",),
        rendered_symbols=("Runtime",),
        evidence=evidence,
    )

    assert result.mode == "focused"
    assert result.evidence.ranking.algorithm == "personalized_pagerank"
    assert result.focus_fnames == result.evidence.ranking.focus_fnames
    assert result.rendered_files == ("pico/core/runtime.py",)
    assert result.rendered_symbols == ("Runtime",)
    assert not hasattr(result, "artifact_path")


def test_map_result_mode_literal_matches_spec_range():
    assert get_args(MapResult.__annotations__["mode"]) == ("broad", "focused")


def test_map_result_requires_focus_fnames_to_match_ranking_evidence():
    evidence = _map_context_evidence(("pico/core/runtime.py",))

    with pytest.raises(ValueError, match="focus_fnames"):
        MapResult(
            mode="focused",
            repo_map_text="pico/core/engine.py:\n  class Engine",
            focus_fnames=("pico/core/engine.py",),
            rendered_files=("pico/core/engine.py",),
            rendered_symbols=("Engine",),
            evidence=evidence,
        )


def _selector_catalog() -> SelectorCandidateCatalog:
    return SelectorCandidateCatalog(
        index_snapshot_id="sha256:abc123",
        candidate_paths=(
            "pico/core/engine.py",
            "pico/core/runtime.py",
            "pico/tools/registry.py",
        ),
        rendered_paths=(
            "pico/core/engine.py",
            "pico/tools/registry.py",
        ),
        rendered_text=(
            "pico/core/engine.py:\n"
            "  class Engine\n"
            "pico/tools/registry.py:\n"
            "  class ToolRegistry"
        ),
        file_count=3,
        definition_count=5,
        rendered_file_count=2,
        rendered_definition_count=2,
        estimated_tokens=20,
        truncated=True,
    )


def test_selector_candidate_catalog_separates_snapshot_and_visible_paths():
    catalog = _selector_catalog()

    assert catalog.index_snapshot_id == "sha256:abc123"
    assert catalog.candidate_paths == (
        "pico/core/engine.py",
        "pico/core/runtime.py",
        "pico/tools/registry.py",
    )
    assert catalog.rendered_paths == (
        "pico/core/engine.py",
        "pico/tools/registry.py",
    )
    assert "pico/core/runtime.py" not in catalog.rendered_text
    assert catalog.file_count == 3
    assert catalog.definition_count == 5
    assert catalog.rendered_file_count == 2
    assert catalog.rendered_definition_count == 2
    assert catalog.estimated_tokens == 20
    assert catalog.truncated is True
    assert not hasattr(catalog, "visible_paths")


def test_selector_candidate_catalog_is_immutable_value_object():
    catalog = _selector_catalog()

    with pytest.raises(FrozenInstanceError):
        catalog.truncated = False


def test_selector_candidate_catalog_validates_candidate_path_order():
    with pytest.raises(ValueError, match="candidate_paths"):
        SelectorCandidateCatalog(
            index_snapshot_id="sha256:abc123",
            candidate_paths=(
                "pico/tools/registry.py",
                "pico/core/engine.py",
            ),
            rendered_paths=("pico/core/engine.py",),
            rendered_text="pico/core/engine.py:\n  class Engine",
            file_count=2,
            definition_count=2,
            rendered_file_count=1,
            rendered_definition_count=1,
            estimated_tokens=12,
            truncated=False,
        )


def test_selector_candidate_catalog_validates_rendered_paths_are_visible_subset():
    with pytest.raises(ValueError, match="rendered_paths"):
        SelectorCandidateCatalog(
            index_snapshot_id="sha256:abc123",
            candidate_paths=("pico/core/engine.py",),
            rendered_paths=("pico/core/runtime.py",),
            rendered_text="pico/core/runtime.py:\n  class Runtime",
            file_count=1,
            definition_count=1,
            rendered_file_count=1,
            rendered_definition_count=1,
            estimated_tokens=10,
            truncated=False,
        )


def test_selector_candidate_catalog_validates_rendered_path_order():
    with pytest.raises(ValueError, match="rendered_paths"):
        SelectorCandidateCatalog(
            index_snapshot_id="sha256:abc123",
            candidate_paths=(
                "pico/core/engine.py",
                "pico/tools/registry.py",
            ),
            rendered_paths=(
                "pico/tools/registry.py",
                "pico/core/engine.py",
            ),
            rendered_text=(
                "pico/tools/registry.py:\n"
                "  class ToolRegistry\n"
                "pico/core/engine.py:\n"
                "  class Engine"
            ),
            file_count=2,
            definition_count=2,
            rendered_file_count=2,
            rendered_definition_count=2,
            estimated_tokens=12,
            truncated=False,
        )
