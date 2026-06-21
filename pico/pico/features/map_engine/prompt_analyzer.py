"""Prompt signal extraction helpers for MapEngine."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Collection
from collections.abc import Iterable
from collections.abc import Mapping
from pathlib import Path
from pathlib import PurePosixPath

from pico.features.map_engine.models import PromptAnalysis
from pico.features.map_engine.symbol_index import SymbolIndex


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


def analyze_prompt(
    user_message: str,
    symbol_index: SymbolIndex,
    repo_root: str | Path,
) -> PromptAnalysis:
    mentioned_idents = extract_mentioned_idents(user_message)
    effective_symbol_hits = extract_effective_symbol_hits(
        mentioned_idents,
        symbol_index.all_defs,
    )
    indexed_paths = tuple(symbol_index.file_records)
    mentioned_files = _extract_mentioned_files(
        user_message,
        mentioned_idents,
        indexed_paths,
        Path(repo_root),
    )
    path_ident_hit_files = _extract_path_ident_hit_files(
        mentioned_idents,
        indexed_paths,
    )
    path_ident_hits = tuple(path_ident_hit_files)
    branch = (
        "specific"
        if mentioned_files or effective_symbol_hits or path_ident_hits
        else "fuzzy"
    )

    return PromptAnalysis(
        branch=branch,
        mentioned_files=mentioned_files,
        mentioned_idents=mentioned_idents,
        effective_symbol_hits=effective_symbol_hits,
        path_ident_hits=path_ident_hits,
        path_ident_hit_files=path_ident_hit_files,
    )


def _extract_mentioned_files(
    user_message: str,
    mentioned_idents: tuple[str, ...],
    indexed_paths: tuple[str, ...],
    repo_root: Path,
) -> tuple[str, ...]:
    indexed_path_set = set(indexed_paths)
    unique_basenames = _unique_file_terms(
        (PurePosixPath(path).name, path) for path in indexed_paths
    )
    unique_stems = _unique_file_terms(
        (PurePosixPath(path).stem.lower(), path)
        for path in indexed_paths
        if len(PurePosixPath(path).stem) >= 5
    )
    ident_positions = _first_ident_positions(user_message)
    path_like_idents = _path_like_idents(user_message)
    candidates = []
    candidate_order = 0

    for start, token in _iter_clean_tokens(user_message):
        if _is_path_like(token):
            path = _normalize_prompt_path(token, repo_root, indexed_path_set)
        else:
            path = unique_basenames.get(token)
        if path is not None:
            candidates.append((start, candidate_order, path))
            candidate_order += 1

    for ident in mentioned_idents:
        if ident in path_like_idents or len(ident) < 5:
            continue
        path = unique_stems.get(ident.lower())
        if path is None:
            continue
        candidates.append((ident_positions[ident], candidate_order, path))
        candidate_order += 1

    return _dedupe_paths_by_prompt_order(candidates)


def _extract_path_ident_hit_files(
    mentioned_idents: tuple[str, ...],
    indexed_paths: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    term_paths = _path_term_index(indexed_paths)
    hit_files = {}

    for ident in mentioned_idents:
        paths = term_paths.get(ident.lower())
        if paths is not None:
            hit_files[ident] = paths

    return hit_files


def _iter_clean_tokens(text: str) -> Iterable[tuple[int, str]]:
    for match in re.finditer(r"\S+", text):
        token = _clean_prompt_token(match.group(0))
        if token:
            yield match.start(), token


def _clean_prompt_token(token: str) -> str:
    token = token.strip()
    token = token.strip("`*_~'\"“”‘’<>[](){}")
    token = token.rstrip(".,;:!?")
    return token.strip("`*_~'\"“”‘’<>[](){}")


def _is_path_like(token: str) -> bool:
    return "/" in token or "\\" in token


def _normalize_prompt_path(
    token: str,
    repo_root: Path,
    indexed_paths: set[str],
) -> str | None:
    normalized_token = token.replace("\\", "/")
    if normalized_token.startswith("./"):
        normalized_token = normalized_token[2:]

    path = Path(normalized_token)
    if path.is_absolute():
        relative_path = _absolute_path_to_repo_relative(path, repo_root)
    else:
        relative_path = _normalize_repo_relative_path(normalized_token)

    if relative_path in indexed_paths:
        return relative_path
    return None


def _absolute_path_to_repo_relative(path: Path, repo_root: Path) -> str | None:
    root = repo_root.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    try:
        return resolved_path.relative_to(root).as_posix()
    except ValueError:
        return None


def _normalize_repo_relative_path(path: str) -> str | None:
    normalized_path = posixpath.normpath(path)
    if normalized_path in {"", "."}:
        return None
    if normalized_path == ".." or normalized_path.startswith("../"):
        return None
    return normalized_path


def _unique_file_terms(pairs: Iterable[tuple[str, str]]) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for term, path in pairs:
        grouped.setdefault(term, []).append(path)
    return {
        term: paths[0]
        for term, paths in grouped.items()
        if len(set(paths)) == 1
    }


def _first_ident_positions(text: str) -> dict[str, int]:
    positions = {}
    for match in re.finditer(r"\w+", text):
        positions.setdefault(match.group(0), match.start())
    return positions


def _path_like_idents(text: str) -> set[str]:
    idents = set()
    for _, token in _iter_clean_tokens(text):
        if _is_path_like(token):
            idents.update(extract_mentioned_idents(token))
    return idents


def _dedupe_paths_by_prompt_order(
    candidates: Iterable[tuple[int, int, str]],
) -> tuple[str, ...]:
    paths = []
    seen = set()
    for _, _, path in sorted(candidates):
        if path not in seen:
            paths.append(path)
            seen.add(path)
    return tuple(paths)


def _path_term_index(indexed_paths: tuple[str, ...]) -> Mapping[str, tuple[str, ...]]:
    term_paths: dict[str, set[str]] = {}
    for path in indexed_paths:
        repo_path = PurePosixPath(path)
        terms = (*repo_path.parts, repo_path.name, repo_path.stem)
        for term in terms:
            term_paths.setdefault(term.lower(), set()).add(path)

    return {
        term: tuple(sorted(paths))
        for term, paths in sorted(term_paths.items())
    }
