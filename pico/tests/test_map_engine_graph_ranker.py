from math import sqrt

import pytest

from pico.features.map_engine import graph_ranker
from pico.features.map_engine.config import TOP_RANKED_FILES_LIMIT
from pico.features.map_engine.graph_ranker import (
    build_file_reference_graph,
    stable_path_fallback,
)
from pico.features.map_engine.models import (
    CacheEvidence,
    DefinitionRecord,
    FileRecord,
    ReferenceRecord,
)
from pico.features.map_engine.symbol_index import SymbolIndex


def _file_record(path: str) -> FileRecord:
    return FileRecord(
        path=path,
        mtime_ns=1,
        size=1,
        parser_version="test",
        query_version="test",
        schema_version="test",
    )


def _symbol_index(
    *,
    paths: tuple[str, ...],
    definitions_by_symbol: dict[str, tuple[DefinitionRecord, ...]] | None = None,
    references_by_file: dict[str, tuple[ReferenceRecord, ...]] | None = None,
) -> SymbolIndex:
    definitions_by_symbol = definitions_by_symbol or {}
    references_by_file = references_by_file or {}
    definitions_by_file: dict[str, list[DefinitionRecord]] = {}
    for records in definitions_by_symbol.values():
        for record in records:
            definitions_by_file.setdefault(record.path, []).append(record)

    return SymbolIndex(
        all_defs=frozenset(definitions_by_symbol),
        definitions_by_symbol=definitions_by_symbol,
        definitions_by_file={
            path: tuple(records) for path, records in definitions_by_file.items()
        },
        references_by_file=references_by_file,
        file_records={path: _file_record(path) for path in paths},
        index_snapshot_id="test",
        skipped_files=(),
        cache_status=CacheEvidence(
            read_status="miss",
            write_status="not_needed",
            reused_files=(),
            parsed_files=(),
            skipped_files=(),
        ),
    )


def _definition(name: str, path: str, line: int = 0) -> DefinitionRecord:
    return DefinitionRecord(name=name, path=path, line=line, kind="function")


def _reference(name: str, path: str, line: int = 0) -> ReferenceRecord:
    return ReferenceRecord(name=name, path=path, line=line)


def test_build_file_reference_graph_points_from_referencer_to_definer():
    symbol_index = _symbol_index(
        paths=("app.py", "service.py", "standalone.py"),
        definitions_by_symbol={"Service": (_definition("Service", "service.py"),)},
        references_by_file={"app.py": (_reference("Service", "app.py"),)},
    )

    result = build_file_reference_graph(symbol_index)

    assert result.node_paths == ("app.py", "service.py")
    assert tuple(sorted(result.graph.nodes)) == ("app.py", "service.py")
    assert result.fallback_paths == ("app.py", "service.py", "standalone.py")
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.source_path == "app.py"
    assert edge.target_path == "service.py"
    assert edge.identifier == "Service"
    assert edge.reference_count == 1
    assert edge.weight == 1.0
    assert result.graph.has_edge("app.py", "service.py", key="Service")
    assert result.graph["app.py"]["service.py"]["Service"]["identifier"] == "Service"


def test_build_file_reference_graph_weights_repeated_references_by_sqrt_count():
    symbol_index = _symbol_index(
        paths=("app.py", "helpers.py"),
        definitions_by_symbol={"helper": (_definition("helper", "helpers.py"),)},
        references_by_file={
            "app.py": (
                _reference("helper", "app.py", line=1),
                _reference("helper", "app.py", line=2),
                _reference("helper", "app.py", line=3),
            )
        },
    )

    result = build_file_reference_graph(symbol_index)

    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.reference_count == 3
    assert edge.weight == pytest.approx(sqrt(3))
    assert result.graph["app.py"]["helpers.py"]["helper"]["weight"] == pytest.approx(
        sqrt(3)
    )


