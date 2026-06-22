"""File-level definition/reference graph construction."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from math import sqrt
from typing import Literal

import networkx as nx

from pico.features.map_engine.config import FOCUS_OUTBOUND_BOOST
from pico.features.map_engine.config import PAGERANK_ALPHA
from pico.features.map_engine.config import PAGERANK_MAX_ITER
from pico.features.map_engine.config import PAGERANK_TOL
from pico.features.map_engine.config import RANKING_POLICY_VERSION
from pico.features.map_engine.config import TOP_RANKED_FILES_LIMIT
from pico.features.map_engine.context_renderer import focused_definition_candidates
from pico.features.map_engine.evidence import symbol_weight_multiplier
from pico.features.map_engine.models import DefinitionRecord
from pico.features.map_engine.models import RankContributorEvidence
from pico.features.map_engine.models import RankingEvidence
from pico.features.map_engine.symbol_index import SymbolIndex


@dataclass(frozen=True)
class FileReferenceEdge:
    source_path: str
    target_path: str
    identifier: str
    reference_count: int
    weight: float
    weight_multiplier: float
    weight_reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class FileReferenceGraph:
    graph: nx.MultiDiGraph
    edges: tuple[FileReferenceEdge, ...]
    node_paths: tuple[str, ...]
    fallback_paths: tuple[str, ...]


@dataclass(frozen=True)
class RankedFileScore:
    path: str
    node_pagerank: float
    pagerank_norm: float
    definition_rank_sum: float
    top_rank_contributors: tuple[RankContributorEvidence, ...]


@dataclass(frozen=True)
class GraphRankingResult:
    reference_graph: FileReferenceGraph
    ranking: RankingEvidence
    ranked_files: tuple[RankedFileScore, ...]
    ranked_definitions: tuple[DefinitionRecord, ...]


def stable_path_fallback(symbol_index: SymbolIndex) -> tuple[str, ...]:
    return tuple(sorted(symbol_index.file_records))


def build_file_reference_graph(
    symbol_index: SymbolIndex,
    ident_boost_inputs: tuple[str, ...] = (),
) -> FileReferenceGraph:
    fallback_paths = stable_path_fallback(symbol_index)
    known_paths = set(symbol_index.file_records)
    graph = nx.MultiDiGraph()

    edges: list[FileReferenceEdge] = []
    for source_path, identifier, reference_count in _reference_counts(symbol_index):
        if source_path not in known_paths:
            continue
        definitions = symbol_index.definitions_by_symbol.get(identifier, ())
        multiplier, reason_codes = symbol_weight_multiplier(
            identifier,
            definitions,
            ident_boost_inputs,
        )
        for target_path in _definition_paths(
            definitions,
            known_paths,
        ):
            weight = sqrt(reference_count) * multiplier
            edge = FileReferenceEdge(
                source_path=source_path,
                target_path=target_path,
                identifier=identifier,
                reference_count=reference_count,
                weight=weight,
                weight_multiplier=multiplier,
                weight_reason_codes=reason_codes,
            )
            graph.add_edge(
                source_path,
                target_path,
                key=identifier,
                identifier=identifier,
                reference_count=reference_count,
                weight=weight,
                weight_multiplier=multiplier,
                weight_reason_codes=reason_codes,
            )
            edges.append(edge)

    node_paths = tuple(sorted(graph.nodes))
    return FileReferenceGraph(
        graph=graph,
        edges=tuple(edges),
        node_paths=node_paths,
        fallback_paths=fallback_paths,
    )


def rank_broad(
    symbol_index: SymbolIndex,
    ident_boost_inputs: tuple[str, ...] = (),
) -> GraphRankingResult:
    reference_graph = build_file_reference_graph(
        symbol_index,
        ident_boost_inputs=ident_boost_inputs,
    )
    if not reference_graph.node_paths:
        return _stable_fallback_result(reference_graph, symbol_index, ident_boost_inputs)

    try:
        node_pagerank = nx.pagerank(
            reference_graph.graph,
            alpha=PAGERANK_ALPHA,
            max_iter=PAGERANK_MAX_ITER,
            tol=PAGERANK_TOL,
            weight="weight",
        )
    except (nx.PowerIterationFailedConvergence, ZeroDivisionError):
        return _stable_fallback_result(reference_graph, symbol_index, ident_boost_inputs)

    definition_group_ranks = _definition_group_ranks(
        reference_graph.edges,
        node_pagerank,
    )
    definition_rank_sums = _definition_rank_sums(definition_group_ranks)
    contributor_evidence = _top_contributors_by_target(
        reference_graph.edges,
        node_pagerank,
    )
    ranked_files = _ranked_file_scores(
        reference_graph.node_paths,
        node_pagerank,
        definition_rank_sums,
        contributor_evidence,
    )
    ranking = _ranking_evidence(
        algorithm="pagerank",
        ident_boost_inputs=ident_boost_inputs,
        top_ranked_files=tuple(
            score.path for score in ranked_files[:TOP_RANKED_FILES_LIMIT]
        ),
    )
    return GraphRankingResult(
        reference_graph=reference_graph,
        ranking=ranking,
        ranked_files=ranked_files,
        ranked_definitions=_ranked_definitions(symbol_index, definition_group_ranks),
    )


def rank_focused(
    symbol_index: SymbolIndex,
    focus_fnames: tuple[str, ...] = (),
    path_ident_hit_files: Mapping[str, tuple[str, ...]] | None = None,
    ident_boost_inputs: tuple[str, ...] = (),
    effective_symbol_hits: tuple[str, ...] = (),
) -> GraphRankingResult:
    focus_fnames = _stable_unique_paths(focus_fnames)
    reference_graph = build_file_reference_graph(
        symbol_index,
        ident_boost_inputs=ident_boost_inputs,
    )
    node_path_set = set(reference_graph.node_paths)
    focus_personalization_files = _focus_personalization_files(
        focus_fnames,
        node_path_set,
    )
    path_personalization_files = _path_personalization_files(
        path_ident_hit_files or {},
        node_path_set,
    )
    personalization_files, personalization = _personalization_weights(
        focus_personalization_files,
        path_personalization_files,
    )
    reference_graph = _with_focus_outbound_boost(
        reference_graph,
        focus_personalization_files,
    )
    if not reference_graph.node_paths:
        return _stable_fallback_result(
            reference_graph,
            symbol_index,
            ident_boost_inputs,
            focus_fnames=focus_fnames,
            focus_personalization_files=focus_personalization_files,
            path_personalization_files=path_personalization_files,
            personalization_files=personalization_files,
            effective_symbol_hits=effective_symbol_hits,
        )

    try:
        node_pagerank = nx.pagerank(
            reference_graph.graph,
            alpha=PAGERANK_ALPHA,
            max_iter=PAGERANK_MAX_ITER,
            tol=PAGERANK_TOL,
            weight="weight",
            personalization=personalization or None,
        )
    except (nx.PowerIterationFailedConvergence, ZeroDivisionError):
        return _stable_fallback_result(
            reference_graph,
            symbol_index,
            ident_boost_inputs,
            focus_fnames=focus_fnames,
            focus_personalization_files=focus_personalization_files,
            path_personalization_files=path_personalization_files,
            personalization_files=personalization_files,
            effective_symbol_hits=effective_symbol_hits,
        )

    definition_group_ranks = _definition_group_ranks(
        reference_graph.edges,
        node_pagerank,
    )
    definition_rank_sums = _definition_rank_sums(definition_group_ranks)
    contributor_evidence = _top_contributors_by_target(
        reference_graph.edges,
        node_pagerank,
    )
    ranked_files = _ranked_file_scores(
        reference_graph.node_paths,
        node_pagerank,
        definition_rank_sums,
        contributor_evidence,
    )
    algorithm = "personalized_pagerank" if personalization_files else "pagerank"
    ranking = _ranking_evidence(
        algorithm=algorithm,
        ident_boost_inputs=ident_boost_inputs,
        top_ranked_files=tuple(
            score.path for score in ranked_files[:TOP_RANKED_FILES_LIMIT]
        ),
        focus_fnames=focus_fnames,
        focus_personalization_files=focus_personalization_files,
        path_personalization_files=path_personalization_files,
        personalization_files=personalization_files,
    )
    return GraphRankingResult(
        reference_graph=reference_graph,
        ranking=ranking,
        ranked_files=ranked_files,
        ranked_definitions=focused_definition_candidates(
            _ranked_definitions(symbol_index, definition_group_ranks),
            symbol_index.definitions_by_symbol,
            effective_symbol_hits=effective_symbol_hits,
        ),
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


def _stable_fallback_result(
    reference_graph: FileReferenceGraph,
    symbol_index: SymbolIndex,
    ident_boost_inputs: tuple[str, ...],
    *,
    focus_fnames: tuple[str, ...] = (),
    focus_personalization_files: tuple[str, ...] = (),
    path_personalization_files: tuple[str, ...] = (),
    personalization_files: tuple[str, ...] = (),
    effective_symbol_hits: tuple[str, ...] = (),
) -> GraphRankingResult:
    ranked_files = tuple(
        RankedFileScore(
            path=path,
            node_pagerank=0.0,
            pagerank_norm=0.0,
            definition_rank_sum=0.0,
            top_rank_contributors=(),
        )
        for path in reference_graph.fallback_paths
    )
    ranking = _ranking_evidence(
        algorithm="stable_path_fallback",
        ident_boost_inputs=ident_boost_inputs,
        top_ranked_files=tuple(
            score.path for score in ranked_files[:TOP_RANKED_FILES_LIMIT]
        ),
        focus_fnames=focus_fnames,
        focus_personalization_files=focus_personalization_files,
        path_personalization_files=path_personalization_files,
        personalization_files=personalization_files,
    )
    return GraphRankingResult(
        reference_graph=reference_graph,
        ranking=ranking,
        ranked_files=ranked_files,
        ranked_definitions=focused_definition_candidates(
            _ranked_definitions(symbol_index, {}),
            symbol_index.definitions_by_symbol,
            effective_symbol_hits=effective_symbol_hits,
        ),
    )


def _ranking_evidence(
    *,
    algorithm: Literal["pagerank", "personalized_pagerank", "stable_path_fallback"],
    ident_boost_inputs: tuple[str, ...],
    top_ranked_files: tuple[str, ...],
    focus_fnames: tuple[str, ...] = (),
    focus_personalization_files: tuple[str, ...] = (),
    path_personalization_files: tuple[str, ...] = (),
    personalization_files: tuple[str, ...] = (),
) -> RankingEvidence:
    return RankingEvidence(
        policy_version=RANKING_POLICY_VERSION,
        algorithm=algorithm,
        focus_fnames=focus_fnames,
        ident_boost_inputs=ident_boost_inputs,
        focus_personalization_files=focus_personalization_files,
        path_personalization_files=path_personalization_files,
        personalization_files=personalization_files,
        top_ranked_files=top_ranked_files,
    )


def _focus_personalization_files(
    focus_fnames: tuple[str, ...],
    node_path_set: set[str],
) -> tuple[str, ...]:
    return tuple(path for path in focus_fnames if path in node_path_set)


def _stable_unique_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    unique_paths: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path not in seen:
            unique_paths.append(path)
            seen.add(path)
    return tuple(unique_paths)


def _path_personalization_files(
    path_ident_hit_files: Mapping[str, tuple[str, ...]],
    node_path_set: set[str],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                path
                for paths in path_ident_hit_files.values()
                for path in paths
                if path in node_path_set
            }
        )
    )


def _personalization_weights(
    focus_personalization_files: tuple[str, ...],
    path_personalization_files: tuple[str, ...],
) -> tuple[tuple[str, ...], dict[str, float]]:
    contribution_counts: Counter[str] = Counter()
    contribution_counts.update(focus_personalization_files)
    contribution_counts.update(path_personalization_files)
    personalization_files = focus_personalization_files + tuple(
        path
        for path in path_personalization_files
        if path not in set(focus_personalization_files)
    )
    total_contributions = sum(contribution_counts.values())
    if not total_contributions:
        return personalization_files, {}
    return personalization_files, {
        path: contribution_counts[path] / total_contributions
        for path in personalization_files
    }


def _with_focus_outbound_boost(
    reference_graph: FileReferenceGraph,
    focus_personalization_files: tuple[str, ...],
) -> FileReferenceGraph:
    focus_path_set = set(focus_personalization_files)
    if not focus_path_set:
        return reference_graph

    graph = nx.MultiDiGraph()
    edges: list[FileReferenceEdge] = []
    for edge in reference_graph.edges:
        weight = edge.weight
        weight_multiplier = edge.weight_multiplier
        weight_reason_codes = edge.weight_reason_codes
        if edge.source_path in focus_path_set:
            weight *= FOCUS_OUTBOUND_BOOST
            weight_multiplier *= FOCUS_OUTBOUND_BOOST
            weight_reason_codes = weight_reason_codes + ("focus_outbound_boost",)

        boosted_edge = FileReferenceEdge(
            source_path=edge.source_path,
            target_path=edge.target_path,
            identifier=edge.identifier,
            reference_count=edge.reference_count,
            weight=weight,
            weight_multiplier=weight_multiplier,
            weight_reason_codes=weight_reason_codes,
        )
        graph.add_edge(
            boosted_edge.source_path,
            boosted_edge.target_path,
            key=boosted_edge.identifier,
            identifier=boosted_edge.identifier,
            reference_count=boosted_edge.reference_count,
            weight=boosted_edge.weight,
            weight_multiplier=boosted_edge.weight_multiplier,
            weight_reason_codes=boosted_edge.weight_reason_codes,
        )
        edges.append(boosted_edge)

    return FileReferenceGraph(
        graph=graph,
        edges=tuple(edges),
        node_paths=reference_graph.node_paths,
        fallback_paths=reference_graph.fallback_paths,
    )


def _definition_group_ranks(
    edges: tuple[FileReferenceEdge, ...],
    node_pagerank: dict[str, float],
) -> dict[tuple[str, str], float]:
    outgoing_weight_by_source = _outgoing_weight_by_source(edges)
    group_ranks: dict[tuple[str, str], float] = {}
    for edge in edges:
        outgoing_weight = outgoing_weight_by_source[edge.source_path]
        contribution = node_pagerank.get(edge.source_path, 0.0) * (
            edge.weight / outgoing_weight
        )
        key = (edge.target_path, edge.identifier)
        group_ranks[key] = group_ranks.get(key, 0.0) + contribution
    return group_ranks


def _definition_rank_sums(
    definition_group_ranks: dict[tuple[str, str], float],
) -> dict[str, float]:
    rank_sums: dict[str, float] = {}
    for (path, _identifier), rank in definition_group_ranks.items():
        rank_sums[path] = rank_sums.get(path, 0.0) + rank
    return rank_sums


def _top_contributors_by_target(
    edges: tuple[FileReferenceEdge, ...],
    node_pagerank: dict[str, float],
) -> dict[str, tuple[RankContributorEvidence, ...]]:
    outgoing_weight_by_source = _outgoing_weight_by_source(edges)
    contributors_by_target: dict[
        str,
        list[tuple[float, RankContributorEvidence]],
    ] = {}
    for edge in edges:
        contribution = node_pagerank.get(edge.source_path, 0.0) * (
            edge.weight / outgoing_weight_by_source[edge.source_path]
        )
        contributor = RankContributorEvidence(
            source_path=edge.source_path,
            identifier=edge.identifier,
            weighted_edge=edge.weight,
            weight_multiplier=edge.weight_multiplier,
            weight_reason_codes=edge.weight_reason_codes,
        )
        contributors_by_target.setdefault(edge.target_path, []).append(
            (contribution, contributor)
        )

    return {
        target_path: tuple(
            contributor
            for _contribution, contributor in sorted(
                contributors,
                key=lambda item: (
                    -item[0],
                    item[1].source_path,
                    item[1].identifier,
                ),
            )[:3]
        )
        for target_path, contributors in contributors_by_target.items()
    }


def _ranked_file_scores(
    node_paths: tuple[str, ...],
    node_pagerank: dict[str, float],
    definition_rank_sums: dict[str, float],
    contributor_evidence: dict[str, tuple[RankContributorEvidence, ...]],
) -> tuple[RankedFileScore, ...]:
    max_pagerank = max(node_pagerank.values(), default=0.0)
    scores = [
        RankedFileScore(
            path=path,
            node_pagerank=node_pagerank.get(path, 0.0),
            pagerank_norm=(
                node_pagerank.get(path, 0.0) / max_pagerank
                if max_pagerank
                else 0.0
            ),
            definition_rank_sum=definition_rank_sums.get(path, 0.0),
            top_rank_contributors=contributor_evidence.get(path, ()),
        )
        for path in node_paths
    ]
    return tuple(
        sorted(
            scores,
            key=lambda score: (
                -score.node_pagerank,
                score.path,
            ),
        )
    )


def _outgoing_weight_by_source(
    edges: tuple[FileReferenceEdge, ...],
) -> dict[str, float]:
    outgoing_weight_by_source: dict[str, float] = {}
    for edge in edges:
        outgoing_weight_by_source[edge.source_path] = (
            outgoing_weight_by_source.get(edge.source_path, 0.0) + edge.weight
        )
    return outgoing_weight_by_source


def _ranked_definitions(
    symbol_index: SymbolIndex,
    definition_group_ranks: dict[tuple[str, str], float],
) -> tuple[DefinitionRecord, ...]:
    definitions = [
        definition
        for definitions_for_symbol in symbol_index.definitions_by_symbol.values()
        for definition in definitions_for_symbol
    ]
    return tuple(
        sorted(
            definitions,
            key=lambda definition: (
                -definition_group_ranks.get((definition.path, definition.name), 0.0),
                definition.path,
                definition.name,
                definition.line,
                definition.kind,
            ),
        )
    )
