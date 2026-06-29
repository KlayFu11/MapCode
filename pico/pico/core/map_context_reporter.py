"""Console-safe projections for MapContext evidence."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from pico.core.map_context import MapContextResult
from pico.features.map_engine.models import IndexStatus, MapResult


@dataclass(frozen=True)
class MapEngineConsoleReport:
    title: str
    lines: tuple[str, ...]
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines", tuple(self.lines))
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    def to_text(self) -> str:
        return "\n".join((self.title, *self.lines))


@dataclass(frozen=True)
class MapEngineConsoleReporter:
    def render_index_status(self, status: IndexStatus) -> MapEngineConsoleReport:
        payload = {
            "cache_status": status.cache_status.read_status,
            "index_snapshot_id": status.index_snapshot_id,
            "file_count": status.file_count,
            "definition_count": status.definition_count,
            "reference_count": status.reference_count,
        }
        return MapEngineConsoleReport(
            title="MapEngine index",
            lines=(
                f"- cache: {status.cache_status.read_status}",
                f"- files: {status.file_count}",
                f"- definitions: {status.definition_count}",
                f"- references: {status.reference_count}",
                f"- snapshot: {status.index_snapshot_id}",
            ),
            payload=payload,
        )

    def render_context(self, result: MapContextResult) -> MapEngineConsoleReport:
        fallback_reason = (
            result.selection_decision.fallback_reason
            if result.selection_decision is not None
            else None
        )
        return self.render_map_result(
            result.active_result,
            branch=result.branch,
            stage=result.stage,
            selector_model_calls=result.selector_model_calls,
            fallback_reason=fallback_reason,
            repo_map_artifact_path=result.repo_map_artifact_path,
            evidence_artifact_path=result.evidence_artifact_path,
        )

    def render_map_result(
        self,
        result: MapResult,
        *,
        branch: Literal["specific", "fuzzy"],
        stage: Literal["execution", "fallback"],
        selector_model_calls: int = 0,
        fallback_reason: str | None = None,
        repo_map_artifact_path: str | None = None,
        evidence_artifact_path: str | None = None,
    ) -> MapEngineConsoleReport:
        evidence = result.evidence
        analysis = evidence.analysis
        ranking = evidence.ranking
        rendering = evidence.rendering
        path_ident_matched_files = _unique_path_ident_hit_files(
            analysis.path_ident_hit_files
        )
        omitted_files = tuple(omitted.path for omitted in evidence.omitted_files)
        payload: dict[str, object] = {
            "branch": branch,
            "stage": stage,
            "mode": result.mode,
            "index_snapshot_id": evidence.index_snapshot_id,
            "cache_status": evidence.cache_status.read_status,
            "focus_fnames": list(result.focus_fnames),
            "focus_personalization_files": list(ranking.focus_personalization_files),
            "path_personalization_files": list(ranking.path_personalization_files),
            "personalization_files": list(ranking.personalization_files),
            "symbol_hits": list(analysis.effective_symbol_hits),
            "path_ident_hits": list(analysis.path_ident_hits),
            "path_ident_matched_file_count": len(path_ident_matched_files),
            "top_ranked_files": list(ranking.top_ranked_files),
            "rendered_files": list(result.rendered_files),
            "rendered_symbols": list(result.rendered_symbols),
            "omitted_files": list(omitted_files),
            "map_budget_tokens": rendering.target_tokens,
            "map_budget_chars": rendering.target_chars,
            "used_chars": rendering.used_chars,
            "estimated_tokens": rendering.estimated_tokens,
            "budget_reduction_applied": rendering.budget_reduction_applied,
            "focus_truncated": rendering.focus_truncated,
            "selector_model_calls": selector_model_calls,
        }
        if fallback_reason:
            payload["fallback_reason"] = fallback_reason
        if repo_map_artifact_path:
            payload["repo_map_artifact_path"] = repo_map_artifact_path
        if evidence_artifact_path:
            payload["evidence_artifact_path"] = evidence_artifact_path

        lines = [
            f"- branch: {branch}",
            f"- mode: {result.mode}",
            f"- focus: {_format_values(result.focus_fnames)}",
            "- focus personalization: "
            f"{_format_values(ranking.focus_personalization_files)}",
            "- path personalization: "
            f"{_format_values(ranking.path_personalization_files)}",
            f"- symbol hits: {_format_values(analysis.effective_symbol_hits)}",
            "- path ident hits: "
            f"{_format_values(analysis.path_ident_hits)} "
            f"({len(path_ident_matched_files)} files)",
            f"- top ranked: {_format_values(ranking.top_ranked_files)}",
            f"- rendered: {_format_values(result.rendered_files)}",
            f"- omitted: {_format_values(omitted_files)}",
            "- budget: "
            f"{rendering.target_tokens} tokens, "
            f"{rendering.used_chars} chars used, "
            f"estimated {rendering.estimated_tokens} tokens",
        ]
        if fallback_reason:
            lines.append(f"- fallback: {fallback_reason}")
        if evidence_artifact_path:
            lines.append(f"- evidence: {evidence_artifact_path}")
        return MapEngineConsoleReport(
            title="MapEngine retrieval",
            lines=tuple(lines),
            payload=payload,
        )

    def render_failure(
        self,
        *,
        error_type: str,
        fallback: str,
    ) -> MapEngineConsoleReport:
        return MapEngineConsoleReport(
            title="MapEngine retrieval failed",
            lines=(
                f"- error_type: {error_type}",
                f"- fallback: {fallback}",
            ),
            payload={
                "error_type": error_type,
                "fallback": fallback,
            },
        )


def _unique_path_ident_hit_files(
    hit_files: Mapping[str, Iterable[str]],
) -> tuple[str, ...]:
    return tuple(sorted({path for paths in hit_files.values() for path in paths}))


def _format_values(values: Iterable[str]) -> str:
    items = tuple(values)
    if not items:
        return "none"
    return ", ".join(items)
