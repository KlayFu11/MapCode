"""Runtime-owned selector request and decision DTOs."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SelectorModelRequest:
    system_prompt: str
    user_prompt: str
    visible_paths: tuple[str, ...]


@dataclass(frozen=True)
class SelectorResult:
    suggested_files: tuple[str, ...]
    invalid_files: tuple[str, ...]
    excess_files: tuple[str, ...]
    reasoning: str
    parse_error: str | None


FallbackReason = Literal[
    "one_shot_no_confirm",
    "selector_request_over_budget",
    "selector_no_valid_files",
    "user_selected_broad",
    "user_cancelled",
    "invalid_confirmation",
]


@dataclass(frozen=True)
class SelectionDecision:
    selector_result: SelectorResult | None
    confirmed_files: tuple[str, ...]
    fallback_mode: Literal["none", "broad_map"]
    fallback_reason: FallbackReason | None

    def __post_init__(self) -> None:
        if self.fallback_mode == "none":
            if not self.confirmed_files:
                raise ValueError("confirmed_files must be non-empty")
            if self.fallback_reason is not None:
                raise ValueError("fallback_reason must be None")
            return

        if self.confirmed_files:
            raise ValueError("confirmed_files must be empty for broad fallback")
        if self.fallback_reason is None:
            raise ValueError("fallback_reason must be set for broad fallback")
        if (
            self.selector_result is None
            and self.fallback_reason
            not in ("one_shot_no_confirm", "selector_request_over_budget")
        ):
            raise ValueError("selector_result must be retained after selector call")

    @classmethod
    def broad_fallback(
        cls,
        reason: FallbackReason,
        selector_result: SelectorResult | None = None,
    ) -> "SelectionDecision":
        return cls(
            selector_result=selector_result,
            confirmed_files=(),
            fallback_mode="broad_map",
            fallback_reason=reason,
        )

    @classmethod
    def from_single_choice(
        cls,
        selector_result: SelectorResult,
        answer: str,
    ) -> "SelectionDecision":
        if answer == "接受全部建议":
            if not selector_result.suggested_files:
                raise ValueError("suggested_files must be non-empty to accept all")
            return cls(
                selector_result=selector_result,
                confirmed_files=selector_result.suggested_files,
                fallback_mode="none",
                fallback_reason=None,
            )
        if answer == "使用 broad map":
            return cls.broad_fallback("user_selected_broad", selector_result)
        if answer == "":
            return cls.broad_fallback("user_cancelled", selector_result)
        return cls.broad_fallback("invalid_confirmation", selector_result)
