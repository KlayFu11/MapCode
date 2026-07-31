from types import SimpleNamespace

import pytest

from pico.testing import ScriptedModelClient
from pico import Pico, SessionStore, WorkspaceContext
from pico.core.context_manager import ContextManager
from pico.core.map_context_prompt import EMPTY_REPO_MAP_SECTION_HASH, PromptBuildResult
from pico.core.model_request_budget import (
    MODEL_REQUEST_TOKEN_ESTIMATION_METHOD,
    ModelRequestBudget,
)


def build_workspace(tmp_path):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return WorkspaceContext.build(tmp_path)


def build_agent(tmp_path, outputs, **kwargs):
    workspace = build_workspace(tmp_path)
    store = SessionStore(tmp_path / ".pico" / "sessions")
    approval_policy = kwargs.pop("approval_policy", "auto")
    return Pico(
        model_client=ScriptedModelClient(outputs),
        workspace=workspace,
        session_store=store,
        approval_policy=approval_policy,
        **kwargs,
    )


def build_result(manager, user_message):
    return manager.build(user_message, purpose="main_model")


def set_current_map(
    agent,
    *,
    branch="specific",
    stage="execution",
    focus_fnames=(),
    repo_map_text="repo map body",
    fallback_mode=None,
):
    agent.current_map_context = SimpleNamespace(
        branch=branch,
        stage=stage,
        active_result=SimpleNamespace(
            focus_fnames=focus_fnames,
            repo_map_text=repo_map_text,
        ),
        selection_decision=(
            None
            if fallback_mode is None
            else SimpleNamespace(fallback_mode=fallback_mode)
        ),
    )


def test_context_manager_requires_explicit_prompt_purpose(tmp_path):
    manager = ContextManager(build_agent(tmp_path, []))

    with pytest.raises(TypeError):
        manager.build("Where is the deploy key?")


def test_context_manager_returns_build_local_prompt_result_and_budget_metadata(tmp_path):
    model_request_budget = ModelRequestBudget(
        provider="test",
        model="test-model",
        model_input_budget_tokens=512,
        prompt_safety_margin_tokens=32,
        estimation_method=MODEL_REQUEST_TOKEN_ESTIMATION_METHOD,
        source="explicit",
    )
    agent = build_agent(tmp_path, [], model_request_budget=model_request_budget)
    manager = ContextManager(agent)

    first = build_result(manager, "Inspect the context manager.")
    second = build_result(manager, "Inspect the context manager.")

    assert isinstance(first, PromptBuildResult)
    assert first.repo_map_render is None
    assert first is not second
    assert first.metadata is not second.metadata
    assert first.prompt == second.prompt
    assert first.metadata == second.metadata
    assert {
        "model_input_budget_tokens": 512,
        "prompt_safety_margin_tokens": 32,
        "active_repo_map_reservation_tokens": 0,
        "base_prompt_budget_tokens": 480,
        "estimated_request_tokens": model_request_budget.estimate_request_tokens(first.prompt),
        "request_over_budget": model_request_budget.request_over_budget(first.prompt),
        "model_request_budget_source": "explicit",
    }.items() <= first.metadata.items()


def test_context_manager_assembles_sections_in_expected_order(tmp_path):
    agent = build_agent(tmp_path, [])
    agent.memory.append_note("deploy key is red", tags=("deploy",), created_at="2026-04-07T10:00:00+00:00")
    agent.record({"role": "user", "content": "old request", "created_at": "2026-04-07T09:59:00+00:00"})
    agent.record({"role": "assistant", "content": "old answer", "created_at": "2026-04-07T10:00:30+00:00"})

    result = build_result(ContextManager(agent), "Where is the deploy key?")
    prompt = result.prompt
    metadata = result.metadata

    assert prompt.index("You are pico") < prompt.index("Memory:")
    assert prompt.index("Memory:") < prompt.index("Available skills:")
    assert prompt.index("Available skills:") < prompt.index("Relevant memory:")
    assert prompt.index("Relevant memory:") < prompt.index("Transcript:")
    assert prompt.index("Transcript:") < prompt.index("Current user request:")
    assert prompt.rstrip().endswith("Current user request:\nWhere is the deploy key?")
    assert metadata["section_order"] == ["prefix", "memory", "skills", "relevant_memory", "history", "current_request"]


