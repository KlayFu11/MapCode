"""Structured trace event helpers."""

from .workspace import now

RETRIEVAL_EVENTS = (
    "map_index_status",
    "map_prompt_analyzed",
    "map_context_ranked",
    "map_context_selected",
    "map_selector_requested",
    "map_focus_confirmed",
    "map_generated",
    "map_context_failed",
)

PHASE_BY_EVENT = {
    "run_started": "runtime",
    "prompt_built": "prompt",
    "model_requested": "model",
    "model_parsed": "parse",
    "tool_executed": "tool",
    "checkpoint_created": "checkpoint",
    "compaction_started": "compact",
    "compaction_finished": "compact",
    "runtime_identity_mismatch": "runtime",
    "run_finished": "runtime",
    **{event: "retrieval" for event in RETRIEVAL_EVENTS},
}


def build_runtime_event(runtime, task_state, event, payload):
    payload = dict(payload or {})
    if event == "prompt_built":
        _add_prompt_built_summaries(payload)
    payload["event"] = str(event)
    payload["created_at"] = now()
    payload.setdefault("trace_id", task_state.run_id)
    payload.setdefault("turn_id", task_state.task_id)
    payload.setdefault("phase", PHASE_BY_EVENT.get(str(event), "runtime"))
    payload.setdefault("status", _status_for(event, payload))
    payload.setdefault("duration_ms", int(payload.get("duration_ms", 0) or 0))
    payload.setdefault("input_chars", int(payload.get("input_chars", 0) or 0))
    payload.setdefault("output_chars", int(payload.get("output_chars", 0) or 0))
    payload.setdefault("estimated_input_tokens", int(payload.get("estimated_input_tokens", 0) or 0))
    payload.setdefault("estimated_output_tokens", int(payload.get("estimated_output_tokens", 0) or 0))
    payload.setdefault("artifact_paths", list(payload.get("affected_paths", []) or []))
    payload.setdefault("error_type", _error_type(payload))
    payload.setdefault("parent_span_id", runtime._last_trace_span_id.get(task_state.run_id, ""))
    runtime._trace_seq += 1
    payload.setdefault("span_id", f"span_{runtime._trace_seq:06d}")
    runtime._last_trace_span_id[task_state.run_id] = payload["span_id"]
    return payload


def _add_prompt_built_summaries(payload):
    metadata = payload.get("prompt_metadata")
    if not isinstance(metadata, dict):
        return
    map_context = metadata.get("map_context")
    if isinstance(map_context, dict):
        payload["repo_map_render"] = {
            key: map_context.get(key)
            for key in ("section_rendered", "contract_rendered", "fallback_notice_rendered", "map_body_raw_chars", "map_body_rendered_chars", "section_rendered_chars", "section_rendered_hash", "base_prompt_reduction_applied", "omission_reason")
        }
    payload["request_budget"] = {
        key: metadata.get(key)
        for key in ("model_input_budget_tokens", "prompt_safety_margin_tokens", "active_repo_map_reservation_tokens", "base_prompt_budget_tokens", "estimated_request_tokens", "request_over_budget", "model_request_budget_source", "base_prompt_over_budget_with_repo_map_reservation")
    }


def _status_for(event, payload):
    if "status" in payload:
        return str(payload.get("status") or "")
    if event == "tool_executed":
        return str(payload.get("tool_status") or "ok")
    if event == "run_finished":
        return str(payload.get("status") or "completed")
    if event == "map_context_failed":
        return "error"
    if str(payload.get("tool_error_code", "")):
        return "error"
    return "ok"


def _error_type(payload):
    return str(payload.get("tool_error_code") or payload.get("security_event_type") or payload.get("error_type") or "")
