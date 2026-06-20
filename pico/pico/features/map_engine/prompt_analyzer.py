"""Prompt signal extraction helpers for MapEngine."""

from __future__ import annotations

import re
from collections.abc import Collection
from collections.abc import Iterable


def extract_mentioned_idents(text: str) -> tuple[str, ...]:
    tokens = re.split(r"\W+", text)
    return tuple(dict.fromkeys(token for token in tokens if token))


def extract_effective_symbol_hits(
    mentioned_idents: Iterable[str],
    all_defs: Collection[str],
) -> tuple[str, ...]:
    hits = []
    seen = set()

    for ident in mentioned_idents:
        if ident in all_defs and ident not in seen:
            hits.append(ident)
            seen.add(ident)

    return tuple(hits)
