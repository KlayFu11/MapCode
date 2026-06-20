from pathlib import Path

import pico.features.map_engine.symbol_index as symbol_index
from pico.features.map_engine.models import DefinitionRecord
from pico.features.map_engine.models import ReferenceRecord
from pico.features.map_engine.symbol_index import (
    PYTHON_TAGS_QUERY_PATH,
    ParsedSourceFile,
    SkippedSymbolFile,
    extract_python_definitions,
    extract_python_references,
    parse_python_source_files,
)


def test_extracts_python_definitions_with_zero_based_lines():
    source = """\
API_TIMEOUT = 30
DEFAULT_NAME = "mapcode"


class Greeter:
    def greet(self, name):
        return format_name(name)


async def build_async():
    return Greeter()


def format_name(value):
    return value.strip().title()
"""

    definitions = extract_python_definitions(source, "pkg/service.py")

    assert definitions == (
        DefinitionRecord(
            name="API_TIMEOUT",
            path="pkg/service.py",
            line=0,
            kind="constant",
        ),
        DefinitionRecord(
            name="DEFAULT_NAME",
            path="pkg/service.py",
            line=1,
            kind="constant",
        ),
        DefinitionRecord(
            name="Greeter",
            path="pkg/service.py",
            line=4,
            kind="class",
        ),
        DefinitionRecord(
            name="greet",
            path="pkg/service.py",
            line=5,
            kind="function",
        ),
        DefinitionRecord(
            name="build_async",
            path="pkg/service.py",
            line=9,
            kind="function",
        ),
        DefinitionRecord(
            name="format_name",
            path="pkg/service.py",
            line=13,
            kind="function",
        ),
    )


def test_definition_extraction_does_not_return_references():
    source = """\
class Greeter:
    pass


def run():
    return Greeter()
"""

    definitions = extract_python_definitions(source, "pkg/app.py")

    assert [definition.name for definition in definitions] == ["Greeter", "run"]


def test_extracts_python_call_references_with_zero_based_lines():
    source = """\
class Greeter:
    def greet(self, name):
        return format_name(name)


def run(value):
    greeter = Greeter()
    return greeter.greet(value.strip())
"""

    references = extract_python_references(source, "pkg/app.py")

    assert references == (
        ReferenceRecord(name="format_name", path="pkg/app.py", line=2),
        ReferenceRecord(name="Greeter", path="pkg/app.py", line=6),
        ReferenceRecord(name="greet", path="pkg/app.py", line=7),
        ReferenceRecord(name="strip", path="pkg/app.py", line=7),
    )


def test_constant_definitions_are_module_level_assignments():
    source = """\
MODULE_CONST = 1


class Settings:
    CLASS_CONST = 2
"""

    definitions = extract_python_definitions(source, "pkg/settings.py")

    assert definitions == (
        DefinitionRecord(
            name="MODULE_CONST",
            path="pkg/settings.py",
            line=0,
            kind="constant",
        ),
        DefinitionRecord(
            name="Settings",
            path="pkg/settings.py",
            line=3,
            kind="class",
        ),
    )


def test_python_tags_query_is_mapcode_owned_with_aider_attribution():
    query_path = Path(PYTHON_TAGS_QUERY_PATH)
    query_text = query_path.read_text(encoding="utf-8")

    assert query_path.name == "python-tags.scm"
    assert "Adapted from Aider" in query_text
    assert "Apache License 2.0" in query_text


def test_parse_python_source_files_records_read_and_decode_failures(tmp_path: Path):
    (tmp_path / "good.py").write_text(
        "class Greeter:\n    pass\n\n\ndef run():\n    return Greeter()\n",
        encoding="utf-8",
    )
    (tmp_path / "bad.py").write_bytes(b"\xff")

    result = parse_python_source_files(
        tmp_path,
        ("good.py", "missing.py", "bad.py"),
    )

    assert result.parsed_files == (
        ParsedSourceFile(
            path="good.py",
            definitions=(
                DefinitionRecord(name="Greeter", path="good.py", line=0, kind="class"),
                DefinitionRecord(name="run", path="good.py", line=4, kind="function"),
            ),
            references=(ReferenceRecord(name="Greeter", path="good.py", line=5),),
        ),
    )
    assert result.skipped_files == (
        SkippedSymbolFile(path="missing.py", reason="read_failed"),
        SkippedSymbolFile(path="bad.py", reason="decode_failed"),
    )


def test_parse_python_source_files_records_query_failure_and_continues(
    tmp_path: Path,
    monkeypatch,
):
    (tmp_path / "good.py").write_text("def good():\n    return call()\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("def broken():\n    return call()\n", encoding="utf-8")
    original_run_query_captures = symbol_index._run_query_captures

    def fake_run_query_captures(query, root_node):
        if b"broken" in root_node.text:
            raise RuntimeError("query failed")
        return original_run_query_captures(query, root_node)

    monkeypatch.setattr(symbol_index, "_run_query_captures", fake_run_query_captures)

    result = parse_python_source_files(tmp_path, ("good.py", "broken.py"))

    assert result.parsed_files == (
        ParsedSourceFile(
            path="good.py",
            definitions=(
                DefinitionRecord(name="good", path="good.py", line=0, kind="function"),
            ),
            references=(ReferenceRecord(name="call", path="good.py", line=1),),
        ),
    )
    assert result.skipped_files == (
        SkippedSymbolFile(path="broken.py", reason="query_failed"),
    )


def test_parse_python_source_files_records_parse_failure_and_continues(
    tmp_path: Path,
    monkeypatch,
):
    (tmp_path / "good.py").write_text("def good():\n    return call()\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("def broken():\n    return call()\n", encoding="utf-8")
    original_get_parser = symbol_index.get_parser
    original_parser = original_get_parser("python")

    class FakeParser:
        def parse(self, source_bytes):
            if b"broken" in source_bytes:
                raise RuntimeError("parse failed")
            return original_parser.parse(source_bytes)

    monkeypatch.setattr(symbol_index, "get_parser", lambda language: FakeParser())

    result = parse_python_source_files(tmp_path, ("good.py", "broken.py"))

    assert result.parsed_files == (
        ParsedSourceFile(
            path="good.py",
            definitions=(
                DefinitionRecord(name="good", path="good.py", line=0, kind="function"),
            ),
            references=(ReferenceRecord(name="call", path="good.py", line=1),),
        ),
    )
    assert result.skipped_files == (
        SkippedSymbolFile(path="broken.py", reason="parse_failed"),
    )
