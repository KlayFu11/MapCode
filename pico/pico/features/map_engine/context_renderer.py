"""Definition candidate ordering and TreeContext rendering helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Literal
from typing import Protocol

from grep_ast import TreeContext

from pico.features.map_engine.config import BROAD_MAP_BUDGET_TOKENS
from pico.features.map_engine.config import FOCUSED_MAP_BUDGET_TOKENS
from pico.features.map_engine.models import DefinitionRecord
from pico.features.map_engine.models import OmittedFileEvidence
from pico.features.map_engine.models import PromptAnalysis
from pico.features.map_engine.models import RankContributorEvidence
from pico.features.map_engine.models import RenderingEvidence
from pico.features.map_engine.models import RenderedFileEvidence


class RankedFileScoreLike(Protocol):
    path: str
    node_pagerank: float
    pagerank_norm: float
    definition_rank_sum: float
    top_rank_contributors: tuple[RankContributorEvidence, ...]


@dataclass(frozen=True)
class RankedContextRender:
    repo_map_text: str
    rendered_files: tuple[RenderedFileEvidence, ...]
    omitted_files: tuple[OmittedFileEvidence, ...]
    rendered_symbols: tuple[str, ...]
    rendering: RenderingEvidence


def focused_definition_candidates(
    ranked_definitions: tuple[DefinitionRecord, ...],
    definitions_by_symbol: Mapping[str, tuple[DefinitionRecord, ...]],
    effective_symbol_hits: tuple[str, ...] = (),
) -> tuple[DefinitionRecord, ...]:
    candidates: list[DefinitionRecord] = []
    seen: set[DefinitionRecord] = set()

    for symbol in effective_symbol_hits:
        for definition in definitions_by_symbol.get(symbol, ()):
            if definition in seen:
                continue
            candidates.append(definition)
            seen.add(definition)

    for definition in ranked_definitions:
        if definition in seen:
            continue
        candidates.append(definition)
        seen.add(definition)

    return tuple(candidates)


def render_ranked_context(
    ranked_files: tuple[RankedFileScoreLike, ...],
    ranked_definitions: tuple[DefinitionRecord, ...],
    definitions_by_file: Mapping[str, tuple[DefinitionRecord, ...]],
    analysis: PromptAnalysis,
    *,
    source_by_path: Mapping[str, str] | None = None,
    repo_root: str | Path | None = None,
    mode: Literal["focused", "broad"] = "focused",
    focus_fnames: tuple[str, ...] = (),
    omitted_files: tuple[RankedFileScoreLike, ...] = (),
    omission_reason: str = "not_rendered",
) -> RankedContextRender:
    target_tokens = _target_tokens_for_mode(mode)
    target_chars = target_tokens * 4
    definitions_by_render_path = _definitions_by_render_path(
        ranked_definitions,
    )
    rendered_file_evidence = []
    rendered_symbol_names = []
    rendered_symbols_by_path = {}
    budget_omitted_files = []
    budget_path_only_fallback_applied = False
    blocks = []
    used_chars = 0

    for score in ranked_files:
        rendered_body, rendered_definitions = _render_file_body(
            score.path,
            definitions_by_render_path.get(score.path, ()),
            source_by_path=source_by_path,
            repo_root=repo_root,
        )
        symbols = _unique_symbols(rendered_definitions)
        block = _format_file_block(score.path, rendered_body)
        next_used_chars = _projected_used_chars(used_chars, bool(blocks), block)
        if next_used_chars > target_chars:
            block = _format_file_block(score.path, "")
            next_used_chars = _projected_used_chars(used_chars, bool(blocks), block)
            if next_used_chars > target_chars:
                budget_omitted_files.append(score)
                continue
            symbols = ()
            budget_path_only_fallback_applied = True

        render_rank = len(rendered_file_evidence) + 1
        used_chars = next_used_chars
        blocks.append(block)
        rendered_symbol_names.extend(symbols)
        rendered_symbols_by_path[score.path] = symbols
        rendered_file_evidence.append(
            _rendered_file_evidence(
                score,
                render_rank,
                symbols,
                definitions_by_file,
                analysis,
            )
        )

    explicit_omitted_file_evidence = tuple(
        _omitted_file_evidence(
            score,
            omission_reason,
            definitions_by_file,
            analysis,
        )
        for score in omitted_files
    )
    budget_omitted_file_evidence = tuple(
        _omitted_file_evidence(
            score,
            "map_budget_exhausted",
            definitions_by_file,
            analysis,
        )
        for score in budget_omitted_files
    )
    repo_map_text = "\n".join(blocks)

    return RankedContextRender(
        repo_map_text=repo_map_text,
        rendered_files=tuple(rendered_file_evidence),
        omitted_files=explicit_omitted_file_evidence + budget_omitted_file_evidence,
        rendered_symbols=_stable_unique(rendered_symbol_names),
        rendering=RenderingEvidence(
            target_tokens=target_tokens,
            target_chars=target_chars,
            used_chars=len(repo_map_text),
            estimated_tokens=_estimate_tokens(len(repo_map_text)),
            budget_reduction_applied=bool(budget_omitted_files)
            or budget_path_only_fallback_applied,
            focus_truncated=_focus_truncated(
                focus_fnames,
                rendered_symbols_by_path,
                definitions_by_render_path,
            ),
        ),
    )


def _target_tokens_for_mode(mode: Literal["focused", "broad"]) -> int:
    if mode == "focused":
        return FOCUSED_MAP_BUDGET_TOKENS
    if mode == "broad":
        return BROAD_MAP_BUDGET_TOKENS
    raise ValueError(f"unsupported render mode: {mode}")


def _projected_used_chars(
    used_chars: int,
    has_blocks: bool,
    block: str,
) -> int:
    separator_chars = 1 if has_blocks else 0
    return used_chars + separator_chars + len(block)


def _estimate_tokens(chars: int) -> int:
    return ceil(chars / 4)


def _focus_truncated(
    focus_fnames: tuple[str, ...],
    rendered_symbols_by_path: Mapping[str, tuple[str, ...]],
    definitions_by_render_path: Mapping[str, tuple[DefinitionRecord, ...]],
) -> bool:
    for path in focus_fnames:
        if path not in rendered_symbols_by_path:
            return True
        expected_symbols = _unique_symbols(definitions_by_render_path.get(path, ()))
        if len(rendered_symbols_by_path[path]) < len(expected_symbols):
            return True
    return False


def _definitions_by_render_path(
    ranked_definitions: tuple[DefinitionRecord, ...],
) -> dict[str, tuple[DefinitionRecord, ...]]:
    definitions_by_path: dict[str, list[DefinitionRecord]] = {}
    seen: set[DefinitionRecord] = set()
    for definition in ranked_definitions:
        if definition in seen:
            continue
        definitions_by_path.setdefault(definition.path, []).append(definition)
        seen.add(definition)

    return {
        path: tuple(definitions)
        for path, definitions in definitions_by_path.items()
    }


def _render_file_body(
    path: str,
    definitions: tuple[DefinitionRecord, ...],
    *,
    source_by_path: Mapping[str, str] | None,
    repo_root: str | Path | None,
) -> tuple[str, tuple[DefinitionRecord, ...]]:
    if not definitions:
        return "", ()

    source = _source_for_path(path, source_by_path, repo_root)
    if source is None:
        return "", ()

    valid_definitions = _definitions_with_valid_lines(definitions, source)
    if not valid_definitions:
        return "", ()

    try:
        context = TreeContext(
            path,
            source,
            color=False,
            line_number=False,
            child_context=True,
            last_line=False,
            margin=0,
            mark_lois=True,
            loi_pad=0,
            show_top_of_file_parent_scope=False,
        )
        context.add_lines_of_interest(
            sorted({definition.line for definition in valid_definitions})
        )
        context.add_context()
        body = context.format().rstrip()
    except Exception:
        return "", ()

    if not body:
        return "", ()
    return body, valid_definitions


def _source_for_path(
    path: str,
    source_by_path: Mapping[str, str] | None,
    repo_root: str | Path | None,
) -> str | None:
    if source_by_path is not None and path in source_by_path:
        return source_by_path[path]
    if repo_root is None:
        return None

    try:
        return (Path(repo_root) / path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _definitions_with_valid_lines(
    definitions: tuple[DefinitionRecord, ...],
    source: str,
) -> tuple[DefinitionRecord, ...]:
    line_count = len(source.splitlines())
    return tuple(
        definition
        for definition in definitions
        if 0 <= definition.line < line_count
    )


def _format_file_block(path: str, body: str) -> str:
    if not body:
        return f"{path}:"
    return f"{path}:\n{body}"


def _rendered_file_evidence(
    score: RankedFileScoreLike,
    render_rank: int,
    rendered_symbols: tuple[str, ...],
    definitions_by_file: Mapping[str, tuple[DefinitionRecord, ...]],
    analysis: PromptAnalysis,
) -> RenderedFileEvidence:
    path_ident_hits = _prompt_path_ident_hits(score.path, analysis)
    return RenderedFileEvidence(
        path=score.path,
        node_pagerank=score.node_pagerank,
        pagerank_norm=score.pagerank_norm,
        definition_rank_sum=score.definition_rank_sum,
        render_rank=render_rank,
        reason_codes=_reason_codes("top_ranked", path_ident_hits),
        prompt_symbol_hits=_prompt_symbol_hits(
            score.path,
            definitions_by_file,
            analysis,
        ),
        prompt_path_ident_hits=path_ident_hits,
        rendered_symbols=rendered_symbols,
        top_rank_contributors=tuple(score.top_rank_contributors),
    )


def _omitted_file_evidence(
    score: RankedFileScoreLike,
    omission_reason: str,
    definitions_by_file: Mapping[str, tuple[DefinitionRecord, ...]],
    analysis: PromptAnalysis,
) -> OmittedFileEvidence:
    path_ident_hits = _prompt_path_ident_hits(score.path, analysis)
    return OmittedFileEvidence(
        path=score.path,
        node_pagerank=score.node_pagerank,
        pagerank_norm=score.pagerank_norm,
        definition_rank_sum=score.definition_rank_sum,
        omission_reason=omission_reason,
        reason_codes=_reason_codes("omitted", path_ident_hits),
        prompt_symbol_hits=_prompt_symbol_hits(
            score.path,
            definitions_by_file,
            analysis,
        ),
        prompt_path_ident_hits=path_ident_hits,
        top_rank_contributors=tuple(score.top_rank_contributors),
    )


def _prompt_symbol_hits(
    path: str,
    definitions_by_file: Mapping[str, tuple[DefinitionRecord, ...]],
    analysis: PromptAnalysis,
) -> tuple[str, ...]:
    definition_names = {
        definition.name for definition in definitions_by_file.get(path, ())
    }
    return tuple(
        symbol
        for symbol in analysis.effective_symbol_hits
        if symbol in definition_names
    )


def _prompt_path_ident_hits(
    path: str,
    analysis: PromptAnalysis,
) -> tuple[str, ...]:
    return tuple(
        ident
        for ident, paths in analysis.path_ident_hit_files.items()
        if path in paths
    )


def _reason_codes(
    base_reason: str,
    path_ident_hits: tuple[str, ...],
) -> tuple[str, ...]:
    if path_ident_hits:
        return (base_reason, "path_ident_match")
    return (base_reason,)


def _unique_symbols(
    definitions: tuple[DefinitionRecord, ...],
) -> tuple[str, ...]:
    return _stable_unique(definition.name for definition in definitions)


def _stable_unique(values) -> tuple[str, ...]:
    unique = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        unique.append(value)
        seen.add(value)
    return tuple(unique)
