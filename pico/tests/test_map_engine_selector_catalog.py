from math import ceil

from pico.features.map_engine import selector_catalog
from pico.features.map_engine.models import CacheEvidence
from pico.features.map_engine.models import DefinitionRecord
from pico.features.map_engine.models import FileRecord
from pico.features.map_engine.selector_catalog import build_selector_catalog
from pico.features.map_engine.symbol_index import SymbolIndex


def _file_record(path: str) -> FileRecord:
    return FileRecord(
        path=path,
        mtime_ns=1,
        size=1,
        parser_version="test",
        query_version="test",
        schema_version="test",
    )


def _definition(
    name: str,
    path: str,
    line: int,
    kind: str = "function",
) -> DefinitionRecord:
    return DefinitionRecord(name=name, path=path, line=line, kind=kind)


def _symbol_index(
    *,
    paths: tuple[str, ...],
    definitions_by_file: dict[str, tuple[DefinitionRecord, ...]] | None = None,
) -> SymbolIndex:
    definitions_by_file = definitions_by_file or {}
    definitions_by_symbol: dict[str, list[DefinitionRecord]] = {}
    for definitions in definitions_by_file.values():
        for definition in definitions:
            definitions_by_symbol.setdefault(definition.name, []).append(definition)

    return SymbolIndex(
        all_defs=frozenset(definitions_by_symbol),
        definitions_by_symbol={
            name: tuple(records)
            for name, records in sorted(definitions_by_symbol.items())
        },
        definitions_by_file=definitions_by_file,
        references_by_file={},
        file_records={path: _file_record(path) for path in paths},
        index_snapshot_id="snapshot-test",
        skipped_files=(),
        cache_status=CacheEvidence(
            read_status="miss",
            write_status="not_needed",
            reused_files=(),
            parsed_files=(),
            skipped_files=(),
        ),
    )


def _line_with(lines: list[str], *parts: str) -> str:
    for line in lines:
        if all(part in line for part in parts):
            return line
    raise AssertionError(f"expected a line containing {parts!r}")


def test_build_selector_catalog_uses_snapshot_paths_and_stable_render_order():
    symbol_index = _symbol_index(
        paths=(
            "pkg/zeta.py",
            "pkg/empty.py",
            "pkg/alpha.py",
        ),
        definitions_by_file={
            "pkg/zeta.py": (
                _definition("zeta", "pkg/zeta.py", line=10, kind="function"),
                _definition("Alpha", "pkg/zeta.py", line=3, kind="class"),
            ),
            "pkg/alpha.py": (
                _definition("build", "pkg/alpha.py", line=1, kind="function"),
            ),
        },
    )

    catalog = build_selector_catalog(symbol_index)

    assert catalog.index_snapshot_id == "snapshot-test"
    assert catalog.candidate_paths == (
        "pkg/alpha.py",
        "pkg/empty.py",
        "pkg/zeta.py",
    )
    assert catalog.rendered_paths == catalog.candidate_paths
    assert catalog.file_count == 3
    assert catalog.definition_count == 3
    assert catalog.rendered_file_count == 3
    assert catalog.rendered_definition_count == 3
    assert catalog.estimated_tokens == ceil(len(catalog.rendered_text) / 4)
    assert catalog.truncated is False

    lines = catalog.rendered_text.splitlines()
    assert lines.index("pkg/alpha.py:") < lines.index("pkg/empty.py:")
    assert lines.index("pkg/empty.py:") < lines.index("pkg/zeta.py:")
    zeta_block = lines[lines.index("pkg/zeta.py:") + 1 :]
    alpha_line = _line_with(zeta_block, "class", "Alpha", "3")
    zeta_line = _line_with(zeta_block, "function", "zeta", "10")
    assert zeta_block.index(alpha_line) < zeta_block.index(zeta_line)


def test_build_selector_catalog_limits_rendered_definitions_per_file(monkeypatch):
    monkeypatch.setattr(selector_catalog, "SELECTOR_CATALOG_MAX_DEFS_PER_FILE", 2)
    symbol_index = _symbol_index(
        paths=("pkg/service.py",),
        definitions_by_file={
            "pkg/service.py": (
                _definition("third", "pkg/service.py", line=30),
                _definition("first", "pkg/service.py", line=10),
                _definition("second", "pkg/service.py", line=20),
            ),
        },
    )

    catalog = build_selector_catalog(symbol_index)

    assert catalog.candidate_paths == ("pkg/service.py",)
    assert catalog.rendered_paths == ("pkg/service.py",)
    assert catalog.definition_count == 3
    assert catalog.rendered_definition_count == 2
    assert catalog.truncated is True
    lines = catalog.rendered_text.splitlines()
    assert _line_with(lines, "function", "first", "10")
    assert _line_with(lines, "function", "second", "20")
    assert not any("third" in line for line in lines)


def test_build_selector_catalog_limits_rendered_files(monkeypatch):
    monkeypatch.setattr(selector_catalog, "SELECTOR_CATALOG_MAX_FILES", 2)
    symbol_index = _symbol_index(
        paths=(
            "pkg/alpha.py",
            "pkg/beta.py",
            "pkg/gamma.py",
        )
    )

    catalog = build_selector_catalog(symbol_index)

    assert catalog.candidate_paths == (
        "pkg/alpha.py",
        "pkg/beta.py",
        "pkg/gamma.py",
    )
    assert catalog.rendered_paths == (
        "pkg/alpha.py",
        "pkg/beta.py",
    )
    assert catalog.rendered_file_count == 2
    assert catalog.rendered_definition_count == 0
    assert "pkg/gamma.py:" not in catalog.rendered_text
    assert catalog.truncated is True


def test_build_selector_catalog_head_clips_complete_file_blocks_for_token_budget(
    monkeypatch,
):
    monkeypatch.setattr(selector_catalog, "SELECTOR_CATALOG_MAX_TOKENS", 8)
    first_path = "aaaaaaaaaaaaaaaaaaaaaaaa.py"
    symbol_index = _symbol_index(
        paths=(
            first_path,
            "bbbb.py",
        )
    )

    catalog = build_selector_catalog(symbol_index)

    assert catalog.candidate_paths == (
        first_path,
        "bbbb.py",
    )
    assert catalog.rendered_paths == (first_path,)
    assert catalog.rendered_text == f"{first_path}:"
    assert catalog.rendered_file_count == 1
    assert catalog.rendered_definition_count == 0
    assert catalog.estimated_tokens == ceil(len(catalog.rendered_text) / 4)
    assert catalog.truncated is True
