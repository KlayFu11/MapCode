"""File-level definition/reference graph construction."""

from collections import Counter
from dataclasses import dataclass
from math import sqrt

import networkx as nx

from pico.features.map_engine.models import DefinitionRecord
from pico.features.map_engine.symbol_index import SymbolIndex


@dataclass(frozen=True)
class FileReferenceEdge:
    source_path: str
    target_path: str
    identifier: str
    reference_count: int
    weight: float


@dataclass(frozen=True)
class FileReferenceGraph:
    graph: nx.MultiDiGraph
    edges: tuple[FileReferenceEdge, ...]
    node_paths: tuple[str, ...]
    fallback_paths: tuple[str, ...]


def stable_path_fallback(symbol_index: SymbolIndex) -> tuple[str, ...]:
    return tuple(sorted(symbol_index.file_records))


def build_file_reference_graph(symbol_index: SymbolIndex) -> FileReferenceGraph:
    fallback_paths = stable_path_fallback(symbol_index)
    known_paths = set(symbol_index.file_records)
    graph = nx.MultiDiGraph()

    edges: list[FileReferenceEdge] = []
    for source_path, identifier, reference_count in _reference_counts(symbol_index):
        if source_path not in known_paths:
            continue
        for target_path in _definition_paths(
            symbol_index.definitions_by_symbol.get(identifier, ()),
            known_paths,
        ):
            weight = sqrt(reference_count)
            edge = FileReferenceEdge(
                source_path=source_path,
                target_path=target_path,
                identifier=identifier,
                reference_count=reference_count,
                weight=weight,
            )
            graph.add_edge(
                source_path,
                target_path,
                key=identifier,
                identifier=identifier,
                reference_count=reference_count,
                weight=weight,
            )
            edges.append(edge)

    node_paths = tuple(sorted(graph.nodes))
    return FileReferenceGraph(
        graph=graph,
        edges=tuple(edges),
        node_paths=node_paths,
        fallback_paths=fallback_paths,
    )


def _reference_counts(
    symbol_index: SymbolIndex,
) -> tuple[tuple[str, str, int], ...]:
    counts: Counter[tuple[str, str]] = Counter()
    for source_path, references in symbol_index.references_by_file.items():
        for reference in references:
            counts[(source_path, reference.name)] += 1

    return tuple(
        (source_path, identifier, count)
        for (source_path, identifier), count in sorted(counts.items())
    )


def _definition_paths(
    definitions: tuple[DefinitionRecord, ...],
    known_paths: set[str],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                definition.path
                for definition in definitions
                if definition.path in known_paths
            }
        )
    )
