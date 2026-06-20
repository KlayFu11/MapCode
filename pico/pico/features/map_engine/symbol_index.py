"""Tree-sitter symbol extraction for MapEngine."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any
from typing import Literal

from tree_sitter import Node
from tree_sitter import Query
from tree_sitter import QueryCursor
from tree_sitter import Tree
from tree_sitter_language_pack import get_language
from tree_sitter_language_pack import get_parser

from pico.features.map_engine.config import MAP_ENGINE_SCHEMA_VERSION
from pico.features.map_engine.config import PARSER_VERSION
from pico.features.map_engine.config import QUERY_VERSION
from pico.features.map_engine.models import DefinitionRecord
from pico.features.map_engine.models import FileRecord
from pico.features.map_engine.models import ReferenceRecord

PYTHON_TAGS_QUERY_PATH = Path(__file__).with_name("queries") / "python-tags.scm"
MAP_ENGINE_CACHE_DIR = Path(".pico") / "map_engine"
INDEX_CACHE_FILE_NAME = "index.json"
CACHE_META_FILE_NAME = "cache.meta.json"

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


@dataclass(frozen=True)
class _CachedParsedFile:
    file_record: FileRecord
    parsed_file: ParsedSourceFile


@dataclass(frozen=True)
class _SymbolIndexCache:
    files: Mapping[str, _CachedParsedFile]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "files",
            MappingProxyType(dict(self.files)),
        )


@dataclass(frozen=True)
class SymbolIndex:
    all_defs: frozenset[str]
    definitions_by_symbol: Mapping[str, tuple[DefinitionRecord, ...]]
    definitions_by_file: Mapping[str, tuple[DefinitionRecord, ...]]
    references_by_file: Mapping[str, tuple[ReferenceRecord, ...]]
    file_records: Mapping[str, FileRecord]
    index_snapshot_id: str
    skipped_files: tuple[SkippedSymbolFile, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "definitions_by_symbol",
            MappingProxyType(
                {
                    symbol: tuple(records)
                    for symbol, records in self.definitions_by_symbol.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "definitions_by_file",
            MappingProxyType(
                {
                    path: tuple(records)
                    for path, records in self.definitions_by_file.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "references_by_file",
            MappingProxyType(
                {
                    path: tuple(records)
                    for path, records in self.references_by_file.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "file_records",
            MappingProxyType(dict(self.file_records)),
        )


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


def build_symbol_index(
    repo_root: str | Path,
    source_paths: Sequence[str],
) -> SymbolIndex:
    root = Path(repo_root)
    ordered_source_paths = tuple(sorted(dict.fromkeys(source_paths)))
    cache = _load_symbol_index_cache(root)
    current_file_records = _current_file_records(root, ordered_source_paths)
    reused_files, paths_to_parse = _split_cache_hits(
        cache,
        current_file_records,
        ordered_source_paths,
    )
    parse_result = parse_python_source_files(root, paths_to_parse)
    parsed_files = tuple(
        sorted(
            (*reused_files, *parse_result.parsed_files),
            key=lambda file: file.path,
        )
    )
    file_records = {
        parsed_file.path: current_file_records.get(parsed_file.path)
        or _file_record_for_path(root, parsed_file.path)
        for parsed_file in parsed_files
    }

    index = _build_symbol_index(
        parsed_files=parsed_files,
        skipped_files=parse_result.skipped_files,
        file_records=file_records,
    )
    _write_symbol_index_cache(root, index, parsed_files)
    return index


def _build_symbol_index(
    parsed_files: Sequence[ParsedSourceFile],
    skipped_files: tuple[SkippedSymbolFile, ...],
    file_records: Mapping[str, FileRecord],
) -> SymbolIndex:
    return SymbolIndex(
        all_defs=frozenset(
            definition.name
            for parsed_file in parsed_files
            for definition in parsed_file.definitions
        ),
        definitions_by_symbol=_build_definitions_by_symbol(parsed_files),
        definitions_by_file=_build_definitions_by_file(parsed_files),
        references_by_file=_build_references_by_file(parsed_files),
        file_records=file_records,
        index_snapshot_id=_build_index_snapshot_id(file_records.values()),
        skipped_files=skipped_files,
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


def _build_definitions_by_symbol(
    parsed_files: Sequence[ParsedSourceFile],
) -> dict[str, tuple[DefinitionRecord, ...]]:
    grouped: dict[str, list[DefinitionRecord]] = {}
    for parsed_file in parsed_files:
        for definition in parsed_file.definitions:
            grouped.setdefault(definition.name, []).append(definition)

    return {
        symbol: tuple(
            sorted(
                records,
                key=lambda definition: (
                    definition.path,
                    definition.line,
                    definition.name,
                    definition.kind,
                ),
            )
        )
        for symbol, records in sorted(grouped.items())
    }


def _build_definitions_by_file(
    parsed_files: Sequence[ParsedSourceFile],
) -> dict[str, tuple[DefinitionRecord, ...]]:
    return {
        parsed_file.path: parsed_file.definitions
        for parsed_file in sorted(parsed_files, key=lambda file: file.path)
    }


def _build_references_by_file(
    parsed_files: Sequence[ParsedSourceFile],
) -> dict[str, tuple[ReferenceRecord, ...]]:
    return {
        parsed_file.path: parsed_file.references
        for parsed_file in sorted(parsed_files, key=lambda file: file.path)
    }


def _current_file_records(
    repo_root: Path,
    source_paths: Sequence[str],
) -> dict[str, FileRecord]:
    file_records = {}
    for relative_path in source_paths:
        try:
            file_records[relative_path] = _file_record_for_path(repo_root, relative_path)
        except OSError:
            pass
    return file_records


def _split_cache_hits(
    cache: _SymbolIndexCache | None,
    current_file_records: Mapping[str, FileRecord],
    source_paths: Sequence[str],
) -> tuple[tuple[ParsedSourceFile, ...], tuple[str, ...]]:
    if cache is None:
        return (), tuple(source_paths)

    reused_files = []
    paths_to_parse = []
    for relative_path in source_paths:
        current_record = current_file_records.get(relative_path)
        cached_file = cache.files.get(relative_path)
        if (
            current_record is not None
            and cached_file is not None
            and cached_file.file_record == current_record
        ):
            reused_files.append(cached_file.parsed_file)
        else:
            paths_to_parse.append(relative_path)

    return tuple(reused_files), tuple(paths_to_parse)


def _file_record_for_path(repo_root: Path, relative_path: str) -> FileRecord:
    stat_result = (repo_root / relative_path).stat()
    return FileRecord(
        path=relative_path,
        mtime_ns=stat_result.st_mtime_ns,
        size=stat_result.st_size,
        parser_version=PARSER_VERSION,
        query_version=QUERY_VERSION,
        schema_version=MAP_ENGINE_SCHEMA_VERSION,
    )


def _build_index_snapshot_id(file_records: Iterable[FileRecord]) -> str:
    payload = {
        "schema_version": MAP_ENGINE_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "query_version": QUERY_VERSION,
        "files": [
            {
                "path": record.path,
                "mtime_ns": record.mtime_ns,
                "size": record.size,
            }
            for record in sorted(file_records, key=lambda record: record.path)
        ],
    }
    digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return f"sha256:{digest}"


def _load_symbol_index_cache(repo_root: Path) -> _SymbolIndexCache | None:
    try:
        index_payload = json.loads(_index_cache_path(repo_root).read_text(encoding="utf-8"))
        meta_payload = json.loads(_cache_meta_path(repo_root).read_text(encoding="utf-8"))
        return _symbol_index_cache_from_payloads(index_payload, meta_payload)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _write_symbol_index_cache(
    repo_root: Path,
    index: SymbolIndex,
    parsed_files: Sequence[ParsedSourceFile],
) -> None:
    try:
        cache_dir = _cache_dir_for_repo(repo_root)
        cache_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            cache_dir / INDEX_CACHE_FILE_NAME,
            _index_cache_payload(index, parsed_files),
        )
        _write_json(
            cache_dir / CACHE_META_FILE_NAME,
            _cache_meta_payload(index.file_records.values(), index.index_snapshot_id),
        )
    except OSError:
        return


def _symbol_index_cache_from_payloads(
    index_payload: object,
    meta_payload: object,
) -> _SymbolIndexCache:
    if not (
        isinstance(index_payload, dict)
        and isinstance(meta_payload, dict)
        and _cache_payload_versions_match(index_payload)
        and _cache_payload_versions_match(meta_payload)
        and index_payload.get("index_snapshot_id")
        == meta_payload.get("index_snapshot_id")
    ):
        raise ValueError("invalid symbol index cache")

    meta_records = {
        record.path: record
        for record in _file_records_from_meta_payload(meta_payload)
    }
    cached_files = {}
    for file_payload in _payload_list(index_payload, "files"):
        parsed_file = _parsed_file_from_index_payload(file_payload)
        meta_record = meta_records.get(parsed_file.path)
        if meta_record is None:
            continue
        payload_record = _file_record_from_index_payload(file_payload)
        if payload_record == meta_record:
            cached_files[parsed_file.path] = _CachedParsedFile(
                file_record=payload_record,
                parsed_file=parsed_file,
            )

    return _SymbolIndexCache(files=cached_files)


def _cache_payload_versions_match(payload: Mapping[str, object]) -> bool:
    return (
        payload.get("schema_version") == MAP_ENGINE_SCHEMA_VERSION
        and payload.get("parser_version") == PARSER_VERSION
        and payload.get("query_version") == QUERY_VERSION
    )


def _file_records_from_meta_payload(payload: Mapping[str, object]) -> tuple[FileRecord, ...]:
    return tuple(
        _file_record_from_meta_payload(file_payload)
        for file_payload in _payload_list(payload, "files")
    )


def _parsed_file_from_index_payload(payload: Mapping[str, object]) -> ParsedSourceFile:
    path = str(payload["path"])
    return ParsedSourceFile(
        path=path,
        definitions=tuple(
            _definition_record_from_payload(definition_payload)
            for definition_payload in _payload_list(payload, "definitions")
        ),
        references=tuple(
            _reference_record_from_payload(reference_payload)
            for reference_payload in _payload_list(payload, "references")
        ),
    )


def _file_record_from_index_payload(payload: Mapping[str, object]) -> FileRecord:
    return FileRecord(
        path=str(payload["path"]),
        mtime_ns=int(payload["mtime_ns"]),
        size=int(payload["size"]),
        parser_version=PARSER_VERSION,
        query_version=QUERY_VERSION,
        schema_version=MAP_ENGINE_SCHEMA_VERSION,
    )


def _file_record_from_meta_payload(payload: Mapping[str, object]) -> FileRecord:
    return FileRecord(
        path=str(payload["path"]),
        mtime_ns=int(payload["mtime_ns"]),
        size=int(payload["size"]),
        parser_version=str(payload["parser_version"]),
        query_version=str(payload["query_version"]),
        schema_version=str(payload["schema_version"]),
    )


def _definition_record_from_payload(payload: Mapping[str, object]) -> DefinitionRecord:
    return DefinitionRecord(
        name=str(payload["name"]),
        path=str(payload["path"]),
        line=int(payload["line"]),
        kind=str(payload["kind"]),
    )


def _reference_record_from_payload(payload: Mapping[str, object]) -> ReferenceRecord:
    return ReferenceRecord(
        name=str(payload["name"]),
        path=str(payload["path"]),
        line=int(payload["line"]),
    )


def _index_cache_payload(
    index: SymbolIndex,
    parsed_files: Sequence[ParsedSourceFile],
) -> dict[str, object]:
    return {
        "schema_version": MAP_ENGINE_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "query_version": QUERY_VERSION,
        "index_snapshot_id": index.index_snapshot_id,
        "files": [
            _parsed_file_cache_payload(parsed_file, index.file_records[parsed_file.path])
            for parsed_file in sorted(parsed_files, key=lambda file: file.path)
        ],
    }


def _parsed_file_cache_payload(
    parsed_file: ParsedSourceFile,
    file_record: FileRecord,
) -> dict[str, object]:
    return {
        "path": parsed_file.path,
        "mtime_ns": file_record.mtime_ns,
        "size": file_record.size,
        "definitions": [
            _definition_record_payload(definition)
            for definition in parsed_file.definitions
        ],
        "references": [
            _reference_record_payload(reference)
            for reference in parsed_file.references
        ],
    }


def _cache_meta_payload(
    file_records: Iterable[FileRecord],
    index_snapshot_id: str,
) -> dict[str, object]:
    return {
        "schema_version": MAP_ENGINE_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "query_version": QUERY_VERSION,
        "index_snapshot_id": index_snapshot_id,
        "files": [
            _file_record_payload(record)
            for record in sorted(file_records, key=lambda record: record.path)
        ],
    }


def _file_record_payload(record: FileRecord) -> dict[str, object]:
    return {
        "path": record.path,
        "mtime_ns": record.mtime_ns,
        "size": record.size,
        "parser_version": record.parser_version,
        "query_version": record.query_version,
        "schema_version": record.schema_version,
    }


def _definition_record_payload(record: DefinitionRecord) -> dict[str, object]:
    return {
        "name": record.name,
        "path": record.path,
        "line": record.line,
        "kind": record.kind,
    }


def _reference_record_payload(record: ReferenceRecord) -> dict[str, object]:
    return {
        "name": record.name,
        "path": record.path,
        "line": record.line,
    }


def _payload_list(
    payload: Mapping[str, object],
    key: str,
) -> tuple[Mapping[str, object], ...]:
    values = payload[key]
    if not isinstance(values, list):
        raise ValueError(f"{key} must be a list")
    if not all(isinstance(value, dict) for value in values):
        raise ValueError(f"{key} entries must be objects")
    return tuple(values)


def _cache_dir_for_repo(repo_root: Path) -> Path:
    return repo_root / MAP_ENGINE_CACHE_DIR


def _index_cache_path(repo_root: Path) -> Path:
    return _cache_dir_for_repo(repo_root) / INDEX_CACHE_FILE_NAME


def _cache_meta_path(repo_root: Path) -> Path:
    return _cache_dir_for_repo(repo_root) / CACHE_META_FILE_NAME


def _write_json(path: Path, value: object) -> None:
    path.write_text(_canonical_json(value).decode("utf-8"), encoding="utf-8")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


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
