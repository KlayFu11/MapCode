from pathlib import Path

from pico.core.map_context import MapContextCoordinator
from pico.core.model_request_budget import ModelRequestBudget
from pico.core.runtime import Pico
from pico.core.session_store import SessionStore
from pico.core.workspace import WorkspaceContext
from pico.features.map_engine.engine import MapEngine
from pico.testing import ScriptedModelClient


def _workspace(tmp_path: Path):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return WorkspaceContext.build(tmp_path)


def _runtime(tmp_path: Path, **kwargs) -> Pico:
    return Pico(
        model_client=ScriptedModelClient([]),
        workspace=_workspace(tmp_path),
        session_store=SessionStore(tmp_path / ".pico" / "sessions"),
        approval_policy="auto",
        **kwargs,
    )


def test_runtime_starts_with_map_engine_disabled_and_no_current_map(tmp_path):
    agent = _runtime(tmp_path)

    assert agent.feature_enabled("map_engine") is False
    assert agent.map_engine is None
    assert agent.map_context_coordinator is None
    assert agent.current_map_context is None
    assert isinstance(agent.model_request_budget, ModelRequestBudget)


def test_runtime_enabled_map_engine_assembles_objects_without_eager_index(
    tmp_path,
    monkeypatch,
):
    def fail_if_indexed(self):
        raise AssertionError("runtime startup must not build a MapEngine index")

    monkeypatch.setattr(MapEngine, "ensure_index", fail_if_indexed)

    agent = _runtime(tmp_path, feature_flags={"map_engine": True})

    assert agent.feature_enabled("map_engine") is True
    assert isinstance(agent.map_engine, MapEngine)
    assert isinstance(agent.map_context_coordinator, MapContextCoordinator)
    assert agent.map_context_coordinator.runtime is agent
    assert agent.map_context_coordinator.map_engine is agent.map_engine
    assert agent.map_context_coordinator.run_store is agent.run_store
    assert agent.current_map_context is None
    assert getattr(agent.map_engine, "_symbol_index") is None
