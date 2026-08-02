import json

from pico.testing import ScriptedModelClient
from pico import Pico, SessionStore, WorkspaceContext
from pico.core.model_request_budget import (
    MODEL_REQUEST_TOKEN_ESTIMATION_METHOD,
    ModelRequestBudget,
)
from pico.core.task_state import TaskState


def build_agent(tmp_path, outputs, **kwargs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    workspace = WorkspaceContext.build(tmp_path)
    store = SessionStore(tmp_path / ".pico" / "sessions")
    return Pico(
        model_client=ScriptedModelClient(outputs),
        workspace=workspace,
        session_store=store,
        approval_policy="auto",
        **kwargs,
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def start_trace_run(agent):
    task_state = TaskState.create(
        task_id="task_trace",
        user_request="record map retrieval trace events",
        run_id="run_trace",
    )
    agent.current_task_state = task_state
    agent.current_turn_id = task_state.task_id
    agent.current_run_id = task_state.run_id
    agent.current_run_dir = agent.run_store.start_run(task_state)
    return task_state


def test_runtime_evidence_graph_and_verifier_are_derived_from_real_tool_run(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest run","build":"vite build"}}\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    agent = build_agent(
        tmp_path,
        [
            '<tool name="write_file" path="src/api.py"><content>@app.get("/api/items")\ndef list_items():\n    return fetch("/api/users")\n</content></tool>',
            "<final>Wrote API file.</final>",
        ],
    )

    assert agent.ask("add an api file") == "Wrote API file."

    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    task_state = json.loads((agent.current_run_dir / "task_state.json").read_text(encoding="utf-8"))
    graph = report["artifact_graph"]

    assert graph["changed_paths"] == ["src/api.py"]
    assert graph["categories"]["backend"] == ["src/api.py"]
    assert "/api/items" in graph["route_refs"]
    assert "/api/users" in graph["api_refs"]
    assert task_state["artifact_graph"] == graph

    commands = [item["command"] for item in report["verifier_suggestions"]]
    assert "npm test" in commands
    assert "npm run build" in commands
    assert "uv run python -m pytest -q" in commands
    assert task_state["verifier_suggestions"] == report["verifier_suggestions"]

    trace_events = read_jsonl(agent.current_run_dir / "trace.jsonl")
    tool_event = next(event for event in trace_events if event["event"] == "tool_executed")
    assert tool_event["phase"] == "tool"
    assert tool_event["status"] == "ok"
    assert tool_event["turn_id"] == agent.current_task_state.task_id
    assert tool_event["artifact_paths"] == ["src/api.py"]
    assert tool_event["span_id"]


def test_runtime_reminder_records_failed_tool_without_breaking_the_turn(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool name="patch_file" path="missing.py"><old_text>x</old_text><new_text>y</new_text></tool>',
            "<final>Could not patch missing file.</final>",
        ],
    )

    assert agent.ask("patch missing file") == "Could not patch missing file."

    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    reminders = report["runtime_reminders"]

    assert reminders
    assert reminders[-1]["event"] == "tool_executed"
    assert reminders[-1]["tool"] == "patch_file"
    assert reminders[-1]["status"] == "rejected"
    assert reminders[-1]["message"]
    assert json.loads((agent.current_run_dir / "task_state.json").read_text(encoding="utf-8"))["runtime_reminders"] == reminders


def test_report_uses_task_state_and_runtime_budget_without_map_context(tmp_path):
    agent = build_agent(tmp_path, ["<final>Done.</final>"])

    assert agent.ask("summarize the workspace") == "Done."

    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["map_context"] == {"enabled": False}
    assert report["model_calls"] == {
        "main_model_calls": 1,
        "selector_model_calls": 0,
        "total_model_calls": 1,
    }
    assert report["request_budget"] == {
        "model_input_budget_tokens": agent.model_request_budget.model_input_budget_tokens,
        "prompt_safety_margin_tokens": agent.model_request_budget.prompt_safety_margin_tokens,
        "model_request_budget_source": agent.model_request_budget.source,
        "budget_reduction_applied": False,
        "base_prompt_reduction_applied": False,
        "omission_reason": None,
        "request_over_budget": False,
    }


def test_report_uses_stop_reason_and_immutable_runtime_budget_for_over_budget(tmp_path):
    budget = ModelRequestBudget(
        provider="test",
        model="test-model",
        model_input_budget_tokens=2,
        prompt_safety_margin_tokens=1,
        estimation_method=MODEL_REQUEST_TOKEN_ESTIMATION_METHOD,
        source="explicit",
    )
    agent = build_agent(tmp_path, [], model_request_budget=budget)

    result = agent.ask("summarize the workspace")

    assert "Stopped locally" in result
    report = json.loads((agent.current_run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["request_budget"]["request_over_budget"] is True
    assert report["request_budget"]["model_request_budget_source"] == "explicit"
    assert report["model_calls"] == {
        "main_model_calls": 0,
        "selector_model_calls": 0,
        "total_model_calls": 0,
    }

    agent.last_prompt_metadata = {
        "request_over_budget": False,
        "model_request_budget_source": "tampered",
    }
    rebuilt_report = agent.build_report(agent.current_task_state)
    assert rebuilt_report["request_budget"]["request_over_budget"] is True
    assert rebuilt_report["request_budget"]["model_request_budget_source"] == "explicit"


def test_map_retrieval_trace_events_keep_explainable_payloads(tmp_path):
    agent = build_agent(tmp_path, [])
    task_state = start_trace_run(agent)

    analyzed_payload = {
        "branch": "specific",
        "mentioned_files": ["pico/core/runtime.py"],
        "mentioned_idents": ["PICO", "Runtime"],
        "effective_symbol_hits": ["Runtime"],
        "path_ident_hits": ["PICO"],
        "path_ident_hit_files": {
            "PICO": ["pico/core/runtime.py", "pico/core/session.py"],
        },
    }
    ranked_payload = {
        "stage": "focused",
        "algorithm": "personalized_pagerank",
        "focus_fnames": ["pico/core/runtime.py"],
        "focus_personalization_files": ["pico/core/runtime.py"],
        "path_personalization_files": ["pico/core/session.py"],
        "personalization_files": ["pico/core/runtime.py", "pico/core/session.py"],
        "top_ranked_files": ["pico/core/runtime.py"],
        "top_rank_contributors": [
            {
                "path": "pico/core/runtime.py",
                "identifier": "Runtime",
                "weight_multiplier": 75.0,
                "weight_reason_codes": [
                    "prompt_ident_boost",
                    "structured_ident_boost",
                    "focus_outbound_boost",
                ],
            }
        ],
    }
    selector_payload = {
        "index_snapshot_id": "snapshot-1",
        "candidate_path_count": 4,
        "rendered_path_count": 2,
        "visible_path_count": 3,
        "definition_count": 9,
        "rendered_definition_count": 6,
        "catalog_truncated": True,
        "input_chars": 2048,
        "call_number": 1,
        "budget": {
            "model_input_budget_tokens": 32768,
            "prompt_safety_margin_tokens": 1024,
            "request_over_budget": False,
        },
    }
    selected_payload = {
        "rendered_files": ["pico/core/runtime.py"],
        "omitted_files": ["pico/core/session.py"],
        "map_budget_tokens": 4096,
        "omission_reason": None,
    }

    agent.emit_trace(task_state, "map_index_status", {"index_snapshot_id": "snapshot-1"})
    analyzed_event = agent.emit_trace(task_state, "map_prompt_analyzed", analyzed_payload)
    ranked_event = agent.emit_trace(task_state, "map_context_ranked", ranked_payload)
    selected_event = agent.emit_trace(task_state, "map_context_selected", selected_payload)
    selector_event = agent.emit_trace(task_state, "map_selector_requested", selector_payload)
    agent.emit_trace(task_state, "map_focus_confirmed", {"confirmed_files": ["pico/core/runtime.py"]})
    agent.emit_trace(task_state, "map_generated", {"artifact_paths": ["artifacts/repo-map-001.txt"]})
    failed_event = agent.emit_trace(
        task_state,
        "map_context_failed",
        {
            "error_type": "artifact_write_failed",
            "message": "could not write map evidence",
            "fallback": "without_repo_map",
        },
    )

    trace_events = read_jsonl(agent.run_store.trace_path(task_state))
    map_events = [event for event in trace_events if event["event"].startswith("map_")]

    assert {event["phase"] for event in map_events} == {"retrieval"}
    assert all(event["status"] == "ok" for event in map_events if event["event"] != "map_context_failed")
    assert failed_event["status"] == "error"
    assert analyzed_event["path_ident_hits"] == ["PICO"]
    assert analyzed_event["path_ident_hit_files"] == {
        "PICO": ["pico/core/runtime.py", "pico/core/session.py"],
    }
    assert ranked_event["focus_personalization_files"] == ["pico/core/runtime.py"]
    assert ranked_event["path_personalization_files"] == ["pico/core/session.py"]
    assert ranked_event["personalization_files"] == ["pico/core/runtime.py", "pico/core/session.py"]
    assert ranked_event["top_rank_contributors"][0]["weight_multiplier"] == 75.0
    assert ranked_event["top_rank_contributors"][0]["weight_reason_codes"] == [
        "prompt_ident_boost",
        "structured_ident_boost",
        "focus_outbound_boost",
    ]
    assert selector_event["candidate_path_count"] == 4
    assert selector_event["rendered_path_count"] == 2
    assert selector_event["visible_path_count"] == 3
    assert selector_event["definition_count"] == 9
    assert selector_event["rendered_definition_count"] == 6
    assert selector_event["catalog_truncated"] is True
    assert selector_event["input_chars"] == 2048
    assert selector_event["budget"]["request_over_budget"] is False
    assert selected_event["map_budget_tokens"] == 4096
    assert selected_event["omission_reason"] is None
