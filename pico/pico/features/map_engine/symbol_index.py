"""Tree-sitter symbol extraction for MapEngine."""

from __future__ import annotations

from collections.abc import Iterator
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Literal

from tree_sitter import Node
from tree_sitter import Query
from tree_sitter import QueryCursor
from tree_sitter import Tree
from tree_sitter_language_pack import get_language
from tree_sitter_language_pack import get_parser

from pico.features.map_engine.models import DefinitionRecord
from pico.features.map_engine.models import ReferenceRecord

PYTHON_TAGS_QUERY_PATH = Path(__file__).with_name("queries") / "python-tags.scm"

DEFINITION_CAPTURE_PREFIX = "name.definition."
REFERENCE_CAPTURE_PREFIX = "name.reference."
DEFINITION_KIND_BY_CAPTURE = {
    "name.definition.class": "class",
    "name.definition.constant": "constant",
    "name.definition.function": "function",
}
REFERENCE_CAPTURE_NAMES = frozenset({"name.reference.call"})

SymbolParseSkipReason = Literal[
    "read_failed",
    "decode_failed",
    "parse_failed",
    "query_failed",
]


@dataclass(frozen=True)
class SkippedSymbolFile:
    path: str
    reason: SymbolParseSkipReason


@dataclass(frozen=True)
class ParsedSourceFile:
    path: str
    definitions: tuple[DefinitionRecord, ...]
    references: tuple[ReferenceRecord, ...]


@dataclass(frozen=True)
class SymbolParseResult:
    parsed_files: tuple[ParsedSourceFile, ...]
    skipped_files: tuple[SkippedSymbolFile, ...]


class SymbolParseError(RuntimeError):
    def __init__(self, reason: SymbolParseSkipReason) -> None:
        super().__init__(reason)
        self.reason = reason


def extract_python_definitions(
    source: str | bytes,
    repo_relative_path: str,
) -> tuple[DefinitionRecord, ...]:
    return _parse_python_source(source, repo_relative_path).definitions


def extract_python_references(
    source: str | bytes,
    repo_relative_path: str,
) -> tuple[ReferenceRecord, ...]:
    return _parse_python_source(source, repo_relative_path).references


def parse_python_source_files(
    repo_root: str | Path,
    source_paths: Sequence[str],
) -> SymbolParseResult:
    root = Path(repo_root)
    parsed_files = []
    skipped_files = []

    for relative_path in source_paths:
        try:
            source = _read_python_source(root / relative_path)
            parsed_files.append(_parse_python_source(source, relative_path))
        except OSError:
            skipped_files.append(SkippedSymbolFile(relative_path, "read_failed"))
        except UnicodeDecodeError:
            skipped_files.append(SkippedSymbolFile(relative_path, "decode_failed"))
        except SymbolParseError as exc:
            skipped_files.append(SkippedSymbolFile(relative_path, exc.reason))

    return SymbolParseResult(
        parsed_files=tuple(parsed_files),
        skipped_files=tuple(skipped_files),
    )


def _parse_python_source(
    source: str | bytes,
    repo_relative_path: str,
) -> ParsedSourceFile:
    source_bytes = _source_to_bytes(source)
    tree = _parse_tree(source_bytes)
    captures = _query_tree(tree.root_node)

    return ParsedSourceFile(
        path=repo_relative_path,
        definitions=_definition_records(captures, repo_relative_path),
        references=_reference_records(captures, repo_relative_path),
    )


def _definition_records(
    captures: Any,
    repo_relative_path: str,
) -> tuple[DefinitionRecord, ...]:
    definitions = [
        DefinitionRecord(
            name=_node_text(node),
            path=repo_relative_path,
            line=node.start_point[0],
            kind=kind,
        )
        for capture_name, node in _iter_capture_nodes(captures)
        if capture_name.startswith(DEFINITION_CAPTURE_PREFIX)
        if (kind := DEFINITION_KIND_BY_CAPTURE.get(capture_name)) is not None
    ]

    return tuple(
        sorted(
            definitions,
            key=lambda definition: (
                definition.line,
                definition.name,
                definition.kind,
            ),
        )
    )


def _reference_records(
    captures: Any,
    repo_relative_path: str,
) -> tuple[ReferenceRecord, ...]:
    references = [
        ReferenceRecord(
            name=_node_text(node),
            path=repo_relative_path,
            line=node.start_point[0],
        )
        for capture_name, node in _iter_capture_nodes(captures)
        if capture_name.startswith(REFERENCE_CAPTURE_PREFIX)
        if capture_name in REFERENCE_CAPTURE_NAMES
    ]

    return tuple(
        sorted(
            references,
            key=lambda reference: (
                reference.line,
                reference.name,
            ),
        )
    )


def _source_to_bytes(source: str | bytes) -> bytes:
    if isinstance(source, bytes):
        return source
    return source.encode("utf-8", errors="surrogateescape")


def _read_python_source(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _parse_tree(source_bytes: bytes) -> Tree:
    try:
        parser = get_parser("python")
        return parser.parse(source_bytes)
    except Exception as exc:
        raise SymbolParseError("parse_failed") from exc


def _query_tree(root_node: Node) -> Any:
    try:
        query = Query(get_language("python"), _load_python_query_text())
        return _run_query_captures(query, root_node)
    except Exception as exc:
        raise SymbolParseError("query_failed") from exc


def _load_python_query_text() -> str:
    return PYTHON_TAGS_QUERY_PATH.read_text(encoding="utf-8")


def _run_query_captures(query: Query, root_node: Node) -> Any:
    return QueryCursor(query).captures(root_node)


def _iter_capture_nodes(captures: Any) -> Iterator[tuple[str, Node]]:
    if isinstance(captures, dict):
        for capture_name, nodes in captures.items():
            for node in nodes:
                yield capture_name, node
        return

    for node, capture_name in captures:
        yield capture_name, node


def _node_text(node: Node) -> str:
    text = node.text
    if text is None:
        return ""
    return text.decode("utf-8", errors="surrogateescape")
