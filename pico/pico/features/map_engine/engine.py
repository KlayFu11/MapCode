"""Public deterministic MapEngine facade."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Literal

from pico.features.map_engine.config import MAP_ENGINE_SCHEMA_VERSION
from pico.features.map_engine.context_renderer import RankedContextRender
from pico.features.map_engine.context_renderer import render_ranked_context
from pico.features.map_engine.graph_ranker import GraphRankingResult
from pico.features.map_engine.graph_ranker import rank_broad
from pico.features.map_engine.graph_ranker import rank_focused
from pico.features.map_engine.models import IndexStatus
from pico.features.map_engine.models import MapContextEvidence
from pico.features.map_engine.models import MapResult
from pico.features.map_engine.models import PromptAnalysis
from pico.features.map_engine.models import SelectorCandidateCatalog
from pico.features.map_engine.prompt_analyzer import analyze_prompt
from pico.features.map_engine.selector_catalog import (
    build_selector_catalog as build_selector_candidate_catalog,
)
from pico.features.map_engine.source_files import list_python_source_files
from pico.features.map_engine.symbol_index import SymbolIndex
from pico.features.map_engine.symbol_index import build_symbol_index


class MapEngineIndexNotReady(RuntimeError):
    """Raised when a MapEngine operation needs a ready SymbolIndex snapshot."""


class MapEngine:
    def __init__(self, repo_root: str | Path) -> None:
        self._repo_root = Path(repo_root)
        self._symbol_index: SymbolIndex | None = None
        self._index_status: IndexStatus | None = None

    def ensure_index(self) -> IndexStatus:
        if self._symbol_index is None:
            source_selection = list_python_source_files(self._repo_root)
            symbol_index = build_symbol_index(
                self._repo_root,
                source_selection.source_paths,
            )
            self._symbol_index = symbol_index
            self._index_status = _index_status_from_symbol_index(symbol_index)

        if self._index_status is None:
            raise MapEngineIndexNotReady("MapEngine index status is not ready")
        return self._index_status

    def analyze(self, prompt: str) -> PromptAnalysis:
        return analyze_prompt(
            prompt,
            self._ready_symbol_index(),
            self._repo_root,
        )

    def generate_broad(self, analysis: PromptAnalysis) -> MapResult:
        symbol_index = self._ready_symbol_index()
        start = perf_counter()
        ranking = rank_broad(
            symbol_index,
            ident_boost_inputs=analysis.mentioned_idents,
        )
        rendered_context = render_ranked_context(
            ranking.ranked_files,
            ranking.ranked_definitions,
            symbol_index.definitions_by_file,
            analysis,
            repo_root=self._repo_root,
            mode="broad",
        )
        return _map_result(
            symbol_index=symbol_index,
            analysis=analysis,
            ranking=ranking,
            rendered_context=rendered_context,
            mode="broad",
            focus_fnames=(),
            duration_ms=_elapsed_ms(start),
        )

    def build_selector_catalog(self) -> SelectorCandidateCatalog:
        return build_selector_candidate_catalog(self._ready_symbol_index())

    def generate_focused(
        self,
        analysis: PromptAnalysis,
        focus_fnames: tuple[str, ...],
    ) -> MapResult:
        symbol_index = self._ready_symbol_index()
        start = perf_counter()
        ranking = rank_focused(
            symbol_index,
            focus_fnames=focus_fnames,
            path_ident_hit_files=analysis.path_ident_hit_files,
            ident_boost_inputs=analysis.mentioned_idents,
            effective_symbol_hits=analysis.effective_symbol_hits,
        )
        stable_focus_fnames = ranking.ranking.focus_fnames
        rendered_context = render_ranked_context(
            ranking.ranked_files,
            ranking.ranked_definitions,
            symbol_index.definitions_by_file,
            analysis,
            repo_root=self._repo_root,
            mode="focused",
            focus_fnames=stable_focus_fnames,
        )
        return _map_result(
            symbol_index=symbol_index,
            analysis=analysis,
            ranking=ranking,
            rendered_context=rendered_context,
            mode="focused",
            focus_fnames=stable_focus_fnames,
            duration_ms=_elapsed_ms(start),
        )

    def _ready_symbol_index(self) -> SymbolIndex:
        if self._symbol_index is None:
            raise MapEngineIndexNotReady("MapEngine.ensure_index() must run first")
        return self._symbol_index


def _index_status_from_symbol_index(symbol_index: SymbolIndex) -> IndexStatus:
    return IndexStatus(
        index_snapshot_id=symbol_index.index_snapshot_id,
        cache_status=symbol_index.cache_status,
        file_count=len(symbol_index.file_records),
        definition_count=sum(
            len(definitions)
            for definitions in symbol_index.definitions_by_file.values()
        ),
        reference_count=sum(
            len(references)
            for references in symbol_index.references_by_file.values()
        ),
    )


def _map_result(
    *,
    symbol_index: SymbolIndex,
    analysis: PromptAnalysis,
    ranking: GraphRankingResult,
    rendered_context: RankedContextRender,
    mode: Literal["broad", "focused"],
    focus_fnames: tuple[str, ...],
    duration_ms: int,
) -> MapResult:
    evidence = MapContextEvidence(
        schema_version=MAP_ENGINE_SCHEMA_VERSION,
        index_snapshot_id=symbol_index.index_snapshot_id,
        analysis=analysis,
        ranking=ranking.ranking,
        rendering=rendered_context.rendering,
        rendered_files=rendered_context.rendered_files,
        omitted_files=rendered_context.omitted_files,
        cache_status=symbol_index.cache_status,
        duration_ms=duration_ms,
    )
    return MapResult(
        mode=mode,
        repo_map_text=rendered_context.repo_map_text,
        focus_fnames=focus_fnames,
        rendered_files=tuple(file.path for file in rendered_context.rendered_files),
        rendered_symbols=rendered_context.rendered_symbols,
        evidence=evidence,
    )


def _elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))
