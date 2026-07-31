import ast
from pathlib import Path


def _python_files(root):
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return tuple(modules)


def _is_module_or_child(module, prefix):
    return module == prefix or module.startswith(f"{prefix}.")


def test_core_modules_stay_below_entropy_budget():
    root = Path(__file__).resolve().parents[1]
    budgets = {
        "pico/core/runtime.py": 1000,
        "pico/core/runtime_events.py": 90,
        "pico/core/runtime_consumers.py": 90,
        "pico/core/artifacts.py": 130,
        "pico/core/task_state.py": 140,
        "pico/core/todo_ledger.py": 120,
        "pico/core/worker_manager.py": 220,
        "pico/core/context_manager.py": 690,
        "pico/core/map_context_reporter.py": 200,
        "pico/core/context_usage.py": 120,
        "pico/core/compact.py": 180,
        "pico/core/engine.py": 520,
        "pico/core/model_errors.py": 100,
        "pico/core/permissions.py": 140,
        "pico/core/tool_policy.py": 90,
        "pico/core/plan_mode.py": 140,
        "pico/core/tool_executor.py": 181,
        "pico/core/tool_profiles.py": 80,
        "pico/core/turn_history.py": 250,
        "pico/features/skills.py": 220,
        "pico/features/skills_bundled.py": 120,
        "pico/features/skills_runtime.py": 140,
        "pico/tools/registry.py": 360,
        "pico/tools/todos.py": 80,
        "pico/tools/agents.py": 90,
    }

    for relative_path, max_lines in budgets.items():
        line_count = len((root / relative_path).read_text(encoding="utf-8").splitlines())
        assert line_count <= max_lines, f"{relative_path} has {line_count} lines, budget is {max_lines}"


def test_map_engine_does_not_import_runtime_core_or_aider():
    root = Path(__file__).resolve().parents[1]
    map_engine_root = root / "pico" / "features" / "map_engine"
    forbidden_imports = {}

    for path in _python_files(map_engine_root):
        forbidden = [
            module
            for module in _imported_modules(path)
            if _is_module_or_child(module, "pico.core")
            or _is_module_or_child(module, "aider")
        ]
        if forbidden:
            forbidden_imports[str(path.relative_to(root))] = forbidden

    assert forbidden_imports == {}


def test_runtime_owned_dtos_do_not_live_in_map_engine_models():
    root = Path(__file__).resolve().parents[1]
    models_text = (root / "pico" / "features" / "map_engine" / "models.py").read_text(
        encoding="utf-8"
    )
    forbidden_names = (
        "SelectorModelRequest",
        "SelectorResult",
        "SelectionDecision",
        "MapContextResult",
        "MapEvidenceArtifact",
        "ModelRequestBudget",
        "RepoMapSectionRender",
        "PromptInjectionEvidence",
        "PromptBuildResult",
    )

    leaked_names = [name for name in forbidden_names if name in models_text]

    assert leaked_names == []


def test_model_request_budget_does_not_enter_map_engine_config():
    root = Path(__file__).resolve().parents[1]
    config_text = (root / "pico" / "features" / "map_engine" / "config.py").read_text(
        encoding="utf-8"
    )
    forbidden_terms = (
        "ModelRequestBudget",
        "FALLBACK_MODEL_INPUT_BUDGET_TOKENS",
        "DEFAULT_PROMPT_SAFETY_MARGIN_TOKENS",
        "ContextUsageAnalyzer",
        "DEFAULT_CONTEXT_WINDOW",
        "model_input_budget_tokens",
        "prompt_safety_margin_tokens",
    )

    leaked_terms = [term for term in forbidden_terms if term in config_text]

    assert leaked_terms == []