@pytest.mark.parametrize(
    ("purpose", "repo_map_expected"),
    [
        ("main_model", True),
        ("prompt_preview", True),
        ("evaluation", False),
        ("step_limit_summary", False),
    ],
)
def test_context_manager_scopes_repo_map_to_main_and_preview_purposes(
    tmp_path,
    purpose,
    repo_map_expected,
):
    agent = build_agent(tmp_path, [])
    agent.record({"role": "user", "content": "old request", "created_at": "2026-04-07T09:59:00+00:00"})
    map_body = "pico/core/context_manager.py:\n  class ContextManager\n" + ("x" * 800)
    set_current_map(
        agent,
        focus_fnames=("pico/core/context_manager.py",),
        repo_map_text=map_body,
    )
    manager = ContextManager(agent)

    result = manager.build("Inspect the prompt.", purpose=purpose)

    if repo_map_expected:
        render = result.repo_map_render

        assert result.prompt.index("Transcript:") < result.prompt.index("[Repo Map - Navigation Context Only]")
        assert result.prompt.index("[Repo Map - Navigation Context Only]") < result.prompt.index("Current user request:")
        assert result.prompt.endswith("Current user request:\nInspect the prompt.")
        assert result.metadata["section_order"] == [
            "prefix",
            "memory",
            "skills",
            "relevant_memory",
            "history",
            "repo_map",
            "current_request",
        ]
        assert result.metadata["sections"]["repo_map"] == {
            "raw_chars": len(render.section_text),
            "budget_chars": 0,
            "rendered_chars": len(render.section_text),
        }
        assert result.metadata["map_context"] == {
            "section_rendered": True,
            "contract_rendered": True,
            "fallback_notice_rendered": False,
            "map_body_raw_chars": len(map_body),
            "map_body_rendered_chars": len(map_body),
            "section_rendered_chars": len(render.section_text),
            "section_rendered_hash": render.section_rendered_hash,
            "base_prompt_reduction_applied": False,
            "omission_reason": None,
        }
        assert render.section_text.endswith(map_body)
        assert render.map_body_raw_chars == render.map_body_rendered_chars
    else:
        assert "[Repo Map - Navigation Context Only]" not in result.prompt
        assert "repo_map" not in result.metadata["section_order"]
        assert "map_context" not in result.metadata
        assert result.repo_map_render is None

    assert agent.current_map_context.active_result.repo_map_text == map_body


def test_context_manager_reserves_complete_repo_map_before_reducing_base_sections(tmp_path):
    model_request_budget = ModelRequestBudget(
        provider="test",
        model="test-model",
        model_input_budget_tokens=800,
        prompt_safety_margin_tokens=40,
        estimation_method=MODEL_REQUEST_TOKEN_ESTIMATION_METHOD,
        source="explicit",
    )
    agent = build_agent(tmp_path, [], model_request_budget=model_request_budget)
    agent.prefix = "PREFIX " + ("A" * 1_200)
    agent.memory.render_memory_text = lambda: "MEMORY " + ("B" * 900)
    agent.record({"role": "user", "content": "old request " + ("C" * 600)})
    set_current_map(
        agent,
        focus_fnames=("pico/core/context_manager.py",),
        repo_map_text="pico/core/context_manager.py:\n" + ("M" * 800),
    )
    manager = ContextManager(
        agent,
        total_budget=3_000,
        section_budgets={
            "prefix": 1_200,
            "memory": 900,
            "skills": 120,
            "relevant_memory": 120,
            "history": 900,
        },
    )

    result = build_result(manager, "Inspect this complete map.")
    metadata = result.metadata
    render = result.repo_map_render

    assert metadata["active_repo_map_reservation_tokens"] == (
        model_request_budget.estimate_request_tokens(render.section_text)
    )
    assert metadata["base_prompt_budget_tokens"] == (
        model_request_budget.model_input_budget_tokens
        - metadata["active_repo_map_reservation_tokens"]
        - model_request_budget.prompt_safety_margin_tokens
    )
    assert metadata["effective_base_prompt_budget_chars"] == min(
        manager.total_budget,
        metadata["base_prompt_budget_tokens"] * 4,
    )
    assert metadata["base_prompt_chars"] <= metadata["effective_base_prompt_budget_chars"]
    assert metadata["base_prompt_over_budget"] is False
    assert metadata["base_prompt_over_budget_with_repo_map_reservation"] is False
    assert metadata["budget_reductions"]
    assert render.base_prompt_reduction_applied is True
    assert metadata["map_context"]["base_prompt_reduction_applied"] is True
    assert render.map_body_rendered_chars == render.map_body_raw_chars
    assert render.section_text.endswith("M" * 800)


