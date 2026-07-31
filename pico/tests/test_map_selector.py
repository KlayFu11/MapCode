from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import get_args

import pytest

from pico.core.map_selector import (
    FallbackReason,
    SelectionDecision,
    SelectorModelRequest,
    SelectorResult,
    build_selector_request,
    parse_selector_output,
    render_selector_confirmation,
)


def _selector_result() -> SelectorResult:
    return SelectorResult(
        suggested_files=("pico/core/engine.py", "pico/core/runtime.py"),
        invalid_files=("secret.txt",),
        excess_files=("pico/tools/registry.py",),
        reasoning="Engine and Runtime are central to the requested flow.",
        parse_error=None,
    )


def _broad_result():
    return SimpleNamespace(
        repo_map_text="pico/core/engine.py:\n  class Engine",
        rendered_files=("pico/core/engine.py", "pico/core/runtime.py"),
    )


def _selector_catalog():
    return SimpleNamespace(
        candidate_paths=(
            "pico/core/engine.py",
            "pico/core/hidden.py",
            "pico/core/runtime.py",
            "pico/tests/test_engine.py",
        ),
        rendered_paths=("pico/core/runtime.py", "pico/tests/test_engine.py"),
        rendered_text="pico/core/runtime.py:\n  class Pico\n\npico/tests/test_engine.py:",
    )


def test_build_selector_request_uses_exact_roles_and_stable_visible_union():
    request = build_selector_request(
        "Investigate the Engine retry behavior.",
        _broad_result(),
        _selector_catalog(),
    )

    assert request.system_prompt == (
        "You are MapCode's Branch-B file selector.\n\n"
        "Your only job is to understand the user's request and select the most "
        "semantically relevant existing source files from the provided Broad Repo "
        "Map and Selector Candidate Catalog.\n\n"
        "You are not the main coding agent.\n"
        "Do not propose code changes.\n"
        "Do not propose patches.\n"
        "Do not propose test edits.\n"
        "Do not write implementation plans.\n"
        "Do not call or suggest tools.\n"
        "Do not infer that any selected file has already been read.\n"
        "Do not treat repo map snippets as complete file content.\n\n"
        "You must respond ONLY with a JSON object in this exact format:\n"
        "{\n"
        '  "suggested_files": ["relative/path/to/file.py"],\n'
        '  "reasoning": "brief explanation"\n'
        "}\n\n"
        "Rules:\n"
        "- Only include files shown in the Broad Repo Map or Selector Candidate "
        "Catalog in the selector input\n"
        "- Use repo-relative paths exactly as shown\n"
        "- Do not suggest new files\n"
        "- Return an empty list if no files are clearly relevant\n"
        "- Prefer implementation/source files over test files for normal analysis, "
        "bug fixing, and feature requests\n"
        "- Include test files only when the user explicitly asks about tests, test "
        "failures, pytest behavior, regression coverage, or when the test file is "
        "clearly necessary to understand the requested behavior\n"
        "- Return at most 5 files"
    )
    assert request.user_prompt == (
        "[User Request]\n"
        "Investigate the Engine retry behavior.\n\n"
        "[Broad Repo Map]\n"
        "pico/core/engine.py:\n  class Engine\n\n"
        "[Selector Candidate Catalog]\n"
        "pico/core/runtime.py:\n  class Pico\n\npico/tests/test_engine.py:"
    )
    assert request.visible_paths == (
        "pico/core/engine.py",
        "pico/core/runtime.py",
        "pico/tests/test_engine.py",
    )
    assert "directory" not in request.system_prompt.lower()


def test_parse_selector_output_keeps_only_visible_paths_in_model_order():
    result = parse_selector_output(
        """{
          "suggested_files": [
            "pico/tests/test_engine.py",
            "pico/core/hidden.py",
            "pico/core/engine.py",
            "pico/tests/test_engine.py"
          ],
          "reasoning": "The visible source and test file explain this flow."
        }""",
        frozenset(
            {
                "pico/core/engine.py",
                "pico/core/runtime.py",
                "pico/tests/test_engine.py",
            }
        ),
    )

    assert result.suggested_files == (
        "pico/tests/test_engine.py",
        "pico/core/engine.py",
    )
    assert result.invalid_files == ("pico/core/hidden.py",)
    assert result.excess_files == ()
    assert result.parse_error is None


