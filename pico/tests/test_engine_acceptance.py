import json

from pico.testing import ScriptedModelClient
from pico import Pico, SessionStore, WorkspaceContext
from pico.core.context_manager import ContextManager
from pico.core.engine_helpers import request_step_limit_summary
from pico.core.task_state import TaskState
from pico.providers import ProviderError


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
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_engine_streams_a_real_session_with_tool_artifacts(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool name="write_file" path="notes/result.txt"><content>ok\n</content></tool>',
            "<final>Wrote it.</final>",
        ],
    )
    original_build = agent.context_manager.build
    purposes = []

    def record_purpose(user_message, *, purpose):
        purposes.append(purpose)
        return original_build(user_message, purpose=purpose)

    agent.context_manager.build = record_purpose

    events = list(agent.engine.run_turn("create the result file"))

    assert [event["type"] for event in events] == [
        "turn_started",
        "model_requested",
        "model_parsed",
        "tool_call",
        "tool_result",
        "model_requested",
        "model_parsed",
        "final",
        "turn_finished",
    ]
    assert events[-2]["content"] == "Wrote it."
    assert purposes == ["main_model", "main_model"]
    assert (tmp_path / "notes" / "result.txt").read_text(encoding="utf-8") == "ok\n"

    persisted_events = read_jsonl(agent.session_event_bus.path)
    assert [event["event"] for event in persisted_events][-6:] == [
        "tool_finished",
        "context_usage_recorded",
        "model_requested",
        "model_parsed",
        "assistant_message",
        "turn_finished",
    ]

    report_path = agent.current_run_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert report["final_answer"] == "Wrote it."


def test_engine_records_provider_error_as_failed_run(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            ProviderError(
                "rate limited",
                provider="openai",
                model="gpt-test",
                base_url="https://example.test/v1",
                code="rate_limited",
                http_status=429,
                retryable=True,
                attempts=3,
                retry_count=2,
            )
        ],
    )

    events = list(agent.engine.run_turn("call a rate limited provider"))

    assert events[-2]["type"] == "stop"
    assert "rate_limited" in events[-2]["content"]
    assert events[-2]["content"].startswith("模型错误")
    report = json.loads(
        (agent.current_run_dir / "report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "failed"
    assert report["stop_reason"] == "model_error"
    assert report["prompt_metadata"]["provider_error"]["code"] == "rate_limited"
    assert report["prompt_metadata"]["provider_error"]["retry_count"] == 2

    trace_events = read_jsonl(agent.current_run_dir / "trace.jsonl")
    model_error = next(
        event for event in trace_events if event["event"] == "model_error"
    )
    assert model_error["error"]["http_status"] == 429

    persisted_events = read_jsonl(agent.session_event_bus.path)
    assert any(
        event["event"] == "model_error" and event["code"] == "rate_limited"
        for event in persisted_events
    )


def test_engine_executes_multiple_tool_calls_from_one_model_response(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            "\n".join(
                [
                    '<tool>{"name":"read_file","args":{"path":"README.md","start":1,"end":1}}</tool>',
                    '<tool>{"name":"list_files","args":{"path":"."}}</tool>',
                ]
            ),
            "<final>Both tools ran.</final>",
        ],
    )

    events = list(agent.engine.run_turn("inspect the workspace"))

    assert [event["type"] for event in events if event["type"] == "tool_call"] == [
        "tool_call",
        "tool_call",
    ]
    tool_history = [item for item in agent.session["history"] if item["role"] == "tool"]
    assert [item["name"] for item in tool_history] == ["read_file", "list_files"]
    assert events[-2]["content"] == "Both tools ran."


def test_empty_response_provider_error_is_retried_once_before_failing(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            ProviderError(
                "empty provider response",
                provider="anthropic",
                model="deepseek-v4-pro",
                base_url="https://api.deepseek.com/anthropic/v1",
                code="empty_response",
                retryable=False,
            ),
            "<final>Recovered.</final>",
        ],
    )

    events = list(agent.engine.run_turn("recover from provider empty response"))

    assert events[-2]["content"] == "Recovered."
    persisted_events = read_jsonl(agent.session_event_bus.path)
    assert any(
        event["event"] == "model_retry_scheduled" and event["code"] == "empty_response"
        for event in persisted_events
    )