def test_build_file_reference_graph_dedupes_definers_and_sorts_multi_targets():
    symbol_index = _symbol_index(
        paths=("consumer.py", "z_config.py", "a_config.py"),
        definitions_by_symbol={
            "Config": (
                _definition("Config", "z_config.py", line=1),
                _definition("Config", "a_config.py", line=2),
                _definition("Config", "a_config.py", line=9),
            )
        },
        references_by_file={"consumer.py": (_reference("Config", "consumer.py"),)},
    )

    result = build_file_reference_graph(symbol_index)

    assert tuple(edge.target_path for edge in result.edges) == (
        "a_config.py",
        "z_config.py",
    )
    assert tuple(edge.identifier for edge in result.edges) == ("Config", "Config")
    assert result.graph.has_edge("consumer.py", "a_config.py", key="Config")
    assert result.graph.has_edge("consumer.py", "z_config.py", key="Config")


def test_build_file_reference_graph_ignores_unknown_references():
    symbol_index = _symbol_index(
        paths=("app.py",),
        references_by_file={"app.py": (_reference("Missing", "app.py"),)},
    )

    result = build_file_reference_graph(symbol_index)

    assert result.edges == ()
    assert result.node_paths == ()
    assert result.graph.number_of_nodes() == 0
    assert result.graph.number_of_edges() == 0
    assert result.fallback_paths == ("app.py",)


def test_build_file_reference_graph_does_not_add_self_loop_for_isolated_definition():
    symbol_index = _symbol_index(
        paths=("models.py",),
        definitions_by_symbol={"Model": (_definition("Model", "models.py"),)},
    )

    result = build_file_reference_graph(symbol_index)

    assert result.edges == ()
    assert result.node_paths == ()
    assert result.graph.number_of_nodes() == 0
    assert result.graph.number_of_edges() == 0
    assert not result.graph.has_edge("models.py", "models.py")
    assert result.fallback_paths == ("models.py",)


def test_stable_path_fallback_sorts_symbol_index_file_records():
    symbol_index = _symbol_index(paths=("zeta.py", "alpha.py", "pkg/beta.py"))

    result = build_file_reference_graph(symbol_index)

    assert stable_path_fallback(symbol_index) == ("alpha.py", "pkg/beta.py", "zeta.py")
    assert result.node_paths == ()
    assert result.graph.number_of_nodes() == 0
    assert result.fallback_paths == ("alpha.py", "pkg/beta.py", "zeta.py")


def _edge_by_identifier(result, identifier: str):
    matches = [
        edge for edge in result.reference_graph.edges if edge.identifier == identifier
    ]
    assert len(matches) == 1
    return matches[0]


def _ranked_file(result, path: str):
    matches = [score for score in result.ranked_files if score.path == path]
    assert len(matches) == 1
    return matches[0]


def test_rank_broad_returns_pagerank_evidence_without_personalization():
    symbol_index = _symbol_index(
        paths=("app.py", "service.py", "util.py"),
        definitions_by_symbol={
            "Service": (_definition("Service", "service.py"),),
            "util": (_definition("util", "util.py"),),
        },
        references_by_file={
            "app.py": (_reference("Service", "app.py"),),
            "service.py": (_reference("util", "service.py"),),
        },
    )

    result = graph_ranker.rank_broad(symbol_index, ident_boost_inputs=("Service",))

    assert result.ranking.algorithm == "pagerank"
    assert result.ranking.focus_fnames == ()
    assert result.ranking.ident_boost_inputs == ("Service",)
    assert result.ranking.focus_personalization_files == ()
    assert result.ranking.path_personalization_files == ()
    assert result.ranking.personalization_files == ()
    assert result.ranking.top_ranked_files == tuple(
        score.path for score in result.ranked_files[:TOP_RANKED_FILES_LIMIT]
    )
    assert all(
        "focus_outbound_boost" not in contributor.weight_reason_codes
        for score in result.ranked_files
        for contributor in score.top_rank_contributors
    )