def test_context_manager_omits_repo_map_when_base_prompt_cannot_fit_at_floors(tmp_path):
    model_request_budget = ModelRequestBudget(
        provider="test",
        model="test-model",
        model_input_budget_tokens=320,
        prompt_safety_margin_tokens=40,
        estimation_method=MODEL_REQUEST_TOKEN_ESTIMATION_METHOD,
        source="explicit",
    )
    agent = build_agent(tmp_path, [], model_request_budget=model_request_budget)
    agent.prefix = "PREFIX " + ("A" * 1_000)
    agent.memory.render_memory_text = lambda: "MEMORY " + ("B" * 800)
    map_body = "pico/core/context_manager.py:\n" + ("M" * 800)
    set_current_map(agent, repo_map_text=map_body)
    manager = ContextManager(
        agent,
        total_budget=3_000,
        section_budgets={
            "prefix": 1_000,
            "memory": 800,
            "skills": 120,
            "relevant_memory": 120,
            "history": 120,
        },
    )

    result = build_result(manager, "Inspect the complete map.")
    render = result.repo_map_render

    assert render.section_rendered is False
    assert render.section_text == ""
    assert render.contract_rendered is False
    assert render.map_body_raw_chars == len(map_body)
    assert render.map_body_rendered_chars == 0
    assert render.section_rendered_hash == EMPTY_REPO_MAP_SECTION_HASH
    assert render.omission_reason == "base_prompt_cannot_fit_with_repo_map_reservation"
    assert render.base_prompt_reduction_applied is True
    assert "[Repo Map - Navigation Context Only]" not in result.prompt
    assert map_body not in result.prompt
    assert result.metadata["active_repo_map_reservation_tokens"] == 0
    assert result.metadata["base_prompt_budget_tokens"] == 280
    assert result.metadata["base_prompt_over_budget"] is False
    assert result.metadata["base_prompt_over_budget_with_repo_map_reservation"] is True
    assert result.metadata["estimated_request_tokens"] == model_request_budget.estimate_request_tokens(result.prompt)
    assert result.metadata["request_over_budget"] is model_request_budget.request_over_budget(result.prompt)
    assert "repo_map" not in result.metadata["section_order"]
    assert result.metadata["map_context"]["omission_reason"] == render.omission_reason


def test_context_manager_omits_repo_map_when_renderer_fails(tmp_path, monkeypatch):
    agent = build_agent(tmp_path, [])
    map_body = "pico/core/context_manager.py:\n  class ContextManager"
    set_current_map(agent, repo_map_text=map_body)
    manager = ContextManager(agent)

    def fail_render(_map_context):
        raise RuntimeError("fixture renderer failure")

    monkeypatch.setattr(
        "pico.core.context_manager.render_repo_map_navigation_text",
        fail_render,
    )

    result = build_result(manager, "Inspect the complete map.")
    render = result.repo_map_render

    assert render.section_rendered is False
    assert render.section_text == ""
    assert render.map_body_raw_chars == len(map_body)
    assert render.section_rendered_hash == EMPTY_REPO_MAP_SECTION_HASH
    assert render.omission_reason == "repo_map_section_render_failed"
    assert "[Repo Map - Navigation Context Only]" not in result.prompt
    assert result.metadata["active_repo_map_reservation_tokens"] == 0
    assert "repo_map" not in result.metadata["section_order"]
    assert result.metadata["map_context"]["omission_reason"] == render.omission_reason


