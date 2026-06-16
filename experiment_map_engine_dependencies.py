"""Validate MapEngine dependency compatibility outside Pico runtime.

This script is intentionally standalone. It does not import Pico runtime code or
Aider modules; it only verifies the third-party APIs MapEngine plans to use.
"""

from __future__ import annotations

import math
from pathlib import Path
from tempfile import TemporaryDirectory

import networkx as nx
from grep_ast import TreeContext, filename_to_lang
from tree_sitter import Query, QueryCursor
from tree_sitter_language_pack import get_language, get_parser


PYTHON_QUERY = """
(function_definition
  name: (identifier) @name.definition.function) @definition.function

(class_definition
  name: (identifier) @name.definition.class) @definition.class

(call
  function: (identifier) @name.reference.call) @reference.call
"""

SAMPLE_CODE = """\
class Greeter:
    def greet(self, name):
        return format_name(name)


def format_name(value):
    return value.strip().title()


def run():
    greeter = Greeter()
    return greeter.greet("mapcode")
"""


def run_captures(query: Query, root_node):
    if hasattr(query, "captures"):
        return query.captures(root_node)
    cursor = QueryCursor(query)
    return cursor.captures(root_node)


def normalize_captures(captures) -> list[tuple[str, int, str]]:
    normalized: list[tuple[str, int, str]] = []

    if isinstance(captures, dict):
        for capture_name, nodes in captures.items():
            for node in nodes:
                normalized.append((capture_name, node.start_point[0], node.text.decode("utf-8")))
        return sorted(normalized)

    for node, capture_name in captures:
        normalized.append((capture_name, node.start_point[0], node.text.decode("utf-8")))
    return sorted(normalized)


def validate_tree_sitter() -> list[tuple[str, int, str]]:
    parser = get_parser("python")
    tree = parser.parse(SAMPLE_CODE.encode("utf-8"))
    language = get_language("python")
    query = Query(language, PYTHON_QUERY)
    captures = normalize_captures(run_captures(query, tree.root_node))

    names = {text for capture_name, _, text in captures if capture_name.startswith("name.")}
    required = {"Greeter", "greet", "format_name", "run"}
    missing = required - names
    if missing:
        raise AssertionError(f"missing tree-sitter captures: {sorted(missing)}")

    return captures


def validate_tree_context() -> str:
    with TemporaryDirectory() as temp_dir:
        sample_path = Path(temp_dir) / "sample.py"
        sample_path.write_text(SAMPLE_CODE, encoding="utf-8")
        lines = SAMPLE_CODE.splitlines()
        context = TreeContext(
            str(sample_path),
            SAMPLE_CODE,
            color=False,
            line_number=False,
            child_context=False,
            last_line=False,
            margin=0,
            mark_lois=True,
            loi_pad=0,
            show_top_of_file_parent_scope=False,
        )
        context.add_lines_of_interest(range(len(lines)))
        context.add_context()
        rendered = context.format()

    if "class Greeter" not in rendered or "def run" not in rendered:
        raise AssertionError("TreeContext did not render expected structure")

    lang = filename_to_lang("sample.py")
    if lang != "python":
        raise AssertionError(f"unexpected filename_to_lang result: {lang!r}")

    return rendered


def validate_pagerank() -> dict[str, float]:
    graph = nx.DiGraph()
    graph.add_weighted_edges_from(
        [
            ("sample.py", "helpers.py", 2.0),
            ("helpers.py", "sample.py", 1.0),
            ("cli.py", "sample.py", 1.0),
        ]
    )
    scores = nx.pagerank(graph, alpha=0.85, max_iter=100, tol=1e-6, weight="weight")
    personalized = nx.pagerank(
        graph,
        alpha=0.85,
        max_iter=100,
        tol=1e-6,
        weight="weight",
        personalization={"sample.py": 1.0, "helpers.py": 0.0, "cli.py": 0.0},
    )

    if not math.isclose(sum(scores.values()), 1.0, rel_tol=1e-6):
        raise AssertionError("PageRank scores are not normalized")
    if personalized["sample.py"] <= scores["sample.py"]:
        raise AssertionError("personalization did not boost sample.py")

    return scores


def main() -> None:
    captures = validate_tree_sitter()
    rendered = validate_tree_context()
    scores = validate_pagerank()

    print("tree_sitter_captures:", len(captures))
    print("tree_context_chars:", len(rendered))
    print("pagerank_top:", max(scores.items(), key=lambda item: item[1])[0])
    print("dependency_experiment: ok")


if __name__ == "__main__":
    main()