def test_rank_broad_applies_symbol_multipliers_before_pagerank():
    common_definitions = tuple(
        _definition("common", f"common_{index}.py") for index in range(6)
    )
    symbol_index = _symbol_index(
        paths=(
            "consumer.py",
            "prompt.py",
            "structured.py",
            "private.py",
            *(definition.path for definition in common_definitions),
        ),
        definitions_by_symbol={
            "prompt": (_definition("prompt", "prompt.py"),),
            "structured_ident": (_definition("structured_ident", "structured.py"),),
            "_x": (_definition("_x", "private.py"),),
            "common": common_definitions,
        },
        references_by_file={
            "consumer.py": (
                _reference("prompt", "consumer.py", line=1),
                _reference("structured_ident", "consumer.py", line=2),
                _reference("_x", "consumer.py", line=3),
                _reference("common", "consumer.py", line=4),
                _reference("common", "consumer.py", line=5),
                _reference("common", "consumer.py", line=6),
                _reference("common", "consumer.py", line=7),
            )
        },
    )

    result = graph_ranker.rank_broad(symbol_index, ident_boost_inputs=("prompt",))

    prompt_edge = _edge_by_identifier(result, "prompt")
    structured_edge = _edge_by_identifier(result, "structured_ident")
    private_edge = _edge_by_identifier(result, "_x")
    common_edges = [
        edge for edge in result.reference_graph.edges if edge.identifier == "common"
    ]
    assert prompt_edge.weight == pytest.approx(10.0)
    assert prompt_edge.weight_reason_codes == ("prompt_ident_boost",)
    assert structured_edge.weight == pytest.approx(10.0)
    assert structured_edge.weight_reason_codes == ("structured_ident_boost",)
    assert private_edge.weight == pytest.approx(0.1)
    assert private_edge.weight_reason_codes == ("private_ident_penalty",)
    assert len(common_edges) == 6
    assert {edge.weight_reason_codes for edge in common_edges} == {
        ("common_ident_penalty",)
    }
    assert all(edge.weight == pytest.approx(sqrt(4) * 0.1) for edge in common_edges)


def test_rank_broad_prompt_ident_matching_is_case_sensitive():
    symbol_index = _symbol_index(
        paths=("app.py", "upper.py", "lower.py"),
        definitions_by_symbol={
            "Target": (_definition("Target", "upper.py"),),
            "target": (_definition("target", "lower.py"),),
        },
        references_by_file={
            "app.py": (
                _reference("Target", "app.py", line=1),
                _reference("target", "app.py", line=2),
            )
        },
    )

    result = graph_ranker.rank_broad(symbol_index, ident_boost_inputs=("Target",))

    assert _edge_by_identifier(result, "Target").weight == pytest.approx(10.0)
    assert _edge_by_identifier(result, "Target").weight_reason_codes == (
        "prompt_ident_boost",
    )
    assert _edge_by_identifier(result, "target").weight == pytest.approx(1.0)
    assert _edge_by_identifier(result, "target").weight_reason_codes == ()


def test_rank_broad_computes_definition_group_rank_and_definition_rank_sum():
    symbol_index = _symbol_index(
        paths=("app.py", "alpha.py", "beta.py"),
        definitions_by_symbol={
            "Alpha": (
                _definition("Alpha", "alpha.py", line=1),
                _definition("Alpha", "alpha.py", line=9),
            ),
            "Beta": (_definition("Beta", "beta.py"),),
        },
        references_by_file={
            "app.py": (
                _reference("Alpha", "app.py", line=1),
                _reference("Alpha", "app.py", line=2),
                _reference("Beta", "app.py", line=3),
            )
        },
    )

    result = graph_ranker.rank_broad(symbol_index)

    app_rank = _ranked_file(result, "app.py").node_pagerank
    alpha_share = sqrt(2) / (sqrt(2) + 1)
    beta_share = 1 / (sqrt(2) + 1)
    assert _ranked_file(result, "alpha.py").definition_rank_sum == pytest.approx(
        app_rank * alpha_share
    )
    assert _ranked_file(result, "beta.py").definition_rank_sum == pytest.approx(
        app_rank * beta_share
    )


def test_rank_broad_top_files_follow_node_pagerank_not_definition_rank_sum():
    symbol_index = _symbol_index(
        paths=("source.py", "target.py"),
        definitions_by_symbol={
            "Target": (_definition("Target", "target.py"),),
        },
        references_by_file={
            "source.py": (_reference("Target", "source.py"),),
        },
    )

    result = graph_ranker.rank_broad(symbol_index)

    by_node_pagerank = tuple(
        path
        for path, _rank in sorted(
            (
                (score.path, score.node_pagerank)
                for score in result.ranked_files
            ),
            key=lambda item: (-item[1], item[0]),
        )
    )
    assert tuple(score.path for score in result.ranked_files) == by_node_pagerank
    assert result.ranking.top_ranked_files == by_node_pagerank
    assert _ranked_file(result, "target.py").definition_rank_sum > 0