def test_context_manager_marks_broad_fallback_notice_in_repo_map_render(tmp_path):
    agent = build_agent(tmp_path, [])
    set_current_map(
        agent,
        branch="fuzzy",
        stage="fallback",
        focus_fnames=(),
        repo_map_text="broad repo map body",
        fallback_mode="broad_map",
    )

    result = build_result(ContextManager(agent), "Inspect the prompt.")

    assert result.repo_map_render.fallback_notice_rendered is True
    assert result.metadata["map_context"]["fallback_notice_rendered"] is True
    assert "Mode: broad_fallback" in result.prompt
    assert "No specific focus files were confirmed." in result.prompt


@pytest.mark.parametrize(
    "purpose",
    ["main_model", "prompt_preview", "evaluation", "step_limit_summary"],
)
def test_context_manager_feature_off_without_map_context_preserves_base_prompt(tmp_path, purpose):
    agent = build_agent(tmp_path, [])

    result = ContextManager(agent).build("Inspect the prompt.", purpose=purpose)

    assert agent.feature_enabled("map_engine") is False
    assert agent.current_map_context is None
    assert "[Repo Map - Navigation Context Only]" not in result.prompt
    assert "repo_map" not in result.metadata["section_order"]
    assert "map_context" not in result.metadata
    assert result.repo_map_render is None


def test_context_manager_preview_build_keeps_main_repo_map_render_build_local(tmp_path):
    agent = build_agent(tmp_path, [])
    manager = ContextManager(agent)
    main_map_body = "pico/core/runtime.py:\n  class Pico\n"
    preview_map_body = "pico/core/engine.py:\n  class Engine\n"
    set_current_map(agent, repo_map_text=main_map_body)

    main_result = manager.build("Inspect the main prompt.", purpose="main_model")
    main_section_text = main_result.repo_map_render.section_text
    main_metadata = dict(main_result.metadata["map_context"])

    set_current_map(agent, repo_map_text=preview_map_body)
    preview_result = manager.build("Inspect the preview prompt.", purpose="prompt_preview")

    assert main_result.repo_map_render is not preview_result.repo_map_render
    assert main_result.repo_map_render.section_text == main_section_text
    assert main_map_body in main_result.prompt
    assert preview_map_body not in main_result.prompt
    assert main_result.metadata["map_context"] == main_metadata
    assert preview_map_body in preview_result.prompt
    assert main_map_body not in preview_result.prompt


def test_context_manager_reduces_relevant_memory_before_history_and_preserves_newer_context(tmp_path):
    agent = build_agent(tmp_path, [])
    agent.prefix = "PREFIX " + ("A" * 600)
    agent.memory.render_memory_text = lambda: "MEMORY " + ("B" * 600)
    agent.memory.append_note("keep episodic note one " + ("C" * 220), tags=("keep",), created_at="2026-04-07T10:00:00+00:00")
    agent.memory.append_note("keep episodic note two " + ("D" * 220), tags=("keep",), created_at="2026-04-07T10:01:00+00:00")
    agent.memory.append_note("keep episodic note three " + ("E" * 220), tags=("keep",), created_at="2026-04-07T10:02:00+00:00")
    agent.record({"role": "user", "content": "OLD-CONTEXT " + ("D" * 260), "created_at": "2026-04-07T09:59:00+00:00"})
    for minute in range(1, 8):
        role = "assistant" if minute % 2 == 1 else "user"
        content = "RECENT-CONTEXT " + ("E" * 260) if minute == 7 else f"recent-{minute} " + ("E" * 180)
        agent.record({"role": role, "content": content, "created_at": f"2026-04-07T10:0{minute}:00+00:00"})

    manager = ContextManager(
        agent,
        total_budget=700,
        section_budgets={
            "prefix": 120,
            "memory": 120,
            "skills": 60,
            "relevant_memory": 120,
            "history": 400,
        },
    )

    result = build_result(manager, "keep this request verbatim")
    prompt = result.prompt
    metadata = result.metadata

    for section in ("prefix", "memory", "relevant_memory", "history"):
        assert metadata["sections"][section]["rendered_chars"] <= metadata["sections"][section]["budget_chars"]

    reduction_sections = [entry["section"] for entry in metadata["budget_reductions"]]
    assert reduction_sections[0] == "relevant_memory"
    assert reduction_sections
    assert "RECENT-CONTEXT" in prompt
    assert "OLD-CONTEXT" not in prompt
    assert "keep this request verbatim" in prompt


