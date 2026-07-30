from dataclasses import FrozenInstanceError
from hashlib import sha256
from types import SimpleNamespace
from typing import get_args

import pytest

from pico.core.map_context_prompt import (
    EMPTY_REPO_MAP_SECTION_HASH,
    PROMPT_BUDGET_METADATA_KEYS,
    PromptBuildResult,
    PromptInjectionEvidence,
    PromptPurpose,
    RepoMapSectionRender,
    hash_repo_map_section_text,
    render_repo_map_navigation_text,
)


def _section_hash(text: str) -> str:
    return "sha256:" + sha256(text.encode("utf-8")).hexdigest()


def _metadata(**overrides) -> dict:
    metadata = {
        "model_input_budget_tokens": 32_768,
        "prompt_safety_margin_tokens": 1_024,
        "active_repo_map_reservation_tokens": 120,
        "base_prompt_budget_tokens": 31_624,
        "estimated_request_tokens": 900,
        "request_over_budget": False,
        "model_request_budget_source": "fallback",
    }
    metadata.update(overrides)
    return metadata


def _rendered_section() -> RepoMapSectionRender:
    section_text = "[Repo Map]\npico/core/runtime.py:\n  class Pico"
    return RepoMapSectionRender(
        section_text=section_text,
        section_rendered=True,
        contract_rendered=True,
        fallback_notice_rendered=False,
        map_body_raw_chars=28,
        map_body_rendered_chars=28,
        section_rendered_chars=len(section_text),
        section_rendered_hash=_section_hash(section_text),
        base_prompt_reduction_applied=False,
        omission_reason=None,
    )


def test_hash_repo_map_section_text_uses_stable_sha256_prefix():
    assert hash_repo_map_section_text("abc") == _section_hash("abc")
    assert EMPTY_REPO_MAP_SECTION_HASH == _section_hash("")


def test_repo_map_section_render_records_build_local_section_facts():
    render = _rendered_section()

    assert render.section_rendered is True
    assert render.contract_rendered is True
    assert render.map_body_rendered_chars == render.map_body_raw_chars
    assert render.section_rendered_hash == hash_repo_map_section_text(render.section_text)
    assert render.omission_reason is None

    with pytest.raises(FrozenInstanceError):
        render.section_text = ""


def test_repo_map_section_render_validates_omitted_section_invariants():
    render = RepoMapSectionRender.omitted(
        "base_prompt_cannot_fit_with_repo_map_reservation",
        map_body_raw_chars=512,
        base_prompt_reduction_applied=True,
    )

    assert render.section_text == ""
    assert render.section_rendered is False
    assert render.contract_rendered is False
    assert render.fallback_notice_rendered is False
    assert render.map_body_raw_chars == 512
    assert render.map_body_rendered_chars == 0
    assert render.section_rendered_chars == 0
    assert render.section_rendered_hash == EMPTY_REPO_MAP_SECTION_HASH
    assert render.omission_reason == "base_prompt_cannot_fit_with_repo_map_reservation"


def test_repo_map_section_render_rejects_invalid_empty_section_state():
    with pytest.raises(ValueError, match="omission_reason"):
        RepoMapSectionRender(
            section_text="",
            section_rendered=False,
            contract_rendered=False,
            fallback_notice_rendered=False,
            map_body_raw_chars=0,
            map_body_rendered_chars=0,
            section_rendered_chars=0,
            section_rendered_hash=EMPTY_REPO_MAP_SECTION_HASH,
            base_prompt_reduction_applied=False,
            omission_reason=None,
        )


def test_prompt_injection_evidence_copies_from_section_render_without_text():
    render = _rendered_section()
    evidence = PromptInjectionEvidence.from_section_render(render)

    assert evidence.section_rendered == render.section_rendered
    assert evidence.contract_rendered == render.contract_rendered
    assert evidence.fallback_notice_rendered == render.fallback_notice_rendered
    assert evidence.map_body_raw_chars == render.map_body_raw_chars
    assert evidence.map_body_rendered_chars == render.map_body_rendered_chars
    assert evidence.section_rendered_hash == render.section_rendered_hash
    assert evidence.omission_reason == render.omission_reason
    assert not hasattr(evidence, "section_text")


