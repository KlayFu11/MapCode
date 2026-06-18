"""MapEngine-owned data transfer objects."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DefinitionRecord:
    name: str
    path: str
    line: int
    kind: str


@dataclass(frozen=True)
class ReferenceRecord:
    name: str
    path: str
    line: int


@dataclass(frozen=True)
class FileRecord:
    path: str
    mtime_ns: int
    size: int
    parser_version: str