def test_context_manager_renders_top_three_episodic_notes_per_note_under_budget(tmp_path):
    agent = build_agent(tmp_path, [])
    agent.memory.append_note("alpha episodic note " + ("A" * 120), tags=("recall",), created_at="2026-04-07T10:00:00+00:00")
    agent.memory.append_note("beta episodic recall note " + ("B" * 120), created_at="2026-04-07T10:01:00+00:00")
    agent.memory.append_note("gamma episodic note " + ("C" * 120), tags=("recall",), created_at="2026-04-07T10:02:00+00:00")
    agent.memory.append_note("older unmatched note", created_at="2026-04-07T09:59:00+00:00")
    agent.memory.append_note("Unrelated note", created_at="2026-04-07T11:00:00+00:00")

    result = build_result(ContextManager(
        agent,
        total_budget=500,
        section_budgets={
            "prefix": 60,
            "memory": 60,
            "skills": 80,
            "relevant_memory": 80,
            "history": 60,
        },
    ), "recall")
    prompt = result.prompt
    metadata = result.metadata

    assert metadata["relevant_memory"]["selected_count"] == 3
    assert metadata["relevant_memory"]["limit"] == 3
    assert metadata["relevant_memory"]["selected_notes"] == [
        "gamma episodic note " + ("C" * 120),
        "alpha episodic note " + ("A" * 120),
        "beta episodic recall note " + ("B" * 120),
    ]
    assert len(metadata["relevant_memory"]["rendered_notes"]) == 3
    assert metadata["relevant_memory"]["rendered_count"] == 3
    assert metadata["relevant_memory"]["rendered_notes"][0].startswith("gamma episodi")
    assert metadata["relevant_memory"]["rendered_notes"][1].startswith("alpha episodi")
    assert metadata["relevant_memory"]["rendered_notes"][2].startswith("beta episodi")
    relevant_section = prompt.split("Relevant memory:\n", 1)[1].split("\n\nTranscript:", 1)[0]
    assert len([line for line in relevant_section.splitlines() if line.startswith("- ")]) == 3
    assert "alpha episodi" in relevant_section
    assert "beta episodic" in relevant_section
    assert "gamma episodi" in relevant_section
    assert "older unmatched note" not in relevant_section


def test_context_manager_preserves_current_request_when_over_budget(tmp_path):
    agent = build_agent(tmp_path, [])
    agent.prefix = "PREFIX " + ("A" * 600)
    agent.memory.render_memory_text = lambda: "MEMORY " + ("B" * 600)
    agent.memory.retrieval_view = lambda query, limit=3: "Relevant memory:\n" + "\n".join(f"- {i} " + ("C" * 220) for i in range(5))
    agent.history_text = lambda: "Transcript:\n" + "\n".join(f"[user] {i} " + ("D" * 220) for i in range(5))

    request = "please preserve this request exactly"
    result = build_result(ContextManager(
        agent,
        total_budget=250,
        section_budgets={
            "prefix": 80,
            "memory": 80,
            "skills": 40,
            "relevant_memory": 80,
            "history": 80,
        },
    ), request)
    prompt = result.prompt
    metadata = result.metadata

    assert prompt.split("Current user request:\n", 1)[1] == request
    assert metadata["current_request"]["text"] == request
    assert metadata["current_request"]["rendered_chars"] == len(request)


