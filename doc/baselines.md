# MapCode Reference Baselines

## Purpose

This file records the local reference baselines used by MapCode v1 before MapEngine implementation starts.

The baseline directories are read-only project inputs. They explain behavior and provide comparison material, but they are not product source targets and must not be tracked into the MapCode Git baseline.

## Baseline Directories

| Directory | Role | Git status policy | Write policy |
|---|---|---|---|
| `pico_origin/` | Read-only Pico baseline snapshot used to compare the current `pico/` runtime against its original reference shape. | Ignored and not tracked. | Do not edit. |
| `aider/` | Read-only Aider reference source used to study Repo Map behavior, tree-sitter query usage, graph ranking, and context rendering ideas. | Ignored and not tracked. | Do not edit. |

`pico/` is the current MapCode implementation base. Product work should be incremental on `pico/`, not by modifying `pico_origin/` or importing from `aider/`.

## Aider License Boundary

The local Aider reference includes `aider/LICENSE.txt`, which is Apache License 2.0. `aider/pyproject.toml` also declares `License :: OSI Approved :: Apache Software License`.

Allowed use in MapCode v1:

- Study Aider Repo Map behavior and translate the design into MapCode-owned modules.
- Reuse the idea of Python tree-sitter queries, definition/reference extraction, PageRank/PPR ranking, and TreeContext-style rendering.
- Carry forward attribution and license notes when code or query material is adapted.

Forbidden use in MapCode v1:

- Do not add `import aider.*` anywhere in MapCode product code.
- Do not copy Aider `RepoMap` wholesale into `pico/`.
- Do not make `aider/` a runtime dependency.
- Do not track `aider/` in the MapCode Git index.

## Pico Baseline Boundary

`pico_origin/` is a local read-only source baseline. It is used to understand what changed from the original Pico runtime and to compare architecture, tests, docs, and runtime behavior.

Allowed use in MapCode v1:

- Read `pico_origin/` when a task needs baseline comparison.
- Use it to explain whether a change belongs to MapCode or came from the original Pico baseline.

Forbidden use in MapCode v1:

- Do not edit `pico_origin/`.
- Do not track `pico_origin/` in the MapCode Git index.
- Do not copy unreviewed chunks from `pico_origin/` into `pico/` as a substitute for an explicit MapCode task.

## Verification

Baseline boundaries are expected to satisfy:

```powershell
git check-ignore -v aider pico_origin
git ls-files aider pico_origin
Select-String -Path .\doc\baselines.md -Pattern "aider|pico_origin|Apache|import aider"
```
