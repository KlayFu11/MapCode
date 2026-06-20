"""Git index path enumeration for MapEngine."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Literal

GIT_COMMAND_TIMEOUT_SECONDS = 5
DENYLIST_DIR_NAMES = frozenset(
    {
        ".git",
        ".pico",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "build",
        "dist",
        "node_modules",
    }
)
DENYLIST_SUFFIXES = (".egg-info",)

SkipReason = Literal["missing", "denylisted", "non_python", "not_regular_file"]


class SourceFileDiscoveryError(RuntimeError):
    """Raised when Git index based source discovery cannot run."""


@dataclass(frozen=True)
class SkippedSourceFile:
    path: str
    reason: SkipReason


@dataclass(frozen=True)
class SourceFileSelection:
    source_paths: tuple[str, ...]
    skipped_files: tuple[SkippedSourceFile, ...]


def list_git_index_paths(cwd: str | Path) -> tuple[str, ...]:
    repo_root = _git_repo_root(cwd)
    return _list_git_index_paths_at_root(repo_root)


def list_python_source_files(cwd: str | Path) -> SourceFileSelection:
    try:
        repo_root = _git_repo_root(cwd)
        index_paths = _list_git_index_paths_at_root(repo_root)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SourceFileDiscoveryError("Git source file discovery failed") from exc

    source_paths = []
    skipped_files = []
    for relative_path in index_paths:
        skip_reason = _source_file_skip_reason(repo_root, relative_path)
        if skip_reason is None:
            source_paths.append(relative_path)
        else:
            skipped_files.append(SkippedSourceFile(relative_path, skip_reason))

    return SourceFileSelection(
        source_paths=tuple(source_paths),
        skipped_files=tuple(skipped_files),
    )


def _list_git_index_paths_at_root(repo_root: Path) -> tuple[str, ...]:
    output = _run_git(("ls-files", "--cached", "-z"), repo_root)
    paths = _decode_nul_separated_paths(output)

    return tuple(sorted(dict.fromkeys(paths)))


def _git_repo_root(cwd: str | Path) -> Path:
    output = _run_git(("rev-parse", "--show-toplevel"), Path(cwd))
    return Path(_decode_git_text(output).strip()).resolve()


def _run_git(args: tuple[str, ...], cwd: Path) -> bytes:
    result = subprocess.run(
        ("git", *args),
        cwd=cwd,
        capture_output=True,
        check=True,
        timeout=GIT_COMMAND_TIMEOUT_SECONDS,
    )
    return result.stdout


def _decode_nul_separated_paths(output: bytes) -> tuple[str, ...]:
    return tuple(
        _decode_git_text(path)
        for path in output.split(b"\0")
        if path
    )


def _decode_git_text(output: bytes) -> str:
    return output.decode("utf-8", errors="surrogateescape")


def _source_file_skip_reason(repo_root: Path, relative_path: str) -> SkipReason | None:
    absolute_path = repo_root / relative_path
    if not absolute_path.exists():
        return "missing"
    if _is_denylisted(relative_path):
        return "denylisted"
    if not relative_path.endswith(".py"):
        return "non_python"
    if not absolute_path.is_file():
        return "not_regular_file"
    return None


def _is_denylisted(relative_path: str) -> bool:
    parts = PurePosixPath(relative_path).parts
    return any(
        part in DENYLIST_DIR_NAMES
        or any(part.endswith(suffix) for suffix in DENYLIST_SUFFIXES)
        for part in parts
    )
