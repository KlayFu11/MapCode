import json
import subprocess
from dataclasses import replace

from pico import Pico, SessionStore, WorkspaceContext
from pico.core.map_context_prompt import REPO_MAP_NAVIGATION_CONTRACT, RepoMapSectionRender
from pico.testing import ScriptedModelClient


def _git(repo, *args):
    subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=True,
        timeout=5,
    )


def _runtime(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text(
        "class AuthService:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "mapcode@example.test")
    _git(tmp_path, "config", "user.name", "MapCode Test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "fixture")
    return Pico(
        model_client=ScriptedModelClient(
            [
                '<tool name="list_files" path="."></tool>',
                "<final>Done.</final>",
            ]
        ),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".pico" / "sessions"),
        approval_policy="auto",
        feature_flags={"map_engine": True},
    )


class _RecordingCoordinator:
    def __init__(self, delegate):
        self.delegate = delegate
        self.finalize_calls = []

    def analyze_turn(self, task_state, user_message):
        return self.delegate.analyze_turn(task_state, user_message)

    def prepare_specific(self, task_state, analysis):
        return self.delegate.prepare_specific(task_state, analysis)

    def finalize_prompt_context(self, task_state, result, repo_map_render):
        self.finalize_calls.append((task_state, result, repo_map_render))
        return self.delegate.finalize_prompt_context(
            task_state,
            result,
            repo_map_render,
        )


def test_first_main_build_persists_complete_repo_map_evidence_before_prompt_event(
    tmp_path,
):
    agent = _runtime(tmp_path)
    coordinator = _RecordingCoordinator(agent.map_context_coordinator)
    agent.map_context_coordinator = coordinator
    build_results = []
    original_build = agent._build_prompt_and_metadata

    def record_main_build(user_message, *, purpose):
        result = original_build(user_message, purpose=purpose)
        if purpose == "main_model":
            build_results.append(result)
        return result

    agent._build_prompt_and_metadata = record_main_build

    assert agent.engine.ask("Inspect src/auth.py.") == "Done."

    assert len(build_results) == 2
    assert len(coordinator.finalize_calls) == 1
    _, prepared, rendered = coordinator.finalize_calls[0]
    assert rendered is build_results[0].repo_map_render
    assert rendered.section_rendered is True

    artifacts_dir = agent.current_run_dir / "artifacts"
    repo_map_path = artifacts_dir / "repo-map-001.txt"
    evidence_path = artifacts_dir / "map-evidence-001.json"
    assert repo_map_path.read_text(encoding="utf-8") == rendered.section_text
    assert build_results[1].repo_map_render.section_text == rendered.section_text
    assert [path.name for path in artifacts_dir.glob("repo-map-*.txt")] == [
        "repo-map-001.txt"
    ]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["map_context_id"] == prepared.map_context_id
    assert evidence["repo_map_artifact_path"].endswith("repo-map-001.txt")
    assert "evidence_artifact_path" not in evidence
    assert "repo_map_text" not in evidence["active_result"]

    trace_rows = [
        json.loads(line)
        for line in (agent.current_run_dir / "trace.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    trace_events = [row["event"] for row in trace_rows]
    assert trace_events.index("map_generated") < trace_events.index("prompt_built")
    assert trace_events.index("prompt_built") < trace_events.index("model_requested")

    ranked = next(row for row in trace_rows if row["event"] == "map_context_ranked")
    selected = next(
        row for row in trace_rows if row["event"] == "map_context_selected"
    )
    prompt_built = next(row for row in trace_rows if row["event"] == "prompt_built")
    metadata = build_results[0].metadata
    assert ranked["index_snapshot_id"] == evidence["index_snapshot_id"]
    assert selected["rendered_files"] == evidence["active_result"]["rendered_files"]
    assert prompt_built["repo_map_render"] == metadata["map_context"]
    assert prompt_built["request_budget"] == {
        key: metadata[key]
        for key in (
            "model_input_budget_tokens",
            "prompt_safety_margin_tokens",
            "active_repo_map_reservation_tokens",
            "base_prompt_budget_tokens",
            "estimated_request_tokens",
            "request_over_budget",
            "model_request_budget_source",
            "base_prompt_over_budget_with_repo_map_reservation",
        )
    }
    assert "repo_map_text" not in prompt_built["repo_map_render"]
    assert "sections" not in prompt_built["request_budget"]


def test_omitted_first_main_build_persists_empty_repo_map_evidence_before_fallback(
    tmp_path,
):
    agent = _runtime(tmp_path)
    coordinator = _RecordingCoordinator(agent.map_context_coordinator)
    agent.map_context_coordinator = coordinator
    build_results = []
    original_build = agent._build_prompt_and_metadata

    def force_first_main_render_omitted(user_message, *, purpose):
        result = original_build(user_message, purpose=purpose)
        if purpose != "main_model":
            return result
        if not build_results:
            original_render = result.repo_map_render
            assert original_render is not None
            omitted_render = RepoMapSectionRender.omitted(
                "base_prompt_cannot_fit_with_repo_map_reservation",
                map_body_raw_chars=original_render.map_body_raw_chars,
                base_prompt_reduction_applied=original_render.base_prompt_reduction_applied,
            )
            metadata = dict(result.metadata)
            metadata["map_context"] = {
                "section_rendered": omitted_render.section_rendered,
                "contract_rendered": omitted_render.contract_rendered,
                "fallback_notice_rendered": omitted_render.fallback_notice_rendered,
                "map_body_raw_chars": omitted_render.map_body_raw_chars,
                "map_body_rendered_chars": omitted_render.map_body_rendered_chars,
                "section_rendered_chars": omitted_render.section_rendered_chars,
                "section_rendered_hash": omitted_render.section_rendered_hash,
                "base_prompt_reduction_applied": omitted_render.base_prompt_reduction_applied,
                "omission_reason": omitted_render.omission_reason,
            }
            result = replace(
                result,
                metadata=metadata,
                repo_map_render=omitted_render,
            )
        build_results.append(result)
        return result

    agent._build_prompt_and_metadata = force_first_main_render_omitted

    assert agent.engine.ask("Inspect src/auth.py.") == "Done."

    assert len(build_results) == 3
    assert len(coordinator.finalize_calls) == 1
    _, _, rendered = coordinator.finalize_calls[0]
    assert rendered is build_results[0].repo_map_render
    assert rendered.section_text == ""
    assert build_results[1].repo_map_render is None
    assert build_results[2].repo_map_render is None

    artifacts_dir = agent.current_run_dir / "artifacts"
    repo_map_path = artifacts_dir / "repo-map-001.txt"
    evidence_path = artifacts_dir / "map-evidence-001.json"
    assert repo_map_path.read_text(encoding="utf-8") == ""
    assert [path.name for path in artifacts_dir.glob("repo-map-*.txt")] == [
        "repo-map-001.txt"
    ]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["prompt_injection"]["section_rendered"] is False
    assert (
        evidence["prompt_injection"]["omission_reason"]
        == "base_prompt_cannot_fit_with_repo_map_reservation"
    )
    assert agent.current_task_state.selector_model_calls == 0
    assert all(
        REPO_MAP_NAVIGATION_CONTRACT not in prompt
        for prompt in agent.model_client.prompts
    )

    trace_events = [
        json.loads(line)["event"]
        for line in (agent.current_run_dir / "trace.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert trace_events.count("map_generated") == 1
    assert "map_context_failed" not in trace_events
