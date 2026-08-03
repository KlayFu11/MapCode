# V1 to V2 Extensions

## Purpose

This document records features that are intentionally deferred from MapCode V1 and should be revisited in V2 planning.

V1 currently focuses on whether a single `ask()` / one run can fetch repo map context, prepare MapContext evidence, inject the required information into the model prompt, and drive the model processing path as expected.

V2 should focus on multi-turn and cross-run snapshot lifecycle behavior after the single-run path is proven.

## V1 Boundary

V1 should validate the end-to-end behavior of one run:

- MapEngine can build or load the needed repo map context before model execution.
- MapContext evidence, artifacts, trace/report data, and prompt injection fields are filled consistently.
- The model receives the expected map information within the designed budget and role boundaries.
- One run keeps a stable `index_snapshot_id` for all MapContext-related evidence.

V1 does not need to solve the complete snapshot refresh lifecycle for later user turns in the same conversation.

## V2 Snapshot Refresh Direction

V2 should add turn-start snapshot refresh for each new user turn / run.

Expected behavior:

- During one `ask()` execution, MapEngine is not rerun just because tools modify files.
- Before every new user turn / run, MapCode must validate the current repository code state.
- If any tracked or staged Python file changes in path set, `mtime_ns`, `size`, `parser_version`, `query_version`, or `schema_version`, MapCode should generate a new current snapshot.
- Unchanged files should reuse the persistent parsed cache.
- Changed or newly added files should be reparsed.
- Deleted files should be removed from the new snapshot.
- Within one run, Branch A/B, broad map, focused map, selector catalog, prompt injection evidence, and artifacts should all use the same `index_snapshot_id`.

## V2 Non-Goals

V2 snapshot refresh should not mean immediate MapEngine refresh after every tool write.

The intended model is:

- Refresh to latest code at the start of each new user turn / run.
- Keep one stable snapshot inside that run.
- Let tool writes inside the run become visible to MapEngine on the next user turn / run.

## Design Notes For Later SPEC Update

When V2 planning starts, update the active PRD, SPEC, FuncFlow, and V2 task docs to make this behavior explicit.

Likely SPEC additions:

- Define `turn-start snapshot validation` as a MapEngine lifecycle step before MapContext preparation.
- Define how current Git tracked/staged Python source records are collected.
- Define the comparison key: source path set plus `FileRecord(path, mtime_ns, size, parser_version, query_version, schema_version)`.
- Define cache reuse rules for unchanged files, changed files, new files, and deleted files.
- Define the evidence rule that all MapContext outputs in one run share one `index_snapshot_id`.
- State clearly that run-internal tool writes do not trigger automatic repo map refresh.
