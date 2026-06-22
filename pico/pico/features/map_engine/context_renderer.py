"""Definition candidate ordering helpers for map context rendering."""

from collections.abc import Mapping

from pico.features.map_engine.models import DefinitionRecord


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
