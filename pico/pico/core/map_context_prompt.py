"""Prompt render and build-result DTOs for map context injection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pico.core.map_context import MapContextResult


REPO_MAP_NAVIGATION_CONTRACT = """[Repo Map - Navigation Context Only]
The following repo map shows selected code-structure signatures only, not complete or authoritative file contents.
Use it only to decide which files and symbols to inspect.
Do not treat repo map snippets as authoritative full file content.
Before relying on implementation details or editing any existing file, use read_file to inspect the complete current source.
Repo map content does not satisfy Pico's prior-read or freshness requirement."""

BROADER_CONTEXT_FALLBACK_NOTICE = (
    "No specific focus files were confirmed. Broad repository context is provided "
    "for navigation."
)


def render_repo_map_navigation_text(result: MapContextResult | None) -> str:
    """Render the complete navigation contract from structured map context."""
    if result is None:
        return ""

    active_result = result.active_result
    focus_files_display = ", ".join(active_result.focus_fnames) or "none"
    is_broad_fallback = (
        result.stage == "fallback"
        and result.selection_decision is not None
        and result.selection_decision.fallback_mode == "broad_map"
    )
    mode = "broad_fallback" if is_broad_fallback else "focused"
    status_lines = [
        f"Branch: {result.branch}",
        f"Mode: {mode}",
        f"Focus files (read these first): {focus_files_display}",
    ]
    if is_broad_fallback:
        status_lines.append(BROADER_CONTEXT_FALLBACK_NOTICE)

    return "\n".join(
        (
            REPO_MAP_NAVIGATION_CONTRACT,
            "",
            *status_lines,
            "",
            active_result.repo_map_text,
        )
    )


def hash_repo_map_section_text(section_text: str) -> str:
    digest = sha256(str(section_text).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


EMPTY_REPO_MAP_SECTION_HASH = hash_repo_map_section_text("")

PROMPT_BUDGET_METADATA_KEYS = (
    "model_input_budget_tokens",
    "prompt_safety_margin_tokens",
    "active_repo_map_reservation_tokens",
    "base_prompt_budget_tokens",
    "estimated_request_tokens",
    "request_over_budget",
    "model_request_budget_source",
)

PromptPurpose = Literal[
    "main_model",
    "prompt_preview",
    "evaluation",
    "step_limit_summary",
]


@dataclass(frozen=True)
class RepoMapSectionRender:
    section_text: str
    section_rendered: bool
    contract_rendered: bool
    fallback_notice_rendered: bool
    map_body_raw_chars: int
    map_body_rendered_chars: int
    section_rendered_chars: int
    section_rendered_hash: str
    base_prompt_reduction_applied: bool
    omission_reason: str | None

    def __post_init__(self) -> None:
        self._validate_non_negative_int("map_body_raw_chars", self.map_body_raw_chars)
        self._validate_non_negative_int(
            "map_body_rendered_chars",
            self.map_body_rendered_chars,
        )
        self._validate_non_negative_int(
            "section_rendered_chars",
            self.section_rendered_chars,
        )
        if self.section_rendered_chars != len(self.section_text):
            raise ValueError("section_rendered_chars must match section_text length")
        if self.section_rendered_hash != hash_repo_map_section_text(self.section_text):
            raise ValueError("section_rendered_hash must match section_text")
        if self.map_body_rendered_chars > self.map_body_raw_chars:
            raise ValueError("map_body_rendered_chars must not exceed raw chars")
        if self.section_rendered:
            self._validate_rendered_state()
        else:
            self._validate_omitted_state()

    @classmethod
    def omitted(
        cls,
        omission_reason: str,
        *,
        map_body_raw_chars: int,
        base_prompt_reduction_applied: bool,
    ) -> "RepoMapSectionRender":
        return cls(
            section_text="",
            section_rendered=False,
            contract_rendered=False,
            fallback_notice_rendered=False,
            map_body_raw_chars=map_body_raw_chars,
            map_body_rendered_chars=0,
            section_rendered_chars=0,
            section_rendered_hash=EMPTY_REPO_MAP_SECTION_HASH,
            base_prompt_reduction_applied=base_prompt_reduction_applied,
            omission_reason=omission_reason,
        )

    def _validate_rendered_state(self) -> None:
        if not self.contract_rendered:
            raise ValueError("rendered repo map section requires contract_rendered")
        if self.omission_reason is not None:
            raise ValueError("rendered repo map section must not set omission_reason")

    def _validate_omitted_state(self) -> None:
        if self.section_text:
            raise ValueError("omitted repo map section must have empty section_text")
        if self.contract_rendered:
            raise ValueError("omitted repo map section must not render contract")
        if self.fallback_notice_rendered:
            raise ValueError("omitted repo map section must not render fallback notice")
        if self.map_body_rendered_chars != 0:
            raise ValueError("omitted repo map section must render zero map body chars")
        if self.section_rendered_chars != 0:
            raise ValueError("omitted repo map section must render zero section chars")
        if self.section_rendered_hash != EMPTY_REPO_MAP_SECTION_HASH:
            raise ValueError("omitted repo map section must use empty section hash")
        if not self.omission_reason:
            raise ValueError("omission_reason must be set for omitted repo map section")

    @staticmethod
    def _validate_non_negative_int(field: str, value: object) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{field} must be a non-negative integer")


@dataclass(frozen=True)
class PromptInjectionEvidence:
    section_rendered: bool
    contract_rendered: bool
    fallback_notice_rendered: bool
    map_body_raw_chars: int
    map_body_rendered_chars: int
    section_rendered_chars: int
    section_rendered_hash: str
    base_prompt_reduction_applied: bool
    omission_reason: str | None

    @classmethod
    def from_section_render(
        cls,
        render: RepoMapSectionRender,
    ) -> "PromptInjectionEvidence":
        return cls(
            section_rendered=render.section_rendered,
            contract_rendered=render.contract_rendered,
            fallback_notice_rendered=render.fallback_notice_rendered,
            map_body_raw_chars=render.map_body_raw_chars,
            map_body_rendered_chars=render.map_body_rendered_chars,
            section_rendered_chars=render.section_rendered_chars,
            section_rendered_hash=render.section_rendered_hash,
            base_prompt_reduction_applied=render.base_prompt_reduction_applied,
            omission_reason=render.omission_reason,
        )


@dataclass(frozen=True)
class PromptBuildResult:
    prompt: str
    metadata: Mapping[str, object]
    repo_map_render: RepoMapSectionRender | None

    def __post_init__(self) -> None:
        missing_keys = [
            key for key in PROMPT_BUDGET_METADATA_KEYS if key not in self.metadata
        ]
        if missing_keys:
            raise ValueError(f"metadata missing required key: {missing_keys[0]}")
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )
