"""Tree-sitter symbol extraction for MapEngine."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from tree_sitter import Node
from tree_sitter import Query
from tree_sitter import QueryCursor
from tree_sitter_language_pack import get_language
from tree_sitter_language_pack import get_parser

from pico.features.map_engine.models import DefinitionRecord

PYTHON_TAGS_QUERY_PATH = Path(__file__).with_name("queries") / "python-tags.scm"

DEFINITION_CAPTURE_PREFIX = "name.definition."
DEFINITION_KIND_BY_CAPTURE = {
    "name.definition.class": "class",
    "name.definition.constant": "constant",
    "name.definition.function": "function",
}


def extract_python_definitions(
    source: str | bytes,
    repo_relative_path: str,
) -> tuple[DefinitionRecord, ...]:
    source_bytes = _source_to_bytes(source)
    parser = get_parser("python")
    tree = parser.parse(source_bytes)
    query = Query(get_language("python"), _load_python_query_text())

    definitions = [
        DefinitionRecord(
            name=_node_text(node),
            path=repo_relative_path,
            line=node.start_point[0],
            kind=kind,
        )
        for capture_name, node in _iter_capture_nodes(
            _run_query_captures(query, tree.root_node)
        )
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


def _source_to_bytes(source: str | bytes) -> bytes:
    if isinstance(source, bytes):
        return source
    return source.encode("utf-8", errors="surrogateescape")


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