def test_rank_broad_sorts_definition_records_by_group_rank_then_spec_tiebreakers():
    symbol_index = _symbol_index(
        paths=("source.py", "alpha.py", "beta.py"),
        definitions_by_symbol={
            "Alpha": (
                DefinitionRecord(
                    name="Alpha",
                    path="alpha.py",
                    line=9,
                    kind="class",
                ),
                DefinitionRecord(
                    name="Alpha",
                    path="alpha.py",
                    line=2,
                    kind="function",
                ),
            ),
            "Beta": (_definition("Beta", "beta.py", line=1),),
        },
        references_by_file={
            "source.py": (
                _reference("Alpha", "source.py", line=1),
                _reference("Alpha", "source.py", line=2),
                _reference("Beta", "source.py", line=3),
            )
        },
    )

    result = graph_ranker.rank_broad(symbol_index)

    assert tuple(
        (definition.path, definition.name, definition.line, definition.kind)
        for definition in result.ranked_definitions
    ) == (
        ("alpha.py", "Alpha", 2, "function"),
        ("alpha.py", "Alpha", 9, "class"),
        ("beta.py", "Beta", 1, "function"),
    )


def test_rank_broad_records_top_rank_contributors():
    symbol_index = _symbol_index(
        paths=(
            "a_source.py",
            "b_source.py",
            "c_source.py",
            "d_source.py",
            "target.py",
            "other.py",
        ),
        definitions_by_symbol={
            "target": (_definition("target", "target.py"),),
            "other": (_definition("other", "other.py"),),
        },
        references_by_file={
            "a_source.py": (
                *(_reference("target", "a_source.py", line=i) for i in range(16)),
                _reference("other", "a_source.py", line=99),
            ),
            "b_source.py": (
                *(_reference("target", "b_source.py", line=i) for i in range(9)),
                _reference("other", "b_source.py", line=99),
            ),
            "c_source.py": (
                *(_reference("target", "c_source.py", line=i) for i in range(4)),
                _reference("other", "c_source.py", line=99),
            ),
            "d_source.py": (
                _reference("target", "d_source.py", line=1),
                _reference("other", "d_source.py", line=99),
            ),
        },
    )

    result = graph_ranker.rank_broad(symbol_index)

    contributors = _ranked_file(result, "target.py").top_rank_contributors
    assert len(contributors) == 3
    assert tuple(contributor.source_path for contributor in contributors) == (
        "a_source.py",
        "b_source.py",
        "c_source.py",
    )
    assert tuple(contributor.identifier for contributor in contributors) == (
        "target",
        "target",
        "target",
    )
    assert tuple(contributor.weighted_edge for contributor in contributors) == (
        pytest.approx(4.0),
        pytest.approx(3.0),
        pytest.approx(2.0),
    )
    assert tuple(contributor.weight_multiplier for contributor in contributors) == (
        pytest.approx(1.0),
        pytest.approx(1.0),
        pytest.approx(1.0),
    )


def test_rank_broad_empty_graph_uses_stable_path_fallback_without_self_loop():
    symbol_index = _symbol_index(
        paths=("zeta.py", "alpha.py", "models.py"),
        definitions_by_symbol={"Model": (_definition("Model", "models.py"),)},
    )

    result = graph_ranker.rank_broad(symbol_index)

    assert result.ranking.algorithm == "stable_path_fallback"
    assert result.ranking.top_ranked_files == ("alpha.py", "models.py", "zeta.py")
    assert tuple(score.path for score in result.ranked_files) == (
        "alpha.py",
        "models.py",
        "zeta.py",
    )
    assert all(score.node_pagerank == 0.0 for score in result.ranked_files)
    assert all(score.definition_rank_sum == 0.0 for score in result.ranked_files)
    assert result.reference_graph.graph.number_of_edges() == 0
    assert not result.reference_graph.graph.has_edge("models.py", "models.py")
