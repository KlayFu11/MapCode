"""Pure projections of MapEngine retrieval evidence for fixed evaluations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RenderingMetrics:
    """Structured rendering facts for one focused or broad map result."""

    target_tokens: int | None
    target_chars: int | None
    used_chars: int | None
    estimated_tokens: int | None
    focus_truncated: bool | None


@dataclass(frozen=True)
class SelectorRequestMetrics:
    """Scalar evidence for one complete selector model request."""

    input_chars: int | None
    estimated_tokens: int | None
    candidate_path_count: int | None
    rendered_path_count: int | None
    visible_path_count: int | None
    definition_count: int | None
    rendered_definition_count: int | None
    catalog_truncated: bool | None


@dataclass(frozen=True)
class FallbackBudgetMetrics:
    """Fallback and request-budget facts projected from completed artifacts."""

    focus_truncated: bool | None
    selector_model_calls: int | None
    selector_request_over_budget: bool | None
    broad_fallback: bool | None
    base_prompt_reduction_applied: bool | None
    repo_map_section_rendered: bool | None
    repo_map_omission_reason: str | None
    request_over_budget: bool | None


@dataclass(frozen=True)
class RankContributorMetrics:
    """One rendered-file contributor projected without changing rank evidence."""

    path: str
    source_path: str | None
    identifier: str | None
    weight_multiplier: float | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalCaseMetrics:
    """Evaluation facts interpreted from one case's evidence and trace."""

    effective_file_hit: bool | None
    effective_symbol_hit: bool | None
    effective_path_ident_hit: bool | None
    path_ident_branch_a: bool | None
    path_ident_raw_ident: str | None
    path_ident_full_hit_files: tuple[str, ...]
    focus_files: tuple[str, ...]
    focus_personalization_files: tuple[str, ...]
    path_personalization_files: tuple[str, ...]
    personalization_files: tuple[str, ...]
    path_ground_truth_personalization_hit: bool | None
    path_ground_truth_rendered_hit: bool | None
    focus_path_isolated: bool | None
    rendered_files: tuple[str, ...]
    rendered_file_hit: bool | None
    first_read_path: str | None
    first_read_hit: bool | None
    focused_rendering: RenderingMetrics | None
    broad_rendering: RenderingMetrics | None
    selector_request: SelectorRequestMetrics | None
    fallback_budget: FallbackBudgetMetrics | None
    top_contributors: tuple[RankContributorMetrics, ...]