def test_parse_selector_output_dedupes_and_places_extra_valid_paths_in_excess():
    allowed_files = frozenset(f"pico/core/{index}.py" for index in range(7))
    raw = (
        '{"suggested_files": ['
        '"pico/core/0.py", "pico/core/0.py", "pico/core/1.py", '
        '"pico/core/2.py", "pico/core/3.py", "pico/core/4.py", '
        '"pico/core/5.py", "pico/core/6.py"], '
        '"reasoning": "ranked"}'
    )

    result = parse_selector_output(raw, allowed_files)

    assert result.suggested_files == tuple(f"pico/core/{index}.py" for index in range(5))
    assert result.excess_files == ("pico/core/5.py", "pico/core/6.py")
    assert result.invalid_files == ()


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        '{"suggested_files": [], "reasoning": "ok", "extra": true}',
        '{"suggested_files": "pico/core/engine.py", "reasoning": "ok"}',
        '{"suggested_files": ["pico/core/engine.py"], "reasoning": 1}',
    ],
)
def test_parse_selector_output_rejects_invalid_full_json_contract(raw):
    result = parse_selector_output(raw, frozenset({"pico/core/engine.py"}))

    assert result.suggested_files == ()
    assert result.invalid_files == ()
    assert result.excess_files == ()
    assert result.reasoning == ""
    assert result.parse_error is not None


def test_parse_selector_output_does_not_clip_raw_json_before_parsing():
    raw = '{"suggested_files": ["pico/core/engine.py"], "reasoning": "' + (
        "x" * 501
    )
    raw += '"}'

    result = parse_selector_output(raw, frozenset({"pico/core/engine.py"}))

    assert result.suggested_files == ("pico/core/engine.py",)
    assert result.reasoning == "x" * 500
    assert result.parse_error is None


def test_render_selector_confirmation_keeps_the_entire_valid_group_visible():
    confirmation = render_selector_confirmation(
        ("pico/core/engine.py", "pico/core/runtime.py")
    )

    assert "pico/core/engine.py" in confirmation
    assert "pico/core/runtime.py" in confirmation
    assert "接受全部建议" in confirmation
    assert "使用 broad map" in confirmation


def test_selector_model_request_keeps_role_prompts_and_visible_paths():
    request = SelectorModelRequest(
        system_prompt="Return exact JSON.",
        user_prompt="[User Request]\nAnalyze the runtime.",
        visible_paths=("pico/core/engine.py", "pico/core/runtime.py"),
    )

    assert request.system_prompt == "Return exact JSON."
    assert request.user_prompt.startswith("[User Request]")
    assert request.visible_paths == ("pico/core/engine.py", "pico/core/runtime.py")

    with pytest.raises(FrozenInstanceError):
        request.system_prompt = "mutated"


def test_selector_result_tracks_valid_invalid_and_excess_paths():
    result = _selector_result()

    assert result.suggested_files == (
        "pico/core/engine.py",
        "pico/core/runtime.py",
    )
    assert result.invalid_files == ("secret.txt",)
    assert result.excess_files == ("pico/tools/registry.py",)
    assert result.parse_error is None


def test_fallback_reason_literal_matches_spec_range():
    assert get_args(FallbackReason) == (
        "one_shot_no_confirm",
        "selector_request_over_budget",
        "selector_no_valid_files",
        "user_selected_broad",
        "user_cancelled",
        "invalid_confirmation",
    )


def test_selection_decision_broad_fallback_sets_empty_confirmed_files():
    result = _selector_result()
    decision = SelectionDecision.broad_fallback(
        "selector_no_valid_files",
        selector_result=result,
    )

    assert decision.selector_result == result
    assert decision.confirmed_files == ()
    assert decision.fallback_mode == "broad_map"
    assert decision.fallback_reason == "selector_no_valid_files"


def test_selection_decision_from_accept_all_confirms_valid_suggestions_only():
    result = _selector_result()
    decision = SelectionDecision.from_single_choice(result, "接受全部建议")

    assert decision.selector_result == result
    assert decision.confirmed_files == result.suggested_files
    assert decision.fallback_mode == "none"
    assert decision.fallback_reason is None
    assert "secret.txt" not in decision.confirmed_files
    assert "pico/tools/registry.py" not in decision.confirmed_files


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ("使用 broad map", "user_selected_broad"),
        ("", "user_cancelled"),
        ("只接受第一个", "invalid_confirmation"),
    ],
)
def test_selection_decision_from_single_choice_maps_broad_fallbacks(answer, reason):
    decision = SelectionDecision.from_single_choice(_selector_result(), answer)

    assert decision.confirmed_files == ()
    assert decision.fallback_mode == "broad_map"
    assert decision.fallback_reason == reason


def test_selection_decision_rejects_accept_all_without_valid_suggestions():
    result = SelectorResult(
        suggested_files=(),
        invalid_files=("missing.py",),
        excess_files=(),
        reasoning="No valid file was visible.",
        parse_error=None,
    )

    with pytest.raises(ValueError, match="suggested_files"):
        SelectionDecision.from_single_choice(result, "接受全部建议")


def test_selection_decision_validates_none_mode_requires_confirmed_files():
    with pytest.raises(ValueError, match="confirmed_files"):
        SelectionDecision(
            selector_result=_selector_result(),
            confirmed_files=(),
            fallback_mode="none",
            fallback_reason=None,
        )


def test_selection_decision_keeps_selector_result_for_selector_fallbacks():
    with pytest.raises(ValueError, match="selector_result"):
        SelectionDecision.broad_fallback("selector_no_valid_files")
