import json
import subprocess

from pico import Pico, SessionStore, WorkspaceContext
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