def collect_retrieval_case_metrics(
    case: Mapping[str, object],
    map_evidence: Mapping[str, object] | None,
    trace_events: Sequence[Mapping[str, object]],
    report: Mapping[str, object] | None = None,
) -> RetrievalCaseMetrics:
    """Interpret structured artifacts without parsing map text or recomputing rank.

    ``None`` marks a fact unavailable from an artifact or not applicable to this
    case. Empty tuples are reserved for collection facts that are absent or empty.
    """

    evidence = _mapping(map_evidence)
    analysis = _mapping(evidence.get("analysis")) if evidence else None
    active_result = _active_result(evidence)
    active_evidence = _result_evidence(active_result)

    mentioned_files, has_mentioned_files = _strings_at(analysis, "mentioned_files")
    symbol_hits, has_symbol_hits = _strings_at(analysis, "effective_symbol_hits")
    path_hits, has_path_hits = _strings_at(analysis, "path_ident_hits")
    ground_truth_files = _strings(case.get("ground_truth_files"))
    ground_truth_symbols = _strings(case.get("ground_truth_symbols"))
    expected_path_ident = _string(case.get("original_path_ident"))

    path_raw_ident = _matching_path_ident(path_hits, expected_path_ident)
    path_hit_files = _path_hit_files(analysis, path_raw_ident)
    has_path_hit_files = _has_path_hit_files(analysis, path_raw_ident)

    focus_files, has_focus_files = _strings_at(active_result, "focus_fnames")
    rendered_files, has_rendered_files = _rendered_paths(active_result, active_evidence)
    ranking = _mapping(active_evidence.get("ranking")) if active_evidence else None
    focus_personalization_files, has_focus_personalization = _strings_at(
        ranking, "focus_personalization_files"
    )
    path_personalization_files, has_path_personalization = _strings_at(
        ranking, "path_personalization_files"
    )
    personalization_files, has_personalization = _strings_at(
        ranking, "personalization_files"
    )

    file_applicable = bool(ground_truth_files) and not (
        ground_truth_symbols or expected_path_ident
    )
    symbol_applicable = bool(ground_truth_symbols)
    path_applicable = expected_path_ident is not None

    effective_file_hit = (
        _any_match(mentioned_files, ground_truth_files)
        if file_applicable and has_mentioned_files
        else None
    )
    effective_symbol_hit = (
        _any_match(symbol_hits, ground_truth_symbols)
        if symbol_applicable and has_symbol_hits
        else None
    )
    effective_path_ident_hit = (
        path_raw_ident is not None if path_applicable and has_path_hits else None
    )
    path_ident_branch_a = _path_branch_a(
        analysis,
        path_raw_ident,
        path_applicable,
    )

    path_ground_truth_personalization_hit = (
        _any_match(path_personalization_files, ground_truth_files)
        if path_applicable and has_path_personalization and ground_truth_files
        else None
    )
    path_ground_truth_rendered_hit = (
        _any_match(rendered_files, ground_truth_files)
        if path_applicable and has_rendered_files and ground_truth_files
        else None
    )
    focus_path_isolated = _focus_path_isolated(
        analysis,
        path_raw_ident,
        focus_files,
        focus_personalization_files,
        path_applicable,
        has_focus_files,
        has_focus_personalization,
    )
    rendered_file_hit = (
        _any_match(rendered_files, ground_truth_files)
        if ground_truth_files and has_rendered_files
        else None
    )

    first_read_path = _first_read_path(trace_events)
    first_read_hit = (
        first_read_path in ground_truth_files
        if first_read_path is not None and ground_truth_files
        else None
    )

    focused_rendering = _rendering_for(active_result, active_evidence, "focused")
    broad_result = _mapping(evidence.get("broad_result")) if evidence else None
    broad_rendering = _rendering_for(broad_result, _result_evidence(broad_result), "broad")
    if broad_rendering is None:
        broad_rendering = _rendering_for(active_result, active_evidence, "broad")
    selector_request = _selector_request_metrics(trace_events)
    fallback_budget = _fallback_budget_metrics(evidence, active_evidence, report)

    return RetrievalCaseMetrics(
        effective_file_hit=effective_file_hit,
        effective_symbol_hit=effective_symbol_hit,
        effective_path_ident_hit=effective_path_ident_hit,
        path_ident_branch_a=path_ident_branch_a,
        path_ident_raw_ident=path_raw_ident,
        path_ident_full_hit_files=path_hit_files if has_path_hit_files else (),
        focus_files=focus_files,
        focus_personalization_files=focus_personalization_files,
        path_personalization_files=path_personalization_files,
        personalization_files=personalization_files,
        path_ground_truth_personalization_hit=path_ground_truth_personalization_hit,
        path_ground_truth_rendered_hit=path_ground_truth_rendered_hit,
        focus_path_isolated=focus_path_isolated,
        rendered_files=rendered_files,
        rendered_file_hit=rendered_file_hit,
        first_read_path=first_read_path,
        first_read_hit=first_read_hit,
        focused_rendering=focused_rendering,
        broad_rendering=broad_rendering,
        selector_request=selector_request,
        fallback_budget=fallback_budget,
        top_contributors=_contributors(active_evidence),
    )


def _active_result(evidence: Mapping[str, object] | None) -> Mapping[str, object] | None:
    if evidence is None:
        return None
    return _mapping(evidence.get("active_result")) or _mapping(evidence.get("result"))


