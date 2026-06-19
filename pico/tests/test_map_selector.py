from dataclasses import FrozenInstanceError
from typing import get_args

import pytest

from pico.core.map_selector import (
    FallbackReason,
    SelectionDecision,
    SelectorModelRequest,
    SelectorResult,
)


def _selector_result() -> SelectorResult:
    return SelectorResult(
        suggested_files=("pico/core/engine.py", "pico/core/runtime.py"),
        invalid_files=("secret.txt",),
        excess_files=("pico/tools/registry.py",),
        reasoning="Engine and Runtime are central to the requested flow.",
        parse_error=None,
    )


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
