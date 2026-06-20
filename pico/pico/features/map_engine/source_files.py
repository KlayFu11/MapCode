"""Git index path enumeration for MapEngine."""

import subprocess
from pathlib import Path

GIT_COMMAND_TIMEOUT_SECONDS = 5


def list_git_index_paths(cwd: str | Path) -> tuple[str, ...]:
    repo_root = _git_repo_root(cwd)
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
