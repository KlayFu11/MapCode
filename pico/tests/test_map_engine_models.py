from dataclasses import FrozenInstanceError
from typing import get_args

import pytest

from pico.features.map_engine.models import (
    CacheEvidence,
    DefinitionRecord,
    FileRecord,
    IndexStatus,
    OmittedFileEvidence,
    RankContributorEvidence,
    RankingEvidence,
    ReferenceRecord,
    RenderedFileEvidence,
    RenderingEvidence,
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
