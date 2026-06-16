# MapCode macOS Migration Handoff

## Conclusion

MapCode v1 development can move to macOS.

The current Windows failures should be treated as environment/baseline conflicts, not as proof that MapCode or Pico can only run on macOS. The project target should remain cross-platform unless a later product decision explicitly narrows support.

## Current Task State

- Branch on Windows: `winfeat/dev`
- Last committed HEAD before the current uncommitted batch: `88969af docs(V1-F0-02,V1-F0-03,V1-F0-04): align foundation governance docs`
- Current active batch: `V1-F0-05`, `V1-F0-06`, `V1-F0-07`, `V1-F0-08`
- Current task progress checkboxes: not checked yet
- Reason not checked: `V1-F0-06` baseline is recorded but not green on Windows; user review and commit are still pending
- Next intended task after this batch is accepted: `V1-F1-01 创建 MapEngine 配置和版本常量`

## Current Uncommitted Changes

- `.gitignore`
- `doc/baselines.md`
- `doc/prompt.md`
- `doc/tasks/v1/00-foundation.md`
- `doc/tasks/v1/progress.md`
- `pico/pyproject.toml`
- `experiment_map_engine_dependencies.py`
- `doc/mac-migration-handoff.md`

The local `.venv/` and `.planning/` directories are ignored. They are useful on this Windows machine but should not be relied on as the migration mechanism.

## What Was Completed In The Batch

### V1-F0-05

- `doc/prompt.md` was updated so the post-F0 path points to `V1-F1-01`.
- `doc/tasks/v1/00-foundation.md` validation was corrected to scan `doc/tasks/v1/*.md`.

### V1-F0-06

- Root `.venv` was created on Windows.
- Pico editable install was verified.
- `pico[dev]` was initially missing and then added to `pico/pyproject.toml`.
- Windows baseline was run and recorded, but not all tests passed.

### V1-F0-07

- `experiment_map_engine_dependencies.py` was created as a standalone script.
- The dependency experiment validated:
  - Python tree-sitter captures
  - `grep_ast.TreeContext` rendering
  - `networkx` PageRank and Personalized PageRank
- Final experiment output on Windows:

```text
tree_sitter_captures: 12
tree_context_chars: 219
pagerank_top: sample.py
dependency_experiment: ok
```

### V1-F0-08

- Verified MapEngine dependencies were added to `pico/pyproject.toml`:
  - `grep-ast`
  - `networkx`
  - `scipy`
  - `tree-sitter`
  - `tree-sitter-language-pack`
  - `tzdata` on Windows
- `doc/baselines.md` was updated with dependency and license boundaries.

## Windows Failures Observed

### 1. Root pytest import shadowing

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest pico\tests -q
```

Result: collection fails because the outer `pico/` directory shadows the installed inner `pico` package. Tests importing `from pico import Pico` resolve the wrong namespace.

Workaround used on Windows:

```powershell
cd .\pico
..\.venv\Scripts\python.exe -m pytest tests -q
```

### 2. Missing packaging extra

Initial result:

```text
pico 0.3.0 does not provide the extra 'dev'
```

Fix applied:

- Added `[project.optional-dependencies].dev` to `pico/pyproject.toml`.

### 3. Missing Windows timezone data

Initial result:

```text
ZoneInfoNotFoundError: No time zone found with key Asia/Shanghai
```

Fix applied:

- Added `tzdata>=2026.2; sys_platform == 'win32'`.

### 4. NetworkX numeric backend gap

Initial dependency experiment failed with:

```text
ModuleNotFoundError: No module named 'numpy'
```

Cause:

- `networkx.pagerank()` uses a numeric backend.
- Aider requirements indicate RepoMap uses NetworkX plus SciPy.

Fix applied:

- Added `scipy>=1.17.1,<1.18`; it supplies the required NumPy dependency.

### 5. Windows/POSIX test assumptions

Observed full pytest result from `D:\VScodeProject\MapCode\pico`:

```text
266 passed, 20 failed, 2 skipped, 6 warnings
```

Main failure categories:

- POSIX command assumptions: `pwd`, `tail`, `grep`, `python3`
- POSIX quoting assumptions from `shlex.quote()`
- `Path.home()` failures when tests clear all environment variables
- Windows symlink privilege failure
- Windows path separator differences such as `scripts\check.py` vs `scripts/check.py`
- Evaluator verifier failures caused by shell incompatibility

## macOS Revalidation Plan

On macOS, after applying or committing the current uncommitted changes, run:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e "./pico[dev]"
./.venv/bin/python experiment_map_engine_dependencies.py
cd pico
../.venv/bin/python -m pytest tests -q
../.venv/bin/python -m ruff check pico tests
```

If these pass on macOS, then the current Windows failures can be recorded as Windows compatibility issues rather than blockers for continuing v1 implementation on macOS.

If macOS also fails, keep `V1-F0-06` unchecked and fix the baseline before starting `V1-F1-01`.

## Product Platform Decision

Current judgment:

- Continue development on macOS is acceptable.
- Do not declare MapCode macOS-only.
- Pico appears to have POSIX-oriented tests and shell assumptions, which makes macOS/Linux the lower-friction development environment.
- MapCode should remain designed as a local Python project that can become cross-platform with explicit compatibility work.

Practical policy:

- Primary development platform for the next implementation phase: macOS.
- Windows support status: not validated; existing failures are known baseline compatibility issues.
- Do not promise Windows support until the Windows baseline is separately fixed and tested.
