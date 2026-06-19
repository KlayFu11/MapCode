"""Runtime-owned MapContext and evidence artifact DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TYPE_CHECKING

from pico.core.map_selector import SelectionDecision
from pico.features.map_engine.models import MapContextEvidence, MapResult, PromptAnalysis

if TYPE_CHECKING:
    from pico.core.map_context_prompt import PromptInjectionEvidence


@dataclass(frozen=True)
class MapResultEvidence:
    mode: Literal["broad", "focused"]
    focus_fnames: tuple[str, ...]
    rendered_files: tuple[str, ...]
    rendered_symbols: tuple[str, ...]
    evidence: MapContextEvidence

    @classmethod
    def from_map_result(cls, result: MapResult) -> "MapResultEvidence":
        return cls(
            mode=result.mode,
            focus_fnames=result.focus_fnames,
            rendered_files=result.rendered_files,
            rendered_symbols=result.rendered_symbols,
            evidence=result.evidence,
        )


@dataclass(frozen=True)
class MapContextResult:
    map_context_id: str
    branch: Literal["specific", "fuzzy"]
    stage: Literal["execution", "fallback"]
    active_result: MapResult
    broad_result: MapResult | None
    selection_decision: SelectionDecision | None
    selector_model_calls: int
    prompt_injection: PromptInjectionEvidence | None
    repo_map_artifact_path: str | None
    evidence_artifact_path: str | None

    def __post_init__(self) -> None:
        if not self.map_context_id.startswith("mapctx_"):
            raise ValueError("map_context_id must start with mapctx_")
        if self.branch == "specific":
            if self.broad_result is not None or self.selection_decision is not None:
                raise ValueError("specific branch must not include selector state")
            if self.selector_model_calls != 0:
                raise ValueError("specific branch selector_model_calls must be 0")
        else:
            if self.broad_result is None or self.selection_decision is None:
                raise ValueError("fuzzy branch requires broad_result and selection_decision")
            if (
                self.broad_result.evidence.index_snapshot_id
                != self.active_result.evidence.index_snapshot_id
            ):
                raise ValueError("Branch B results must share index_snapshot_id")
            expected_calls = 1 if self.selection_decision.selector_result is not None else 0
            if self.selector_model_calls != expected_calls:
                raise ValueError("selector_model_calls must match selection_decision")
        if self.stage == "fallback":
            if self.active_result != self.broad_result:
                raise ValueError("fallback stage active_result must reuse broad_result")
            if (
                self.selection_decision is None
                or self.selection_decision.fallback_mode != "broad_map"
            ):
                raise ValueError("fallback stage requires broad_map selection_decision")
        self._validate_prompt_artifact_state()

    def _validate_prompt_artifact_state(self) -> None:
        has_prompt_injection = self.prompt_injection is not None
        has_repo_artifact = self.repo_map_artifact_path is not None
        has_evidence_artifact = self.evidence_artifact_path is not None
        if len({has_prompt_injection, has_repo_artifact, has_evidence_artifact}) != 1:
            raise ValueError("prompt injection and artifact paths must be set together")


@dataclass(frozen=True)
class MapEvidenceArtifact:
    schema_version: str
    map_context_id: str
    run_id: str
    branch: Literal["specific", "fuzzy"]
    stage: Literal["execution", "fallback"]
    index_snapshot_id: str
    analysis: PromptAnalysis
    broad_result: MapResultEvidence | None
    active_result: MapResultEvidence
    selection_decision: SelectionDecision | None
    prompt_injection: PromptInjectionEvidence
    repo_map_artifact_path: str

    def __post_init__(self) -> None:
        if self.index_snapshot_id != self.active_result.evidence.index_snapshot_id:
            raise ValueError("index_snapshot_id must match active_result evidence")
        if self.analysis != self.active_result.evidence.analysis:
            raise ValueError("analysis must match active_result evidence")
        if (
            self.broad_result is not None
            and self.broad_result.evidence.index_snapshot_id != self.index_snapshot_id
        ):
            raise ValueError("broad_result must share index_snapshot_id")
