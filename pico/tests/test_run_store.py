import json

from pico.core.run_store import RunStore
from pico.core.task_state import STOP_REASON_FINAL_ANSWER_RETURNED, TaskState


def test_run_store_creates_run_directory_and_state_file(tmp_path):
    store = RunStore(tmp_path / ".pico" / "runs")
    state = TaskState.create(run_id="run_001", task_id="task_001", user_request="Inspect the repo.")

    run_dir = store.start_run(state)

    assert run_dir == store.run_dir(state.run_id)
    assert run_dir.exists()
    persisted = json.loads((run_dir / "task_state.json").read_text(encoding="utf-8"))
    assert persisted["task_id"] == "task_001"
    assert persisted["run_id"] == "run_001"
    assert persisted["user_request"] == "Inspect the repo."
    assert persisted["map_context_summary"] == {}
    assert persisted["main_model_calls"] == 0
    assert persisted["selector_model_calls"] == 0


def test_run_store_appends_trace_jsonl(tmp_path):
    store = RunStore(tmp_path / ".pico" / "runs")
    state = TaskState.create(run_id="run_002", task_id="task_002", user_request="Trace the run.")
    store.start_run(state)

    store.append_trace(state, {"event": "run_started", "created_at": "2026-04-07T00:00:00+00:00"})
    store.append_trace(
        state.run_id,
        {
            "event": "prompt_built",
            "created_at": "2026-04-07T00:00:01+00:00",
            "prompt_metadata": {"prompt_chars": 128, "secret_env_count": 1},
        },
    )
    store.append_trace(state.run_id, {"event": "run_finished", "created_at": "2026-04-07T00:00:02+00:00"})

    lines = (store.trace_path(state.run_id)).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["event"] == "run_started"
    assert json.loads(lines[1])["event"] == "prompt_built"
    assert json.loads(lines[2])["event"] == "run_finished"


def test_run_store_writes_report_json(tmp_path):
    store = RunStore(tmp_path / ".pico" / "runs")
    state = TaskState.create(run_id="run_003", task_id="task_003", user_request="Report the run.")
    store.start_run(state)
    state.finish_success("Done.")

    store.write_task_state(state)
    store.write_report(state, {"task_state": state.to_dict(), "stop_reason": state.stop_reason})

    report = json.loads(store.report_path(state.run_id).read_text(encoding="utf-8"))
    assert report["stop_reason"] == STOP_REASON_FINAL_ANSWER_RETURNED
    assert report["task_state"]["final_answer"] == "Done."


def test_run_store_tolerates_missing_final_report(tmp_path):
    store = RunStore(tmp_path / ".pico" / "runs")
    state = TaskState.create(run_id="run_004", task_id="task_004", user_request="Crash before finalize.")

    store.start_run(state)
    store.append_trace(state, {"event": "run_started"})

    assert store.trace_path(state.run_id).exists()
    assert not store.report_path(state.run_id).exists()


def test_run_store_writes_numbered_json_artifacts(tmp_path):
    store = RunStore(tmp_path / ".pico" / "runs")
    state = TaskState.create(run_id="run_005", task_id="task_005", user_request="Persist evidence.")
    store.start_run(state)

    first_path = store.write_json_artifact(
        state,
        "map-evidence",
        {"event": "map_generated", "ranked_files": ["src/app.py"]},
    )
    second_path = store.write_json_artifact(
        state.run_id,
        "map-evidence",
        {"event": "map_generated", "ranked_files": ["src/auth.py"]},
    )

    assert first_path == store.artifacts_dir(state.run_id) / "map-evidence-001.json"
    assert second_path == store.artifacts_dir(state.run_id) / "map-evidence-002.json"
    assert json.loads(first_path.read_text(encoding="utf-8")) == {
        "event": "map_generated",
        "ranked_files": ["src/app.py"],
    }
    assert json.loads(second_path.read_text(encoding="utf-8")) == {
        "event": "map_generated",
        "ranked_files": ["src/auth.py"],
    }


def test_run_store_writes_json_artifact_atomically(tmp_path):
    store = RunStore(tmp_path / ".pico" / "runs")
    state = TaskState.create(run_id="run_006", task_id="task_006", user_request="Persist atomically.")
    store.start_run(state)
    calls = []

    def write_json_atomic(path, payload):
        calls.append((path, payload))
        path.write_text(json.dumps(payload), encoding="utf-8")

    store._write_json_atomic = write_json_atomic

    path = store.write_json_artifact(state, "map-evidence", {"ok": True})

    assert path == store.artifacts_dir(state.run_id) / "map-evidence-001.json"
    assert calls == [(path, {"ok": True})]
