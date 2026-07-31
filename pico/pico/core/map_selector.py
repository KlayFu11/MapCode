"""Runtime-owned selector request and decision DTOs."""

import json
from dataclasses import dataclass
from typing import Literal

from pico.features.map_engine.models import MapResult, SelectorCandidateCatalog


MAX_SELECTOR_SUGGESTED_FILES = 5
SELECTOR_REASONING_MAX_CHARS = 500

_SELECTOR_SYSTEM_PROMPT = """You are MapCode's Branch-B file selector.

Your only job is to understand the user's request and select the most semantically relevant existing source files from the provided Broad Repo Map and Selector Candidate Catalog.

You are not the main coding agent.
Do not propose code changes.
Do not propose patches.
Do not propose test edits.
Do not write implementation plans.
Do not call or suggest tools.
Do not infer that any selected file has already been read.
Do not treat repo map snippets as complete file content.

You must respond ONLY with a JSON object in this exact format:
{
  "suggested_files": ["relative/path/to/file.py"],
  "reasoning": "brief explanation"
}

Rules:
- Only include files shown in the Broad Repo Map or Selector Candidate Catalog in the selector input
- Use repo-relative paths exactly as shown
- Do not suggest new files
- Return an empty list if no files are clearly relevant
- Prefer implementation/source files over test files for normal analysis, bug fixing, and feature requests
- Include test files only when the user explicitly asks about tests, test failures, pytest behavior, regression coverage, or when the test file is clearly necessary to understand the requested behavior
- Return at most {max_selector_suggested_files} files"""


def build_selector_request(
    original_user_message: str,
    broad_result: MapResult,
    selector_catalog: SelectorCandidateCatalog,
) -> "SelectorModelRequest":
    """Build the provider-role-separated input from files visible to selector."""
    visible_paths = tuple(
        dict.fromkeys(broad_result.rendered_files + selector_catalog.rendered_paths)
    )
    user_prompt = (
        f"[User Request]\n{original_user_message}\n\n"
        f"[Broad Repo Map]\n{broad_result.repo_map_text}\n\n"
        f"[Selector Candidate Catalog]\n{selector_catalog.rendered_text}"
    )
    return SelectorModelRequest(
        system_prompt=_SELECTOR_SYSTEM_PROMPT.replace(
            "{max_selector_suggested_files}", str(MAX_SELECTOR_SUGGESTED_FILES)
        ),
        user_prompt=user_prompt,
        visible_paths=visible_paths,
    )


def parse_selector_output(raw: str, allowed_files: frozenset[str]) -> "SelectorResult":
    """Parse a complete selector response, then validate only visible paths."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        return _parse_error_result(f"invalid JSON: {error.msg}")

    if not isinstance(payload, dict):
        return _parse_error_result("selector output must be a JSON object")
    if set(payload) != {"suggested_files", "reasoning"}:
        return _parse_error_result(
            "selector output must contain exactly suggested_files and reasoning"
        )

    suggested_files = payload["suggested_files"]
    reasoning = payload["reasoning"]
    if not isinstance(suggested_files, list) or not all(
        isinstance(path, str) for path in suggested_files
    ):
        return _parse_error_result("suggested_files must be a list of strings")
    if not isinstance(reasoning, str):
        return _parse_error_result("reasoning must be a string")

    valid_files: list[str] = []
    invalid_files: list[str] = []
    seen_paths: set[str] = set()
    for path in suggested_files:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        if path in allowed_files:
            valid_files.append(path)
        else:
            invalid_files.append(path)

    return SelectorResult(
        suggested_files=tuple(valid_files[:MAX_SELECTOR_SUGGESTED_FILES]),
        invalid_files=tuple(invalid_files),
        excess_files=tuple(valid_files[MAX_SELECTOR_SUGGESTED_FILES:]),
        reasoning=reasoning[:SELECTOR_REASONING_MAX_CHARS],
        parse_error=None,
    )


def render_selector_confirmation(valid_files: tuple[str, ...]) -> str:
    """Render the complete valid suggestion group for the fixed confirmation UI."""
    file_lines = "\n".join(f"- {path}" for path in valid_files)
    return (
        "Selector 建议聚焦以下文件：\n"
        f"{file_lines}\n\n"
        "请选择“接受全部建议”或“使用 broad map”。"
    )


def _parse_error_result(parse_error: str) -> "SelectorResult":
    return SelectorResult(
        suggested_files=(),
        invalid_files=(),
        excess_files=(),
        reasoning="",
        parse_error=parse_error,
    )


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
