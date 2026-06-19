"""Runtime-owned model request input budget contracts."""

from dataclasses import dataclass
from typing import Literal, get_args


FALLBACK_MODEL_INPUT_BUDGET_TOKENS = 32_768
DEFAULT_PROMPT_SAFETY_MARGIN_TOKENS = 1_024
MODEL_REQUEST_TOKEN_ESTIMATION_METHOD = "ceil(chars / 4)"

BudgetSource = Literal["explicit", "provider_model", "fallback"]
_VALID_BUDGET_SOURCES = set(get_args(BudgetSource))


def estimate_model_request_tokens(text: str) -> int:
    return (len(str(text)) + 3) // 4


@dataclass(frozen=True)
class ModelRequestBudget:
    provider: str
    model: str
    model_input_budget_tokens: int
    prompt_safety_margin_tokens: int
    estimation_method: str
    source: BudgetSource

    def __post_init__(self) -> None:
        if not self._is_plain_int(self.model_input_budget_tokens):
            raise ValueError("model_input_budget_tokens must be an integer")
        if self.model_input_budget_tokens <= 0:
            raise ValueError("model_input_budget_tokens must be positive")
        if not self._is_plain_int(self.prompt_safety_margin_tokens):
            raise ValueError("prompt_safety_margin_tokens must be an integer")
        if self.prompt_safety_margin_tokens < 0:
            raise ValueError("prompt_safety_margin_tokens must be non-negative")
        if self.prompt_safety_margin_tokens >= self.model_input_budget_tokens:
            raise ValueError("prompt_safety_margin_tokens must be below input budget")
        if self.estimation_method != MODEL_REQUEST_TOKEN_ESTIMATION_METHOD:
            raise ValueError("estimation_method must be ceil(chars / 4)")
        if self.source not in _VALID_BUDGET_SOURCES:
            raise ValueError("source must be explicit, provider_model, or fallback")

    def estimate_request_tokens(self, text: str) -> int:
        return estimate_model_request_tokens(text)

    def request_over_budget(self, text: str) -> bool:
        estimated_request_tokens = self.estimate_request_tokens(text)
        return (
            estimated_request_tokens + self.prompt_safety_margin_tokens
            > self.model_input_budget_tokens
        )

    @staticmethod
    def _is_plain_int(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)
