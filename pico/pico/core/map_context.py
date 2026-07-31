"""Runtime-owned MapContext and evidence artifact DTOs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from typing import Literal, TYPE_CHECKING
from uuid import uuid4

from pico.core.map_context_prompt import PromptInjectionEvidence
from pico.core.map_selector import SelectionDecision
from pico.features.map_engine.models import (
    IndexStatus,
    MapContextEvidence,
    MapResult,
    PromptAnalysis,
    SelectorCandidateCatalog,
)

MAP_EVIDENCE_SCHEMA_VERSION = "mapcode.map-evidence.v1"

if TYPE_CHECKING:
    from pico.core.map_context_prompt import RepoMapSectionRender
    from pico.core.run_store import RunStore
    from pico.core.runtime import Pico
    from pico.core.task_state import TaskState
    from pico.features.map_engine.engine import MapEngine


@dataclass(frozen=True)
class MapContextCoordinator:
    runtime: "Pico"
    map_engine: "MapEngine"
    run_store: "RunStore"

    def analyze_turn(
        self,
        task_state: "TaskState",
        user_message: str,
    ) -> PromptAnalysis:
        index_status = self.map_engine.ensure_index()
        self.runtime.emit_trace(
            task_state,
            "map_index_status",
            _index_status_payload(index_status),
        )
        analysis = self.map_engine.analyze(user_message)
        self.runtime.emit_trace(
            task_state,
            "map_prompt_analyzed",
            _analysis_payload(analysis),
        )
        return analysis

    def prepare_specific(
        self,
        task_state: "TaskState",
        analysis: PromptAnalysis,
    ) -> "MapContextResult":
        result = self.map_engine.generate_focused(
            analysis,
            analysis.mentioned_files,
        )
        self._emit_map_result_trace(task_state, result)
        context = MapContextResult(
            map_context_id=_new_map_context_id(),
            branch="specific",
            stage="execution",
            active_result=result,
            broad_result=None,
            selection_decision=None,
            selector_model_calls=0,
            prompt_injection=None,
            repo_map_artifact_path=None,
            evidence_artifact_path=None,
        )
        self._record_map_context_summary(task_state, context)
        return context

    def prepare_broad(
        self,
        task_state: "TaskState",
        analysis: PromptAnalysis,
    ) -> MapResult:
        result = self.map_engine.generate_broad(analysis)
        self._emit_map_result_trace(task_state, result)
        return result

    def build_selector_catalog(
        self,
        task_state: "TaskState",
        broad_result: MapResult,
    ) -> SelectorCandidateCatalog:
        catalog = self.map_engine.build_selector_catalog()
        if catalog.index_snapshot_id != broad_result.evidence.index_snapshot_id:
            raise ValueError("selector catalog must share broad result snapshot")
        return catalog

    def prepare_fuzzy(
        self,
        task_state: "TaskState",
        broad_result: MapResult,
        decision: SelectionDecision,
    ) -> "MapContextResult":
        if decision.confirmed_files:
            active_result = self.map_engine.generate_focused(
                broad_result.evidence.analysis,
                decision.confirmed_files,
            )
            stage: Literal["execution", "fallback"] = "execution"
            self._emit_map_result_trace(task_state, active_result)
        else:
            active_result = broad_result
            stage = "fallback"

        context = MapContextResult(
            map_context_id=_new_map_context_id(),
            branch="fuzzy",
            stage=stage,
            active_result=active_result,
            broad_result=broad_result,
            selection_decision=decision,
            selector_model_calls=task_state.selector_model_calls,
            prompt_injection=None,
            repo_map_artifact_path=None,
            evidence_artifact_path=None,
        )
        self._record_map_context_summary(task_state, context)
        return context

    def finalize_prompt_context(
        self,
        task_state: "TaskState",
        result: "MapContextResult",
        repo_map_render: "RepoMapSectionRender",
    ) -> "MapContextResult":
        prompt_injection = PromptInjectionEvidence.from_section_render(
            repo_map_render
        )
        repo_map_path = self.run_store.write_text_artifact(
            task_state,
            "repo-map",
            repo_map_render.section_text,
        )
        repo_map_artifact_path = self._artifact_path(repo_map_path)
        artifact = MapEvidenceArtifact(
            schema_version=MAP_EVIDENCE_SCHEMA_VERSION,
            map_context_id=result.map_context_id,
            run_id=task_state.run_id,
            branch=result.branch,
            stage=result.stage,
            index_snapshot_id=result.active_result.evidence.index_snapshot_id,
            analysis=result.active_result.evidence.analysis,
            broad_result=(
                MapResultEvidence.from_map_result(result.broad_result)
                if result.broad_result is not None
                else None
            ),
            active_result=MapResultEvidence.from_map_result(result.active_result),
            selection_decision=result.selection_decision,
            prompt_injection=prompt_injection,
            repo_map_artifact_path=repo_map_artifact_path,
        )
        evidence_path = self.run_store.write_json_artifact(
            task_state,
            "map-evidence",
            _json_safe(artifact),
        )
        evidence_artifact_path = self._artifact_path(evidence_path)
        finalized = MapContextResult(
            map_context_id=result.map_context_id,
            branch=result.branch,
            stage=result.stage,
            active_result=result.active_result,
            broad_result=result.broad_result,
            selection_decision=result.selection_decision,
            selector_model_calls=result.selector_model_calls,
            prompt_injection=prompt_injection,
            repo_map_artifact_path=repo_map_artifact_path,
            evidence_artifact_path=evidence_artifact_path,
        )
        self._record_map_context_summary(task_state, finalized)
        self.runtime.emit_trace(
            task_state,
            "map_generated",
            {
                "map_context_id": finalized.map_context_id,
                "index_snapshot_id": finalized.active_result.evidence.index_snapshot_id,
                "artifact_paths": [
                    repo_map_artifact_path,
                    evidence_artifact_path,
                ],
                "repo_map_artifact_path": repo_map_artifact_path,
                "evidence_artifact_path": evidence_artifact_path,
                "section_rendered": prompt_injection.section_rendered,
                "section_rendered_chars": prompt_injection.section_rendered_chars,
                "section_rendered_hash": prompt_injection.section_rendered_hash,
                "omission_reason": prompt_injection.omission_reason,
            },
        )
        return finalized

    def _emit_map_result_trace(
        self,
        task_state: "TaskState",
        result: MapResult,
    ) -> None:
        self.runtime.emit_trace(
            task_state,
            "map_context_ranked",
            _ranked_payload(result),
        )
        self.runtime.emit_trace(
            task_state,
            "map_context_selected",
            _selected_payload(result),
        )

    def _record_map_context_summary(
        self,
        task_state: "TaskState",
        result: "MapContextResult",
    ) -> None:
        task_state.map_context_summary = _map_context_summary(result)
        self.run_store.write_task_state(task_state)

    def _artifact_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.runtime.root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()


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
            if self.selection_decision.confirmed_files:
                if self.stage != "execution":
                    raise ValueError("confirmed selection must use execution stage")
                if self.active_result.mode != "focused":
                    raise ValueError("confirmed selection must use focused active_result")
                if (
                    self.active_result.focus_fnames
                    != self.selection_decision.confirmed_files
                ):
                    raise ValueError(
                        "focused active_result must match confirmed_files"
                    )
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


def _new_map_context_id() -> str:
    return f"mapctx_{uuid4().hex[:12]}"


def _index_status_payload(status: IndexStatus) -> dict[str, object]:
    return {
        "index_snapshot_id": status.index_snapshot_id,
        "cache_status": _json_safe(status.cache_status),
        "file_count": status.file_count,
        "definition_count": status.definition_count,
        "reference_count": status.reference_count,
    }


def _analysis_payload(analysis: PromptAnalysis) -> dict[str, object]:
    return {
        "branch": analysis.branch,
        "mentioned_files": list(analysis.mentioned_files),
        "mentioned_idents": list(analysis.mentioned_idents),
        "effective_symbol_hits": list(analysis.effective_symbol_hits),
        "path_ident_hits": list(analysis.path_ident_hits),
        "path_ident_hit_files": {
            ident: list(paths)
            for ident, paths in analysis.path_ident_hit_files.items()
        },
    }


def _ranked_payload(result: MapResult) -> dict[str, object]:
    ranking = result.evidence.ranking
    return {
        "index_snapshot_id": result.evidence.index_snapshot_id,
        "stage": result.mode,
        "algorithm": ranking.algorithm,
        "focus_fnames": list(ranking.focus_fnames),
        "focus_personalization_files": list(ranking.focus_personalization_files),
        "path_personalization_files": list(ranking.path_personalization_files),
        "personalization_files": list(ranking.personalization_files),
        "top_ranked_files": list(ranking.top_ranked_files),
        "top_rank_contributors": _top_rank_contributors_payload(result),
        "duration_ms": result.evidence.duration_ms,
    }


def _top_rank_contributors_payload(result: MapResult) -> list[dict[str, object]]:
    contributors = []
    for rendered_file in result.evidence.rendered_files:
        for contributor in rendered_file.top_rank_contributors:
            contributors.append(
                {
                    "path": rendered_file.path,
                    "identifier": contributor.identifier,
                    "weight_multiplier": contributor.weight_multiplier,
                    "weight_reason_codes": list(contributor.weight_reason_codes),
                }
            )
    return contributors


def _selected_payload(result: MapResult) -> dict[str, object]:
    rendering = result.evidence.rendering
    return {
        "index_snapshot_id": result.evidence.index_snapshot_id,
        "stage": result.mode,
        "rendered_files": list(result.rendered_files),
        "rendered_symbols": list(result.rendered_symbols),
        "omitted_files": [
            omitted_file.path
            for omitted_file in result.evidence.omitted_files
        ],
        "map_budget_tokens": rendering.target_tokens,
        "map_budget_chars": rendering.target_chars,
        "used_chars": rendering.used_chars,
        "estimated_tokens": rendering.estimated_tokens,
        "budget_reduction_applied": rendering.budget_reduction_applied,
        "focus_truncated": rendering.focus_truncated,
        "omission_reason": _first_omission_reason(result),
    }


def _first_omission_reason(result: MapResult) -> str | None:
    if not result.evidence.omitted_files:
        return None
    return result.evidence.omitted_files[0].omission_reason


def _map_context_summary(result: MapContextResult) -> dict[str, object]:
    return {
        "enabled": True,
        "map_context_id": result.map_context_id,
        "branch": result.branch,
        "stage": result.stage,
        "focus_fnames": list(result.active_result.focus_fnames),
        "rendered_files": list(result.active_result.rendered_files),
        "index_snapshot_id": result.active_result.evidence.index_snapshot_id,
        "selector_model_calls": result.selector_model_calls,
        "repo_map_artifact_path": result.repo_map_artifact_path or "",
        "evidence_artifact_path": result.evidence_artifact_path or "",
    }


def _json_safe(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_json_safe(item) for item in value)
    if isinstance(value, Path):
        return value.as_posix()
    return value
