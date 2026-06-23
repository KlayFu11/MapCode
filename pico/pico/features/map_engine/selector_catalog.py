"""Selector candidate catalog rendering from a ready SymbolIndex snapshot."""

from __future__ import annotations

from math import ceil

from pico.features.map_engine.config import SELECTOR_CATALOG_MAX_DEFS_PER_FILE
from pico.features.map_engine.config import SELECTOR_CATALOG_MAX_FILES
from pico.features.map_engine.config import SELECTOR_CATALOG_MAX_TOKENS
from pico.features.map_engine.models import DefinitionRecord
from pico.features.map_engine.models import SelectorCandidateCatalog
from pico.features.map_engine.symbol_index import SymbolIndex


def build_selector_catalog(symbol_index: SymbolIndex) -> SelectorCandidateCatalog:
    candidate_paths = _candidate_paths(symbol_index)
    rendered_paths = []
    rendered_definition_count = 0
    definition_truncated = False
    token_truncated = False
    blocks = []
    used_chars = 0
    target_chars = SELECTOR_CATALOG_MAX_TOKENS * 4

    for path in candidate_paths[:SELECTOR_CATALOG_MAX_FILES]:
        definitions = _definitions_for_path(symbol_index, path)
        rendered_definitions = definitions[:SELECTOR_CATALOG_MAX_DEFS_PER_FILE]
        definition_truncated = definition_truncated or (
            len(rendered_definitions) < len(definitions)
        )
        block = _format_catalog_file_block(path, rendered_definitions)
        projected_chars = _projected_chars(used_chars, bool(blocks), block)
        if projected_chars > target_chars:
            token_truncated = True
            break

        blocks.append(block)
        rendered_paths.append(path)
        rendered_definition_count += len(rendered_definitions)
        used_chars = projected_chars

    rendered_text = "\n".join(blocks)
    rendered_path_tuple = tuple(rendered_paths)
    file_truncated = len(rendered_path_tuple) < len(candidate_paths)
    definition_count = sum(
        len(_definitions_for_path(symbol_index, path))
        for path in candidate_paths
    )

    return SelectorCandidateCatalog(
        index_snapshot_id=symbol_index.index_snapshot_id,
        candidate_paths=candidate_paths,
        rendered_paths=rendered_path_tuple,
        rendered_text=rendered_text,
        file_count=len(candidate_paths),
        definition_count=definition_count,
        rendered_file_count=len(rendered_path_tuple),
        rendered_definition_count=rendered_definition_count,
        estimated_tokens=_estimate_tokens(rendered_text),
        truncated=file_truncated or definition_truncated or token_truncated,
    )


def _candidate_paths(symbol_index: SymbolIndex) -> tuple[str, ...]:
    return tuple(sorted(symbol_index.file_records))


def _definitions_for_path(
    symbol_index: SymbolIndex,
    path: str,
) -> tuple[DefinitionRecord, ...]:
    return tuple(
        sorted(
            (
                definition
                for definition in symbol_index.definitions_by_file.get(path, ())
                if definition.path == path
            ),
            key=lambda definition: (
                definition.line,
                definition.name,
                definition.kind,
            ),
        )
    )


def _format_catalog_file_block(
    path: str,
    definitions: tuple[DefinitionRecord, ...],
) -> str:
    lines = [f"{path}:"]
    lines.extend(
        f"  {definition.kind} {definition.name} line {definition.line}"
        for definition in definitions
    )
    return "\n".join(lines)


def _projected_chars(
    used_chars: int,
    has_blocks: bool,
    block: str,
) -> int:
    separator_chars = 1 if has_blocks else 0
    return used_chars + separator_chars + len(block)


def _estimate_tokens(rendered_text: str) -> int:
    return ceil(len(rendered_text) / 4)