def test_context_manager_collapses_older_duplicate_reads_into_one_summary_line(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("alpha\nbeta\n", encoding="utf-8")
    agent = build_agent(tmp_path, [])
    agent.memory.set_file_summary("sample.txt", "alpha | beta")
    agent.memory.remember_file("sample.txt")

    for created_at in ("2026-04-07T09:00:00+00:00", "2026-04-07T09:01:00+00:00"):
        agent.record(
            {
                "role": "tool",
                "name": "read_file",
                "args": {"path": "sample.txt", "start": 1, "end": 2},
                "content": "# sample.txt\nalpha\nbeta\n",
                "created_at": created_at,
            }
        )

    for minute in range(2, 8):
        role = "user" if minute % 2 == 0 else "assistant"
        agent.record(
            {
                "role": role,
                "content": f"recent-{minute}",
                "created_at": f"2026-04-07T09:0{minute}:00+00:00",
            }
        )

    result = build_result(ContextManager(agent), "check the file")
    prompt = result.prompt
    metadata = result.metadata
    transcript = prompt.split("\n\nTranscript:\n", 1)[1].split("\n\nCurrent user request:", 1)[0]

    assert transcript.count("[tool:read_file]") == 0
    assert "sample.txt -> alpha | beta" in transcript
    assert metadata["history"]["older_entries_count"] == 1
    assert metadata["history"]["collapsed_duplicate_reads"] == 1
    assert metadata["history"]["reused_file_summary_count"] == 1


def test_context_manager_summarizes_older_tool_output_into_one_line(tmp_path):
    agent = build_agent(tmp_path, [])
    agent.record(
        {
            "role": "tool",
            "name": "run_shell",
            "args": {"command": "pytest -q"},
            "content": "FAIL test_one\nFAIL test_two\nFAIL test_three\nFAIL test_four\n",
            "created_at": "2026-04-07T09:00:00+00:00",
        }
    )

    for minute in range(1, 7):
        role = "user" if minute % 2 == 1 else "assistant"
        agent.record(
            {
                "role": role,
                "content": f"recent-{minute}",
                "created_at": f"2026-04-07T09:0{minute}:00+00:00",
            }
        )

    result = build_result(ContextManager(agent), "check failures")
    prompt = result.prompt
    metadata = result.metadata
    transcript = prompt.split("\n\nTranscript:\n", 1)[1].split("\n\nCurrent user request:", 1)[0]

    assert 'pytest -q -> FAIL test_one | FAIL test_two | FAIL test_three' in transcript
    assert "FAIL test_four" not in transcript
    assert metadata["history"]["summarized_tool_count"] == 1
    assert metadata["history"]["reused_file_summary_count"] == 0


def test_context_manager_relevant_memory_can_mix_durable_notes(tmp_path):
    memory_root = tmp_path / ".pico" / "memory"
    topics_dir = memory_root / "topics"
    topics_dir.mkdir(parents=True)
    (memory_root / "MEMORY.md").write_text(
        "# Durable Memory Index\n\n"
        "- [project-conventions](topics/project-conventions.md): Project Conventions\n"
        "  - summary: Stable repository conventions.\n"
        "  - tags: convention\n",
        encoding="utf-8",
    )
    (topics_dir / "project-conventions.md").write_text(
        "# Project Conventions\n\n"
        "- topic: project-conventions\n"
        "- summary: Stable repository conventions.\n"
        "- tags: convention\n"
        "- updated_at: 2026-04-12T08:14:49+00:00\n\n"
        "## Notes\n"
        "- Use constrained tools instead of guessing.\n",
        encoding="utf-8",
    )

    agent = build_agent(tmp_path, [])

    result = build_result(ContextManager(agent), "What conventions should I follow?")
    prompt = result.prompt
    metadata = result.metadata
    relevant_section = prompt.split("Relevant memory:\n", 1)[1].split("\n\nTranscript:", 1)[0]

    assert "Use constrained tools instead of guessing." in relevant_section
    assert any("Use constrained tools instead of guessing." in item for item in metadata["relevant_memory"]["selected_notes"])
    assert metadata["relevant_memory"]["selected_durable_count"] == 1
    assert metadata["relevant_memory"]["selected_sources"] == ["project-conventions"]
    assert metadata["relevant_memory"]["selected_kinds"] == ["durable"]
