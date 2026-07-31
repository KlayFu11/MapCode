from pico.core.task_state import (
    STOP_REASON_FINAL_ANSWER_RETURNED,
    STOP_REASON_REQUEST_OVER_BUDGET,
    STOP_REASON_RETRY_LIMIT_REACHED,
    STOP_REASON_STEP_LIMIT_REACHED,
    TaskState,
)


def test_task_state_starts_running_with_empty_progress():
    state = TaskState.create(run_id="run_001", task_id="task_001", user_request="Inspect the repo.")

    assert state.task_id == "task_001"
    assert state.run_id == "run_001"
    assert state.user_request == "Inspect the repo."
    assert state.status == "running"
    assert state.tool_steps == 0
    assert state.attempts == 0
    assert state.main_model_calls == 0
    assert state.selector_model_calls == 0
    assert state.map_context_summary == {}
    assert state.last_tool == ""
    assert state.stop_reason == ""
    assert state.final_answer == ""


def test_task_state_records_success_and_final_answer():
    state = TaskState.create(run_id="run_002", task_id="task_002", user_request="Fix the bug.")
    state.record_attempt()
    state.record_tool("read_file")
    state.finish_success("Done.")

    assert state.attempts == 1
    assert state.main_model_calls == 0
    assert state.selector_model_calls == 0
    assert state.tool_steps == 1
    assert state.last_tool == "read_file"
    assert state.status == "completed"
    assert state.stop_reason == STOP_REASON_FINAL_ANSWER_RETURNED
    assert state.final_answer == "Done."


def test_task_state_records_step_limit_stop_reason():
    state = TaskState.create(run_id="run_003", task_id="task_003", user_request="Try again.")

    state.stop_step_limit()

    assert state.status == "stopped"
    assert state.stop_reason == STOP_REASON_STEP_LIMIT_REACHED


def test_task_state_records_retry_limit_stop_reason():
    state = TaskState.create(run_id="run_004", task_id="task_004", user_request="Try again.")

    state.stop_retry_limit()

    assert state.status == "stopped"
    assert state.stop_reason == STOP_REASON_RETRY_LIMIT_REACHED


def test_task_state_records_request_over_budget_stop_reason():
    state = TaskState.create(run_id="run_003b", task_id="task_003b", user_request="Try again.")

    state.stop_request_over_budget()

    assert state.status == "stopped"
    assert state.stop_reason == STOP_REASON_REQUEST_OVER_BUDGET


def test_task_state_snapshot_keeps_final_answer():
    state = TaskState.create(run_id="run_005", task_id="task_005", user_request="Return the answer.")
    state.finish_success("Final answer.")

    snapshot = state.to_dict()

    assert snapshot["final_answer"] == "Final answer."
    assert snapshot["stop_reason"] == STOP_REASON_FINAL_ANSWER_RETURNED


def test_task_state_snapshot_keeps_checkpoint_reference_without_body():
    state = TaskState.create(run_id="run_006", task_id="task_006", user_request="Resume the task.")
    state.checkpoint_id = "ckpt_001"
    state.resume_status = "full-valid"

    snapshot = state.to_dict()

    assert snapshot["checkpoint_id"] == "ckpt_001"
    assert snapshot["resume_status"] == "full-valid"
    assert "current_goal" not in snapshot
    assert "next_step" not in snapshot


def test_task_state_tracks_model_calls_separately_from_attempts():
    state = TaskState.create(run_id="run_007", task_id="task_007", user_request="Call models.")

    state.record_attempt()
    state.record_main_model_call()
    state.record_selector_model_call()

    assert state.attempts == 1
    assert state.main_model_calls == 1
    assert state.selector_model_calls == 1


def test_task_state_snapshot_keeps_lightweight_map_context_summary():
    state = TaskState.create(run_id="run_008", task_id="task_008", user_request="Use map context.")
    state.map_context_summary = {
        "map_context_id": "mapctx_abc",
        "branch": "specific",
        "stage": "execution",
        "focus_fnames": ["pico/core/runtime.py"],
        "rendered_files": ["pico/core/runtime.py"],
        "index_snapshot_id": "sha256:abc123",
        "repo_map_artifact_path": ".pico/runs/run_008/artifacts/repo-map-001.txt",
        "evidence_artifact_path": ".pico/runs/run_008/artifacts/map-evidence-001.json",
        "selector_model_calls": 0,
    }
    state.main_model_calls = 2
    state.selector_model_calls = 1

    snapshot = state.to_dict()
    restored = TaskState.from_dict(snapshot)

    assert snapshot["map_context_summary"] == state.map_context_summary
    assert snapshot["main_model_calls"] == 2
    assert snapshot["selector_model_calls"] == 1
    assert "repo_map_text" not in snapshot["map_context_summary"]
    assert "active_result" not in snapshot["map_context_summary"]
    assert restored.map_context_summary == state.map_context_summary
    assert restored.main_model_calls == 2
    assert restored.selector_model_calls == 1


def test_task_state_from_dict_accepts_old_snapshots_without_map_fields():
    restored = TaskState.from_dict(
        {
            "run_id": "run_009",
            "task_id": "task_009",
            "user_request": "Resume old task state.",
            "attempts": 3,
        }
    )

    assert restored.attempts == 3
    assert restored.main_model_calls == 0
    assert restored.selector_model_calls == 0
    assert restored.map_context_summary == {}
