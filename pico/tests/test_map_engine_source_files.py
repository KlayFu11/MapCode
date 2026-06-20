import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from pico.features.map_engine.source_files import (
    SourceFileDiscoveryError,
    list_git_index_paths,
    list_python_source_files,
)


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


def test_selects_existing_regular_python_files_from_git_index(git_repo: Path):
    _write(git_repo, "pkg/new_file.py")
    _git(git_repo, "add", "pkg/new_file.py")

    selection = list_python_source_files(git_repo)

    assert selection.source_paths == (
        "pkg/new_file.py",
        "tracked.py",
    )
    assert selection.skipped_files == ()


def test_filters_non_python_and_missing_tracked_files(git_repo: Path):
    _write(git_repo, "README.md", "# Demo\n")
    _git(git_repo, "add", "README.md")
    (git_repo / "tracked.py").unlink()

    selection = list_python_source_files(git_repo)

    assert selection.source_paths == ()
    assert [(skip.path, skip.reason) for skip in selection.skipped_files] == [
        ("README.md", "non_python"),
        ("tracked.py", "missing"),
    ]


def test_filters_denylisted_tracked_python_files(git_repo: Path):
    _write(git_repo, ".pico/cache.py")
    _write(git_repo, ".venv/tool.py")
    _write(git_repo, "__pycache__/cached.py")
    _write(git_repo, "build/generated.py")
    _write(git_repo, "src/app.py")
    _git(
        git_repo,
        "add",
        "-f",
        ".pico/cache.py",
        ".venv/tool.py",
        "__pycache__/cached.py",
        "build/generated.py",
        "src/app.py",
    )

    selection = list_python_source_files(git_repo)

    assert selection.source_paths == (
        "src/app.py",
        "tracked.py",
    )
    assert [(skip.path, skip.reason) for skip in selection.skipped_files] == [
        (".pico/cache.py", "denylisted"),
        (".venv/tool.py", "denylisted"),
        ("__pycache__/cached.py", "denylisted"),
        ("build/generated.py", "denylisted"),
    ]


def test_non_git_workspace_raises_without_recursive_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "untracked.py").write_text("value = 1\n", encoding="utf-8")

    def fail_on_rglob(self, pattern):
        raise AssertionError("filesystem recursion is not allowed")

    monkeypatch.setattr(Path, "rglob", fail_on_rglob)

    with pytest.raises(SourceFileDiscoveryError, match="Git source file discovery failed"):
        list_python_source_files(tmp_path)
