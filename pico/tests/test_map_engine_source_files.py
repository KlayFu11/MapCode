import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from pico.features.map_engine.source_files import list_git_index_paths


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )


def _write(repo: Path, relative_path: str, content: str = "value = 1\n") -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "mapcode@example.test")
    _git(tmp_path, "config", "user.name", "MapCode Test")
    _write(tmp_path, "tracked.py")
    _git(tmp_path, "add", "tracked.py")
    _git(tmp_path, "commit", "-m", "initial tracked file")
    return tmp_path


def test_lists_committed_tracked_paths(git_repo: Path):
    assert list_git_index_paths(git_repo) == ("tracked.py",)


def test_lists_staged_new_paths(git_repo: Path):
    _write(git_repo, "pkg/new_file.py")
    _git(git_repo, "add", "pkg/new_file.py")

    assert list_git_index_paths(git_repo) == (
        "pkg/new_file.py",
        "tracked.py",
    )


def test_excludes_untracked_paths(git_repo: Path):
    _write(git_repo, "untracked.py")

    assert list_git_index_paths(git_repo) == ("tracked.py",)


def test_preserves_path_with_space(git_repo: Path):
    _write(git_repo, "pkg/with space.py")
    _git(git_repo, "add", "pkg/with space.py")

    assert list_git_index_paths(git_repo) == (
        "pkg/with space.py",
        "tracked.py",
    )


def test_decodes_nul_separated_git_output_without_line_splitting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command == ("git", "rev-parse", "--show-toplevel"):
            return SimpleNamespace(stdout=f"{tmp_path}\n".encode())
        if command == ("git", "ls-files", "--cached", "-z"):
            return SimpleNamespace(
                stdout=b"pkg/with\nnewline.py\0pkg/with space.py\0"
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert list_git_index_paths(tmp_path / "pkg") == (
        "pkg/with\nnewline.py",
        "pkg/with space.py",
    )
    assert ("git", "ls-files", "--cached", "-z") in calls


def test_subdirectory_cwd_still_returns_repo_relative_paths(git_repo: Path):
    _write(git_repo, "pkg/subdir/module.py")
    _git(git_repo, "add", "pkg/subdir/module.py")

    cwd = git_repo / "pkg" / "subdir"

    assert list_git_index_paths(cwd) == (
        "pkg/subdir/module.py",
        "tracked.py",
    )