def _result_evidence(
    result: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    return _mapping(result.get("evidence")) if result else None


def _path_branch_a(
    analysis: Mapping[str, object] | None,
    path_raw_ident: str | None,
    path_applicable: bool,
) -> bool | None:
    if not path_applicable or analysis is None:
        return None
    branch = _string(analysis.get("branch"))
    mentioned_files, has_mentioned_files = _strings_at(analysis, "mentioned_files")
    symbol_hits, has_symbol_hits = _strings_at(analysis, "effective_symbol_hits")
    if branch is None or not has_mentioned_files or not has_symbol_hits:
        return None
    return branch == "specific" and path_raw_ident is not None and not (
        mentioned_files or symbol_hits
    )


def _focus_path_isolated(
    analysis: Mapping[str, object] | None,
    path_raw_ident: str | None,
    focus_files: tuple[str, ...],
    focus_personalization_files: tuple[str, ...],
    path_applicable: bool,
    has_focus_files: bool,
    has_focus_personalization: bool,
) -> bool | None:
    if not path_applicable or analysis is None:
        return None
    if path_raw_ident is None:
        return False
    mentioned_files, has_mentioned_files = _strings_at(analysis, "mentioned_files")
    symbol_hits, has_symbol_hits = _strings_at(analysis, "effective_symbol_hits")
    if not all((has_mentioned_files, has_symbol_hits, has_focus_files, has_focus_personalization)):
        return None
    if mentioned_files or symbol_hits:
        return None
    return not focus_files and not focus_personalization_files


def _rendering_for(
    result: Mapping[str, object] | None,
    result_evidence: Mapping[str, object] | None,
    mode: str,
) -> RenderingMetrics | None:
    if _string(result.get("mode")) != mode if result else True:
        return None
    rendering = _mapping(result_evidence.get("rendering")) if result_evidence else None
    if rendering is None:
        return None
    return RenderingMetrics(
        target_tokens=_integer(rendering.get("target_tokens")),
        target_chars=_integer(rendering.get("target_chars")),
        used_chars=_integer(rendering.get("used_chars")),
        estimated_tokens=_integer(rendering.get("estimated_tokens")),
        focus_truncated=_boolean(rendering.get("focus_truncated")),
    )


def _contributors(
    result_evidence: Mapping[str, object] | None,
) -> tuple[RankContributorMetrics, ...]:
    if result_evidence is None:
        return ()
    rendered_files = result_evidence.get("rendered_files")
    if not isinstance(rendered_files, Sequence) or isinstance(rendered_files, (str, bytes)):
        return ()
    contributors = []
    for rendered_file in rendered_files:
        file_evidence = _mapping(rendered_file)
        if file_evidence is None:
            continue
        path = _string(file_evidence.get("path"))
        raw_contributors = file_evidence.get("top_rank_contributors")
        if path is None or not isinstance(raw_contributors, Sequence) or isinstance(raw_contributors, (str, bytes)):
            continue
        for raw_contributor in raw_contributors:
            contributor = _mapping(raw_contributor)
            if contributor is None:
                continue
            contributors.append(
                RankContributorMetrics(
                    path=path,
                    source_path=_string(contributor.get("source_path")),
                    identifier=_string(contributor.get("identifier")),
                    weight_multiplier=_number(contributor.get("weight_multiplier")),
                    reason_codes=_strings(contributor.get("weight_reason_codes")),
                )
            )
    return tuple(contributors)


def _rendered_paths(
    result: Mapping[str, object] | None,
    result_evidence: Mapping[str, object] | None,
) -> tuple[tuple[str, ...], bool]:
    paths, present = _strings_at(result, "rendered_files")
    if present:
        return paths, True
    if result_evidence is None or "rendered_files" not in result_evidence:
        return (), False
    values = result_evidence["rendered_files"]
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return (), True
    return tuple(
        path
        for item in values
        if (item_mapping := _mapping(item)) is not None
        and (path := _string(item_mapping.get("path"))) is not None
    ), True


def _path_hit_files(
    analysis: Mapping[str, object] | None,
    raw_ident: str | None,
) -> tuple[str, ...]:
    if analysis is None or raw_ident is None:
        return ()
    raw_mapping = _mapping(analysis.get("path_ident_hit_files"))
    return _strings(raw_mapping.get(raw_ident)) if raw_mapping else ()


def _has_path_hit_files(
    analysis: Mapping[str, object] | None,
    raw_ident: str | None,
) -> bool:
    if analysis is None or raw_ident is None:
        return False
    raw_mapping = _mapping(analysis.get("path_ident_hit_files"))
    return raw_mapping is not None and raw_ident in raw_mapping


def _matching_path_ident(
    path_hits: tuple[str, ...],
    expected_path_ident: str | None,
) -> str | None:
    if expected_path_ident is None:
        return None
    return next((ident for ident in path_hits if ident == expected_path_ident), None)


def _first_read_path(trace_events: Sequence[Mapping[str, object]]) -> str | None:
    for event in trace_events:
        if _string(event.get("event")) != "tool_executed" or _string(event.get("name")) != "read_file":
            continue
        args = _mapping(event.get("args"))
        if args is not None:
            return _string(args.get("path"))
        return None
    return None


def _selector_request_metrics(
    trace_events: Sequence[Mapping[str, object]],
) -> SelectorRequestMetrics | None:
    for event in trace_events:
        if _string(event.get("event")) != "map_selector_requested":
            continue
        input_chars = _integer(event.get("input_chars"))
        return SelectorRequestMetrics(
            input_chars=input_chars,
            estimated_tokens=(input_chars + 3) // 4 if input_chars is not None else None,
            candidate_path_count=_integer(event.get("candidate_path_count")),
            rendered_path_count=_integer(event.get("rendered_path_count")),
            visible_path_count=_integer(event.get("visible_path_count")),
            definition_count=_integer(event.get("definition_count")),
            rendered_definition_count=_integer(event.get("rendered_definition_count")),
            catalog_truncated=_boolean(event.get("catalog_truncated")),
        )
    return None


def _fallback_budget_metrics(
    evidence: Mapping[str, object] | None,
    active_evidence: Mapping[str, object] | None,
    report: Mapping[str, object] | None,
) -> FallbackBudgetMetrics | None:
    report = _mapping(report)
    rendering = _mapping(active_evidence.get("rendering")) if active_evidence else None
    decision = _mapping(evidence.get("selection_decision")) if evidence else None
    prompt_injection = _mapping(evidence.get("prompt_injection")) if evidence else None
    model_calls = _mapping(report.get("model_calls")) if report else None
    request_budget = _mapping(report.get("request_budget")) if report else None

    if not any(
        (
            rendering is not None,
            decision is not None,
            evidence is not None and "branch" in evidence and "stage" in evidence,
            prompt_injection is not None,
            model_calls is not None,
            request_budget is not None,
        )
    ):
        return None

    fallback_reason = _string(decision.get("fallback_reason")) if decision else None
    branch = _string(evidence.get("branch")) if evidence else None
    stage = _string(evidence.get("stage")) if evidence else None
    return FallbackBudgetMetrics(
        focus_truncated=_boolean(rendering.get("focus_truncated")) if rendering else None,
        selector_model_calls=(
            _integer(model_calls.get("selector_model_calls")) if model_calls else None
        ),
        selector_request_over_budget=(
            fallback_reason == "selector_request_over_budget"
            if decision is not None and fallback_reason is not None
            else None
        ),
        broad_fallback=(branch == "fuzzy" and stage == "fallback")
        if branch is not None and stage is not None
        else None,
        base_prompt_reduction_applied=(
            _boolean(prompt_injection.get("base_prompt_reduction_applied"))
            if prompt_injection
            else None
        ),
        repo_map_section_rendered=(
            _boolean(prompt_injection.get("section_rendered"))
            if prompt_injection
            else None
        ),
        repo_map_omission_reason=(
            _string(prompt_injection.get("omission_reason")) if prompt_injection else None
        ),
        request_over_budget=(
            _boolean(request_budget.get("request_over_budget"))
            if request_budget
            else None
        ),
    )


def _strings_at(
    mapping: Mapping[str, object] | None,
    key: str,
) -> tuple[tuple[str, ...], bool]:
    if mapping is None or key not in mapping:
        return (), False
    return _strings(mapping[key]), True


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _boolean(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _any_match(actual: tuple[str, ...], expected: tuple[str, ...]) -> bool:
    return bool(set(actual).intersection(expected))
