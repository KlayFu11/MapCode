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
from pico.config import ProviderConfig, resolve_model_request_budget


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


def _provider(name="openai", model="gpt-test") -> ProviderConfig:
    return ProviderConfig(
        name=name,
        protocol="openai",
        api_key="sk-test",
        base_url="https://example.test/v1",
        model=model,
    )


def test_resolve_model_request_budget_uses_fallback_for_unknown_provider_model(tmp_path):
    budget = resolve_model_request_budget(
        _provider(name="gateway", model="gateway-model"),
        start=tmp_path,
    )

    assert budget.provider == "gateway"
    assert budget.model == "gateway-model"
    assert budget.model_input_budget_tokens == FALLBACK_MODEL_INPUT_BUDGET_TOKENS
    assert budget.model_input_budget_tokens != DEFAULT_CONTEXT_WINDOW
    assert budget.prompt_safety_margin_tokens == DEFAULT_PROMPT_SAFETY_MARGIN_TOKENS
    assert budget.estimation_method == MODEL_REQUEST_TOKEN_ESTIMATION_METHOD
    assert budget.source == "fallback"


def test_resolve_model_request_budget_uses_provider_profile_values(tmp_path):
    (tmp_path / ".pico.toml").write_text(
        "\n".join(
            [
                "[providers.deepseek]",
                'protocol = "anthropic"',
                'model = "deepseek-v4-pro"',
                "model_input_budget_tokens = 65536",
                "prompt_safety_margin_tokens = 2048",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    budget = resolve_model_request_budget(
        _provider(name="deepseek", model="deepseek-v4-pro"),
        start=tmp_path,
    )

    assert budget.model_input_budget_tokens == 65_536
    assert budget.prompt_safety_margin_tokens == 2_048
    assert budget.source == "provider_model"


def test_resolve_model_request_budget_project_section_overrides_provider_profile(tmp_path):
    (tmp_path / ".pico.toml").write_text(
        "\n".join(
            [
                "[model_request_budget]",
                "model_input_budget_tokens = 98304",
                "prompt_safety_margin_tokens = 4096",
                "",
                "[providers.deepseek]",
                'protocol = "anthropic"',
                'model = "deepseek-v4-pro"',
                "model_input_budget_tokens = 65536",
                "prompt_safety_margin_tokens = 2048",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    budget = resolve_model_request_budget(
        _provider(name="deepseek", model="deepseek-v4-pro"),
        start=tmp_path,
    )

    assert budget.model_input_budget_tokens == 98_304
    assert budget.prompt_safety_margin_tokens == 4_096
    assert budget.source == "explicit"


def test_resolve_model_request_budget_cli_values_override_project_section(tmp_path):
    (tmp_path / ".pico.toml").write_text(
        "\n".join(
            [
                "[model_request_budget]",
                "model_input_budget_tokens = 98304",
                "prompt_safety_margin_tokens = 4096",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    budget = resolve_model_request_budget(
        _provider(),
        start=tmp_path,
        model_input_budget_tokens=131_072,
        prompt_safety_margin_tokens=8_192,
    )

    assert budget.model_input_budget_tokens == 131_072
    assert budget.prompt_safety_margin_tokens == 8_192
    assert budget.source == "explicit"


def test_resolve_model_request_budget_rejects_invalid_explicit_config(tmp_path):
    (tmp_path / ".pico.toml").write_text(
        "\n".join(
            [
                "[model_request_budget]",
                'model_input_budget_tokens = "large"',
                "prompt_safety_margin_tokens = 1024",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="model_request_budget.model_input_budget_tokens"):
        resolve_model_request_budget(_provider(), start=tmp_path)
