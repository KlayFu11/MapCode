from dataclasses import FrozenInstanceError

import pytest

from pico.features.map_engine.models import (
    DefinitionRecord,
    FileRecord,
    ReferenceRecord,
)


def test_definition_record_matches_symbol_index_contract():
    record = DefinitionRecord(
        name="JWTAuth",
        path="pico/auth.py",
        line=0,
        kind="class",
    )

    assert record.name == "JWTAuth"
    assert record.path == "pico/auth.py"
    assert record.line == 0
    assert record.kind == "class"


def test_reference_record_matches_symbol_index_contract():
    record = ReferenceRecord(
        name="JWTAuth",
        path="pico/api.py",
        line=12,
    )

    assert record.name == "JWTAuth"
    assert record.path == "pico/api.py"
    assert record.line == 12


def test_file_record_matches_symbol_index_contract():
    record = FileRecord(
        path="pico/auth.py",
        mtime_ns=1_725_000_000,
        size=4_096,
        parser_version="mapcode-python-tags-v1",
    )

    assert record.path == "pico/auth.py"
    assert record.mtime_ns == 1_725_000_000
    assert record.size == 4_096
    assert record.parser_version == "mapcode-python-tags-v1"


def test_records_are_immutable_value_objects():
    left = DefinitionRecord(
        name="build_index",
        path="pico/features/map_engine/symbol_index.py",
        line=7,
        kind="function",
    )
    right = DefinitionRecord(
        name="build_index",
        path="pico/features/map_engine/symbol_index.py",
        line=7,
        kind="function",
    )

    assert left == right

    with pytest.raises(FrozenInstanceError):
        left.line = 8


def test_line_fields_are_zero_based():
    definition = DefinitionRecord(
        name="first_symbol",
        path="pico/first.py",
        line=0,
        kind="function",
    )
    reference = ReferenceRecord(
        name="first_symbol",
        path="pico/second.py",
        line=0,
    )

    assert definition.line == 0
    assert reference.line == 0


def test_paths_are_repo_relative_strings():
    definition = DefinitionRecord(
        name="Settings",
        path="pico/config/settings.py",
        line=4,
        kind="class",
    )
    file_record = FileRecord(
        path="pico/config/settings.py",
        mtime_ns=10,
        size=200,
        parser_version="mapcode-python-tags-v1",
    )

    assert definition.path == "pico/config/settings.py"
    assert file_record.path == "pico/config/settings.py"
    assert not definition.path.startswith("/")
    assert not file_record.path.startswith("/")
