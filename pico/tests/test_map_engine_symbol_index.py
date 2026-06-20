from pathlib import Path

from pico.features.map_engine.models import DefinitionRecord
from pico.features.map_engine.symbol_index import (
    PYTHON_TAGS_QUERY_PATH,
    extract_python_definitions,
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
