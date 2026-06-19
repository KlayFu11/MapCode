from dataclasses import FrozenInstanceError

import pytest

from pico.core.context_usage import DEFAULT_CONTEXT_WINDOW
from pico.core.model_request_budget import (
    DEFAULT_PROMPT_SAFETY_MARGIN_TOKENS,
    FALLBACK_MODEL_INPUT_BUDGET_TOKENS,
    MODEL_REQUEST_TOKEN_ESTIMATION_METHOD,
    ModelRequestBudget,
    estimate_model_request_tokens,
)


def _budget(**overrides) -> ModelRequestBudget:
    values = {
        "provider": "openai",
        "model": "gpt-test",
        "model_input_budget_tokens": 32_768,
        "prompt_safety_margin_tokens": 1_024,
        "estimation_method": MODEL_REQUEST_TOKEN_ESTIMATION_METHOD,
        "source": "fallback",
    }
    values.update(overrides)
    return ModelRequestBudget(**values)


def test_model_request_budget_defines_runtime_owned_fallback_defaults():
    assert FALLBACK_MODEL_INPUT_BUDGET_TOKENS == 32_768
    assert DEFAULT_PROMPT_SAFETY_MARGIN_TOKENS == 1_024
    assert MODEL_REQUEST_TOKEN_ESTIMATION_METHOD == "ceil(chars / 4)"
    assert FALLBACK_MODEL_INPUT_BUDGET_TOKENS != DEFAULT_CONTEXT_WINDOW


def test_model_request_budget_is_immutable_input_gate_fact():
    budget = _budget()

    assert budget.provider == "openai"
    assert budget.model == "gpt-test"
    assert budget.model_input_budget_tokens == 32_768
    assert budget.prompt_safety_margin_tokens == 1_024
    assert budget.estimation_method == "ceil(chars / 4)"
    assert budget.source == "fallback"

    with pytest.raises(FrozenInstanceError):
        budget.model_input_budget_tokens = 200_000


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        ("", 0),
        ("a", 1),
        ("abcd", 1),
        ("abcde", 2),
        ("a" * 15, 4),
        ("a" * 16, 4),
        ("a" * 17, 5),
    ],
)
def test_estimate_model_request_tokens_uses_stable_ceil_chars_div_4(text, tokens):
    assert estimate_model_request_tokens(text) == tokens


def test_request_over_budget_uses_estimated_tokens_plus_margin():
    budget = _budget(
        model_input_budget_tokens=10,
        prompt_safety_margin_tokens=2,
    )

    assert budget.estimate_request_tokens("a" * 32) == 8
    assert budget.request_over_budget("a" * 32) is False
    assert budget.estimate_request_tokens("a" * 33) == 9
    assert budget.request_over_budget("a" * 33) is True


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("model_input_budget_tokens", 0, "model_input_budget_tokens"),
        ("prompt_safety_margin_tokens", -1, "prompt_safety_margin_tokens"),
        ("prompt_safety_margin_tokens", 32_768, "prompt_safety_margin_tokens"),
        ("estimation_method", "tokenizer", "estimation_method"),
        ("source", "default_context_window", "source"),
    ],
)
def test_model_request_budget_rejects_invalid_gate_configuration(field, value, message):
    with pytest.raises(ValueError, match=message):
        _budget(**{field: value})
