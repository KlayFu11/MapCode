from math import sqrt

import pytest

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