def test_prompt_purpose_literal_matches_spec_range():
    assert get_args(PromptPurpose) == (
        "main_model",
        "prompt_preview",
        "evaluation",
        "step_limit_summary",
    )


def test_prompt_build_result_requires_budget_metadata_and_build_local_render():
    metadata = _metadata()
    render = _rendered_section()

    result = PromptBuildResult(
        prompt="full prompt",
        metadata=metadata,
        repo_map_render=render,
    )
    metadata["request_over_budget"] = True

    assert tuple(PROMPT_BUDGET_METADATA_KEYS) == tuple(_metadata())
    assert result.metadata["request_over_budget"] is False
    assert result.repo_map_render is render

    with pytest.raises(FrozenInstanceError):
        result.prompt = "mutated"


def test_prompt_build_result_rejects_missing_budget_metadata():
    metadata = _metadata()
    metadata.pop("base_prompt_budget_tokens")

    with pytest.raises(ValueError, match="base_prompt_budget_tokens"):
        PromptBuildResult(
            prompt="full prompt",
            metadata=metadata,
            repo_map_render=None,
        )


def _map_context(
    *,
    branch: str,
    stage: str,
    focus_fnames: tuple[str, ...],
    repo_map_text: str,
    fallback_mode: str | None = None,
):
    return SimpleNamespace(
        branch=branch,
        stage=stage,
        active_result=SimpleNamespace(
            focus_fnames=focus_fnames,
            repo_map_text=repo_map_text,
            focused_repo_map_string="must not be used",
            focus_fnames_list=("must-not-be-used.py",),
        ),
        selection_decision=(
            None
            if fallback_mode is None
            else SimpleNamespace(fallback_mode=fallback_mode)
        ),
    )


def test_render_repo_map_navigation_text_uses_one_template_for_focused_contexts():
    branch_a = _map_context(
        branch="specific",
        stage="execution",
        focus_fnames=("pico/core/runtime.py", "pico/core/engine.py"),
        repo_map_text="branch-a body",
    )
    branch_b = _map_context(
        branch="fuzzy",
        stage="execution",
        focus_fnames=("pico/core/context_manager.py",),
        repo_map_text="branch-b body",
    )

    for result, branch, focus, body in (
        (branch_a, "specific", "pico/core/runtime.py, pico/core/engine.py", "branch-a body"),
        (branch_b, "fuzzy", "pico/core/context_manager.py", "branch-b body"),
    ):
        text = render_repo_map_navigation_text(result)

        assert text == (
            "[Repo Map - Navigation Context Only]\n"
            "The following repo map shows selected code-structure signatures only, not "
            "complete or authoritative file contents.\n"
            "Use it only to decide which files and symbols to inspect.\n"
            "Do not treat repo map snippets as authoritative full file content.\n"
            "Before relying on implementation details or editing any existing file, use "
            "read_file to inspect the complete current source.\n"
            "Repo map content does not satisfy Pico's prior-read or freshness requirement.\n"
            f"\nBranch: {branch}\n"
            "Mode: focused\n"
            f"Focus files (read these first): {focus}\n"
            f"\n{body}"
        )
        assert "must not be used" not in text
        assert "must-not-be-used.py" not in text


def test_render_repo_map_navigation_text_renders_exact_broad_fallback_notice():
    result = _map_context(
        branch="fuzzy",
        stage="fallback",
        focus_fnames=(),
        repo_map_text="broad body",
        fallback_mode="broad_map",
    )

    assert render_repo_map_navigation_text(result).endswith(
        "Focus files (read these first): none\n"
        "No specific focus files were confirmed. Broad repository context is provided "
        "for navigation.\n\n"
        "broad body"
    )


def test_render_repo_map_navigation_text_returns_empty_text_without_map_context():
    assert render_repo_map_navigation_text(None) == ""
