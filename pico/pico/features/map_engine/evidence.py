"""Ranking evidence helpers for MapEngine graph ranking."""

from pico.features.map_engine.config import COMMON_IDENT_DEFINER_THRESHOLD
from pico.features.map_engine.config import COMMON_IDENT_PENALTY
from pico.features.map_engine.config import IDENT_BOOST
from pico.features.map_engine.config import PRIVATE_IDENT_PENALTY
from pico.features.map_engine.config import STRUCTURED_IDENT_BOOST
from pico.features.map_engine.config import STRUCTURED_IDENT_MIN_LENGTH
from pico.features.map_engine.models import DefinitionRecord


def symbol_weight_multiplier(
    identifier: str,
    definitions: tuple[DefinitionRecord, ...],
    ident_boost_inputs: tuple[str, ...],
) -> tuple[float, tuple[str, ...]]:
    multiplier = 1.0
    reason_codes = []
    ident_boost_set = set(ident_boost_inputs)

    if identifier in ident_boost_set:
        multiplier *= IDENT_BOOST
        reason_codes.append("prompt_ident_boost")
    if is_structured_identifier(identifier):
        multiplier *= STRUCTURED_IDENT_BOOST
        reason_codes.append("structured_ident_boost")
    if identifier.startswith("_"):
        multiplier *= PRIVATE_IDENT_PENALTY
        reason_codes.append("private_ident_penalty")
    if _unique_defining_file_count(definitions) > COMMON_IDENT_DEFINER_THRESHOLD:
        multiplier *= COMMON_IDENT_PENALTY
        reason_codes.append("common_ident_penalty")

    return multiplier, tuple(reason_codes)


def is_structured_identifier(identifier: str) -> bool:
    if len(identifier) < STRUCTURED_IDENT_MIN_LENGTH:
        return False

    has_letter = any(char.isalpha() for char in identifier)
    if has_letter and ("_" in identifier or "-" in identifier):
        return True

    has_lower = any(char.islower() for char in identifier)
    has_upper = any(char.isupper() for char in identifier)
    return has_lower and has_upper


def _unique_defining_file_count(definitions: tuple[DefinitionRecord, ...]) -> int:
    return len({definition.path for definition in definitions})