def test_worker_notification_drained_during_turn_is_streamed(tmp_path):
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"agent","args":{"description":"Inspect","prompt":"Read README","subagent_type":"Explore"}}</tool>',
            "<final>Child done.</final>",
            "<final>Parent done.</final>",
        ],
        max_steps=3,
    )

    events = list(agent.engine.run_turn("delegate and continue"))

    notifications = [
        event for event in events if event["type"] == "worker_notification"
    ]
    assert len(notifications) == 1
    assert "<task-id>agent_1</task-id>" in notifications[0]["content"]


def test_step_limit_triggers_graceful_summary_when_model_complies(tmp_path):
    """达到 step_limit 时，runtime 让模型用剩余预算给一个 <final> 总结，
    用户看到的就不再是冷冰冰的 'Stopped after reaching the step limit'。"""
    agent = build_agent(
        tmp_path,
        [
            # 1 步用掉 max_steps=1，触发 step_limit
            '<tool>{"name":"list_files","args":{"path":"."}}</tool>',
            # step_limit 总结调用——模型遵守了 notice 给 final
            "<final>已经列出文件。还差读取具体内容。继续请用 /resume。</final>",
        ],
        max_steps=1,
    )

    events = list(agent.engine.run_turn("trigger step limit"))

    stop_event = next(e for e in events if e["type"] == "stop")
    assert "已经列出文件" in stop_event["content"]
    assert "step 预算上限" in stop_event["content"]
    # 不能是历史的冷消息
    assert "Stopped after reaching the step limit" not in stop_event["content"]


def test_step_limit_falls_back_to_cold_message_when_summary_fails(tmp_path):
    """模型如果连总结都返回 retry，不能死循环，要 fall back 到老消息。"""
    agent = build_agent(
        tmp_path,
        [
            '<tool>{"name":"list_files","args":{"path":"."}}</tool>',
            # step_limit 总结时模型乱说话（没 <tool> 也没 <final>），解析为 retry
            "I cannot comply.",
        ],
        max_steps=1,
    )

    events = list(agent.engine.run_turn("trigger step limit"))

    stop_event = next(e for e in events if e["type"] == "stop")
    assert "Stopped after reaching the step limit" in stop_event["content"]


def test_step_limit_summary_over_budget_does_not_compact_session_history(tmp_path):
    agent = build_agent(tmp_path, ["<final>Continue from the latest tool result.</final>"])
    agent.context_manager = ContextManager(
        agent,
        total_budget=100,
        section_budgets={"prefix": 40, "memory": 40, "relevant_memory": 40, "history": 40},
        section_floors={"prefix": 40, "memory": 40, "relevant_memory": 40, "history": 40},
    )
    for index in range(8):
        agent.record({"role": "user", "content": f"old request {index} " + ("x" * 80)})
        agent.record({"role": "assistant", "content": f"old answer {index} " + ("y" * 80)})
    history_before = list(agent.session["history"])
    compactions_before = agent.session.get("compactions")
    original_build = agent.context_manager.build
    build_metadata = []

    def record_build(user_message, *, purpose):
        result = original_build(user_message, purpose=purpose)
        build_metadata.append((purpose, result.metadata["prompt_over_budget"]))
        return result

    agent.context_manager.build = record_build
    agent.emit_trace = lambda *args, **kwargs: None

    summary = request_step_limit_summary(
        agent.engine,
        TaskState.create(task_id="task_step_limit_summary", user_request="continue"),
        "continue",
    )

    assert summary == "Continue from the latest tool result."
    assert build_metadata == [("step_limit_summary", True)]
    assert agent.session["history"] == history_before
    assert agent.session.get("compactions") == compactions_before
