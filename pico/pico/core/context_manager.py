"""Prompt 组装与上下文预算控制。

这个模块负责决定：每一轮到底把多少 prefix、memory、相关笔记、历史
以及当前用户请求送进模型。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..features import memory as memorylib, skills as skillslib
from .context_usage import ContextUsageAnalyzer
from .map_context_prompt import (
    RepoMapSectionRender,
    PromptBuildResult,
    PromptPurpose,
    hash_repo_map_section_text,
    render_repo_map_navigation_text,
)
from .turn_history import TurnHistoryBuilder, tail_clip

DEFAULT_TOTAL_BUDGET = 60000
DEFAULT_SECTION_BUDGETS = {
    "prefix": 12000,
    "memory": 8000,
    "skills": 4000,
    "relevant_memory": 6000,
    "history": 30000,
}
DEFAULT_SECTION_FLOORS = {
    "prefix": 4000,
    "memory": 1200,
    "skills": 600,
    "relevant_memory": 1000,
    "history": 6000,
}
# 当 prompt 超预算时，会优先压缩这些 section。
DEFAULT_REDUCTION_ORDER = ("relevant_memory", "skills", "history", "memory", "prefix")
SECTION_ORDER = (
    "prefix",
    "memory",
    "skills",
    "relevant_memory",
    "history",
    "repo_map",
    "current_request",
)
CURRENT_REQUEST_SECTION = "current_request"
REPO_MAP_SECTION = "repo_map"
RELEVANT_MEMORY_LIMIT = 3


@dataclass
class SectionRender:
    raw: str
    budget: int
    rendered: str
    details: dict | None = None

    @property
    def raw_chars(self):
        return len(self.raw)

    @property
    def rendered_chars(self):
        return len(self.rendered)


class ContextManager:
    def __init__(
        self,
        agent,
        total_budget=DEFAULT_TOTAL_BUDGET,
        section_budgets=None,
        section_floors=None,
        reduction_order=None,
    ):
        self.agent = agent
        self.total_budget = int(total_budget)
        self.section_budgets = dict(DEFAULT_SECTION_BUDGETS)
        if section_budgets:
            self.section_budgets.update({str(key): int(value) for key, value in section_budgets.items()})
        self._section_floor_overrides = {str(key): int(value) for key, value in (section_floors or {}).items()}
        self.section_floors = self._compute_section_floors()
        self.reduction_order = tuple(reduction_order or DEFAULT_REDUCTION_ORDER)
        self.history_builder = TurnHistoryBuilder(agent)

    def build(self, user_message, *, purpose: PromptPurpose) -> PromptBuildResult:
        """按预算组装一轮完整 prompt。

        为什么存在：
        仅靠用户这一轮输入，模型并不知道当前仓库状态、会话里已经读过什么、
        哪些旧信息还值得继续参考。这个函数负责把“稳定基线 + 工作记忆 +
        相关笔记 + 历史 + 当前请求”拼成真正发给模型的 prompt。

        输入 / 输出：
        - 输入：`user_message`，也就是用户当前这一轮的新请求。
        - 输出：`PromptBuildResult`。
          `prompt` 是最终发送给模型的文本；
          `metadata` 记录了每个 section 的原始长度、裁剪后的长度、是否触发了
          预算收缩等信息，后续会进入 trace/report，便于解释这轮 prompt
          是怎么被拼出来的。

        在 agent 链路里的位置：
        它位于 `Pico.ask()` 的每轮模型调用之前，是“真正发请求给模型”
        的最后一道组装工序。`WorkspaceContext` 提供稳定前缀，`LayeredMemory`
        提供工作记忆，这个函数则把它们和当前请求合成一份可控大小的 prompt。
        """
        user_message = str(user_message)
        self.section_floors = self._compute_section_floors()
        memory_enabled = True
        relevant_memory_enabled = True
        context_reduction_enabled = True
        if hasattr(self.agent, "feature_enabled"):
            memory_enabled = self.agent.feature_enabled("memory")
            relevant_memory_enabled = self.agent.feature_enabled("relevant_memory")
            context_reduction_enabled = self.agent.feature_enabled("context_reduction")
        memory_text = "Memory:\n- disabled" if not memory_enabled else str(self.agent.memory_text())
        section_texts = {
            "prefix": str(getattr(self.agent, "prefix", "")),
            "memory": memory_text,
            "skills": skillslib.render_prompt_section(getattr(self.agent, "skills", {})),
            "history": "",
            CURRENT_REQUEST_SECTION: f"Current user request:\n{user_message}",
        }
        repo_map_render = self._render_repo_map_section(purpose)
        if repo_map_render is not None and repo_map_render.section_rendered:
            section_texts[REPO_MAP_SECTION] = repo_map_render.section_text
        section_order = self._section_order(section_texts)
        base_section_order = tuple(
            section for section in section_order if section != REPO_MAP_SECTION
        )
        base_prompt_budget = self._base_prompt_budget(repo_map_render)
        if hasattr(self.agent, "todo_ledger"):
            section_texts["memory"] += "\n\n" + self.agent.todo_ledger.render_prompt()
        checkpoint_text = ""
        if hasattr(self.agent, "render_checkpoint_text"):
            checkpoint_text = str(self.agent.render_checkpoint_text() or "").strip()
        if checkpoint_text:
            section_texts["memory"] += "\n\n" + checkpoint_text
        if memory_enabled and hasattr(self.agent, "memory_dir"):
            section_texts["memory"] += "\n\n" + memorylib.build_memory_system_section(self.agent.memory_dir)
        selected_notes = []
        if memory_enabled and relevant_memory_enabled and hasattr(self.agent, "memory") and hasattr(self.agent.memory, "retrieval_candidates"):
            selected_notes = self.agent.memory.retrieval_candidates(user_message, limit=RELEVANT_MEMORY_LIMIT)

        if not context_reduction_enabled:
            rendered = self._render_sections_without_reduction(
                section_texts,
                section_order,
                selected_notes=selected_notes,
            )
            base_prompt = self._assemble_prompt(rendered, base_section_order)
            if self._repo_map_must_be_omitted(
                repo_map_render,
                base_prompt,
                base_prompt_budget,
            ):
                repo_map_render = self._omit_repo_map_section(repo_map_render)
                section_texts.pop(REPO_MAP_SECTION, None)
                section_order = self._section_order(section_texts)
                base_prompt_budget = self._base_prompt_budget(repo_map_render)
                rendered = self._render_sections_without_reduction(
                    section_texts,
                    section_order,
                    selected_notes=selected_notes,
                )
                base_prompt = self._assemble_prompt(rendered, base_section_order)
            prompt = self._assemble_prompt(rendered, section_order)
            metadata = self._metadata(
                prompt=prompt,
                base_prompt=base_prompt,
                base_prompt_budget=base_prompt_budget,
                rendered=rendered,
                budgets={
                    section: render.budget
                    for section, render in rendered.items()
                    if section != CURRENT_REQUEST_SECTION
                },
                reduction_log=[],
                selected_notes=selected_notes,
                user_message=user_message,
                section_texts=section_texts,
                section_order=section_order,
                repo_map_render=repo_map_render,
            )
            return PromptBuildResult(
                prompt=prompt,
                metadata=metadata,
                repo_map_render=repo_map_render,
            )

        budgets = dict(self.section_budgets)
        rendered = self._render_sections(
            section_texts,
            budgets,
            section_order,
            selected_notes=selected_notes,
        )
        base_prompt = self._assemble_prompt(rendered, base_section_order)
        reduction_log = []

        # 如果 prompt 超预算，就按固定顺序不断压缩。
        # 这里的顺序体现了平台偏好：
        # 先牺牲 relevant_memory，再牺牲 history，然后才动 memory 和 prefix。
        # 最新用户请求永远不裁剪，因为那是本轮最重要的输入。
        while len(base_prompt) > base_prompt_budget["effective_chars"]:
            overflow = len(base_prompt) - base_prompt_budget["effective_chars"]
            reduced = False
            for section in self.reduction_order:
                floor = int(self.section_floors.get(section, 0))
                current_budget = int(budgets.get(section, 0))
                if current_budget <= floor:
                    continue
                new_budget = max(floor, current_budget - overflow)
                if new_budget >= current_budget:
                    continue
                reduction_log.append(
                    {
                        "section": section,
                        "before_chars": current_budget,
                        "after_chars": new_budget,
                        "overflow_chars": overflow,
                    }
                )
                budgets[section] = new_budget
                rendered = self._render_sections(
                    section_texts,
                    budgets,
                    section_order,
                    selected_notes=selected_notes,
                )
                base_prompt = self._assemble_prompt(rendered, base_section_order)
                reduced = True
                break
            if not reduced:
                break

        repo_map_render = self._with_base_prompt_reduction(
            repo_map_render,
            base_prompt_budget,
            reduction_log,
        )
        if self._repo_map_must_be_omitted(
            repo_map_render,
            base_prompt,
            base_prompt_budget,
        ):
            repo_map_render = self._omit_repo_map_section(repo_map_render)
            section_texts.pop(REPO_MAP_SECTION, None)
            section_order = self._section_order(section_texts)
            base_prompt_budget = self._base_prompt_budget(repo_map_render)
            rendered = self._render_sections(
                section_texts,
                budgets,
                section_order,
                selected_notes=selected_notes,
            )
            base_prompt = self._assemble_prompt(rendered, base_section_order)
        prompt = self._assemble_prompt(rendered, section_order)

        metadata = self._metadata(
            prompt=prompt,
            base_prompt=base_prompt,
            base_prompt_budget=base_prompt_budget,
            rendered=rendered,
            budgets=budgets,
            reduction_log=reduction_log,
            selected_notes=selected_notes,
            user_message=user_message,
            section_texts=section_texts,
            section_order=section_order,
            repo_map_render=repo_map_render,
        )
        return PromptBuildResult(
            prompt=prompt,
            metadata=metadata,
            repo_map_render=repo_map_render,
        )

    def _base_prompt_budget(self, repo_map_render):
        model_request_budget = self.agent.model_request_budget
        reservation_tokens = (
            0
            if repo_map_render is None
            else model_request_budget.estimate_request_tokens(
                repo_map_render.section_text
            )
        )
        base_prompt_budget_tokens = max(
            0,
            model_request_budget.model_input_budget_tokens
            - reservation_tokens
            - model_request_budget.prompt_safety_margin_tokens,
        )
        return {
            "reservation_tokens": reservation_tokens,
            "base_prompt_budget_tokens": base_prompt_budget_tokens,
            "effective_chars": min(
                self.total_budget,
                base_prompt_budget_tokens * 4,
            ),
        }

    def _with_base_prompt_reduction(
        self,
        repo_map_render,
        base_prompt_budget,
        reduction_log,
    ):
        if repo_map_render is None:
            return None
        reservation_reduced_base_budget = (
            base_prompt_budget["effective_chars"] < self.total_budget
        )
        return replace(
            repo_map_render,
            base_prompt_reduction_applied=(
                reservation_reduced_base_budget and bool(reduction_log)
            ),
        )

    def _repo_map_must_be_omitted(
        self,
        repo_map_render,
        base_prompt,
        base_prompt_budget,
    ):
        return (
            repo_map_render is not None
            and repo_map_render.section_rendered
            and len(base_prompt) > base_prompt_budget["effective_chars"]
        )

    def _omit_repo_map_section(self, repo_map_render):
        return RepoMapSectionRender.omitted(
            "base_prompt_cannot_fit_with_repo_map_reservation",
            map_body_raw_chars=repo_map_render.map_body_raw_chars,
            base_prompt_reduction_applied=repo_map_render.base_prompt_reduction_applied,
        )

    def _render_sections_without_reduction(
        self,
        section_texts,
        section_order,
        selected_notes=None,
    ):
        selected_notes = selected_notes or []
        relevant_lines = ["Relevant memory:"]
        if selected_notes:
            relevant_lines.extend(f"- {note['text']}" for note in selected_notes)
        else:
            relevant_lines.append("- none")
        relevant_raw = "\n".join(relevant_lines)
        history = list(getattr(self.agent, "session", {}).get("history", []))
        history_raw = self.history_builder.raw_text(history)
        rendered = {
            "prefix": SectionRender(raw=section_texts["prefix"], budget=len(section_texts["prefix"]), rendered=section_texts["prefix"], details={}),
            "memory": SectionRender(raw=section_texts["memory"], budget=len(section_texts["memory"]), rendered=section_texts["memory"], details={}),
            "skills": SectionRender(raw=section_texts["skills"], budget=len(section_texts["skills"]), rendered=section_texts["skills"], details={}),
            "relevant_memory": SectionRender(
                raw=relevant_raw,
                budget=len(relevant_raw),
                rendered=relevant_raw,
                details={
                    "selected_notes": [note["text"] for note in selected_notes],
                    "rendered_notes": [note["text"] for note in selected_notes],
                    "selected_count": len(selected_notes),
                    "rendered_count": len(selected_notes),
                    "note_budget": 0,
                },
            ),
            "history": SectionRender(raw=history_raw, budget=len(history_raw), rendered=history_raw, details={"rendered_entries": []}),
            CURRENT_REQUEST_SECTION: SectionRender(
                raw=section_texts[CURRENT_REQUEST_SECTION],
                budget=0,
                rendered=section_texts[CURRENT_REQUEST_SECTION],
                details={},
            ),
        }
        if REPO_MAP_SECTION in section_order:
            repo_map_text = section_texts[REPO_MAP_SECTION]
            rendered[REPO_MAP_SECTION] = SectionRender(
                raw=repo_map_text,
                budget=0,
                rendered=repo_map_text,
                details={},
            )
        return rendered

    def _compute_section_floors(self):
        floors = {
            section: max(20, int(budget) // 4)
            for section, budget in self.section_budgets.items()
        }
        floors.update(self._section_floor_overrides)
        return floors

    def _render_sections(self, section_texts, budgets, section_order, selected_notes=None):
        rendered = {}
        for section in section_order:
            budget = budgets.get(section)
            if section == CURRENT_REQUEST_SECTION:
                raw = section_texts[section]
                rendered[section] = SectionRender(raw=raw, budget=0, rendered=raw, details={})
            elif section == REPO_MAP_SECTION:
                raw = section_texts[section]
                rendered[section] = SectionRender(raw=raw, budget=0, rendered=raw, details={})
            elif section == "relevant_memory":
                rendered[section] = self._render_relevant_memory(selected_notes or [], int(budget or 0))
            elif section == "history":
                rendered[section] = self._render_history_section(int(budget or 0))
            else:
                raw = section_texts[section]
                rendered_text = tail_clip(raw, int(budget)) if budget is not None else raw
                rendered[section] = SectionRender(raw=raw, budget=int(budget) if budget is not None else 0, rendered=rendered_text, details={})
        return rendered

    def _render_relevant_memory(self, selected_notes, budget):
        header = "Relevant memory:"
        note_texts = [str(note.get("text", "")) for note in selected_notes if str(note.get("text", "")).strip()]
        raw_lines = [header] + [f"- {text}" for text in note_texts]
        raw = "\n".join(raw_lines) if note_texts else "\n".join([header, "- none"])
        if not note_texts:
            rendered = raw
            return SectionRender(
                raw=raw,
                budget=budget,
                rendered=rendered,
                details={
                    "selected_notes": [],
                    "rendered_notes": [],
                    "selected_count": 0,
                    "rendered_count": 0,
                    "note_budget": 0,
                },
            )

        per_note_budget = self._per_note_budget(budget, len(note_texts), header)
        rendered_notes = []
        while True:
            # 让每条 note 平分这一段的预算，避免一条超长笔记把其他笔记都挤掉。
            rendered_notes = [tail_clip(text, per_note_budget) for text in note_texts]
            rendered = "\n".join([header] + [f"- {text}" for text in rendered_notes])
            if len(rendered) <= budget or per_note_budget <= 1:
                break
            per_note_budget -= 1

        if len(rendered) > budget and budget > 0:
            rendered = tail_clip(raw, budget)
            rendered_notes = [rendered]

        return SectionRender(
            raw=raw,
            budget=budget,
            rendered=rendered,
            details={
                "selected_notes": note_texts,
                "rendered_notes": rendered_notes,
                "selected_count": len(note_texts),
                "rendered_count": len(rendered_notes),
                "note_budget": per_note_budget,
            },
        )

    def _per_note_budget(self, budget, note_count, header):
        if note_count <= 0:
            return 0
        overhead = len(header) + 3 * note_count
        usable = max(0, budget - overhead)
        return max(1, usable // note_count)

    def _render_history_section(self, budget):
        history = list(getattr(self.agent, "session", {}).get("history", []))
        raw = self.history_builder.raw_text(history)
        if not history:
            rendered = "Transcript:\n- empty"
            return SectionRender(
                raw=raw,
                budget=budget,
                rendered=rendered,
                details={
                    "rendered_entries": [],
                    "older_entries_count": 0,
                    "collapsed_duplicate_reads": 0,
                    "reused_file_summary_count": 0,
                    "summarized_tool_count": 0,
                    "rendered_turns": 0,
                },
            )

        rendered, history_details = self.history_builder.render_section(budget)

        return SectionRender(
            raw=raw,
            budget=budget,
            rendered=rendered,
            details=history_details,
        )

    def _section_order(self, section_texts):
        if REPO_MAP_SECTION in section_texts:
            return SECTION_ORDER
        return tuple(section for section in SECTION_ORDER if section != REPO_MAP_SECTION)

    def _render_repo_map_section(self, purpose):
        if purpose not in {"main_model", "prompt_preview"}:
            return None
        map_context = getattr(self.agent, "current_map_context", None)
        if map_context is None:
            return None

        try:
            map_body = str(map_context.active_result.repo_map_text)
            section_text = render_repo_map_navigation_text(map_context)
            is_broad_fallback = (
                map_context.stage == "fallback"
                and map_context.selection_decision is not None
                and map_context.selection_decision.fallback_mode == "broad_map"
            )
            return RepoMapSectionRender(
                section_text=section_text,
                section_rendered=True,
                contract_rendered=True,
                fallback_notice_rendered=is_broad_fallback,
                map_body_raw_chars=len(map_body),
                map_body_rendered_chars=len(map_body),
                section_rendered_chars=len(section_text),
                section_rendered_hash=hash_repo_map_section_text(section_text),
                base_prompt_reduction_applied=False,
                omission_reason=None,
            )
        except Exception:
            return RepoMapSectionRender.omitted(
                "repo_map_section_render_failed",
                map_body_raw_chars=self._repo_map_body_raw_chars(map_context),
                base_prompt_reduction_applied=False,
            )

    def _repo_map_body_raw_chars(self, map_context):
        try:
            return len(str(map_context.active_result.repo_map_text))
        except Exception:
            return 0

    def _assemble_prompt(self, rendered, section_order):
        # 顺序是刻意设计的：稳定规则放前面，最新请求放最后。
        return "\n\n".join(rendered[section].rendered for section in section_order).strip()

    def _metadata(
        self,
        prompt,
        base_prompt,
        base_prompt_budget,
        rendered,
        budgets,
        reduction_log,
        selected_notes,
        user_message,
        section_texts,
        section_order,
        repo_map_render,
    ):
        model_request_budget = self.agent.model_request_budget
        section_metadata = {}
        for section in section_order:
            if section == CURRENT_REQUEST_SECTION:
                continue
            section_metadata[section] = {
                "raw_chars": rendered[section].raw_chars,
                "budget_chars": int(budgets.get(section, 0)),
                "rendered_chars": rendered[section].rendered_chars,
            }
        section_metadata[CURRENT_REQUEST_SECTION] = {
            "raw_chars": len(section_texts[CURRENT_REQUEST_SECTION]),
            "budget_chars": None,
            "rendered_chars": len(rendered[CURRENT_REQUEST_SECTION].rendered),
        }
        metadata = {
            "model_input_budget_tokens": model_request_budget.model_input_budget_tokens,
            "prompt_safety_margin_tokens": model_request_budget.prompt_safety_margin_tokens,
            "active_repo_map_reservation_tokens": base_prompt_budget["reservation_tokens"],
            "base_prompt_budget_tokens": base_prompt_budget["base_prompt_budget_tokens"],
            "effective_base_prompt_budget_chars": base_prompt_budget["effective_chars"],
            "base_prompt_chars": len(base_prompt),
            "estimated_request_tokens": model_request_budget.estimate_request_tokens(prompt),
            "request_over_budget": model_request_budget.request_over_budget(prompt),
            "model_request_budget_source": model_request_budget.source,
            "prompt_chars": len(prompt),
            "prompt_budget_chars": self.total_budget,
            "base_prompt_over_budget": (
                len(base_prompt) > base_prompt_budget["effective_chars"]
            ),
            "prompt_over_budget": (
                len(base_prompt) > base_prompt_budget["effective_chars"]
            ),
            "section_order": list(section_order),
            "section_budgets": {
                section: (None if section == CURRENT_REQUEST_SECTION else int(budgets.get(section, 0)))
                for section in section_order
            },
            "sections": section_metadata,
            "budget_reductions": reduction_log,
            "reduction_order": list(self.reduction_order),
            "relevant_memory": {
                "limit": RELEVANT_MEMORY_LIMIT,
                "selected_count": len(selected_notes),
                "selected_notes": [note["text"] for note in selected_notes],
                "selected_sources": [str(note.get("source", "")).strip() for note in selected_notes],
                "selected_kinds": [str(note.get("kind", "episodic")).strip() or "episodic" for note in selected_notes],
                "selected_durable_count": sum(
                    1 for note in selected_notes if (str(note.get("kind", "episodic")).strip() or "episodic") == "durable"
                ),
                "raw_chars": rendered["relevant_memory"].raw_chars,
                "rendered_chars": rendered["relevant_memory"].rendered_chars,
                "rendered_notes": list(rendered["relevant_memory"].details.get("rendered_notes", [])),
                "rendered_count": int(rendered["relevant_memory"].details.get("rendered_count", 0)),
            },
            "history": {
                "raw_chars": rendered["history"].raw_chars,
                "rendered_chars": rendered["history"].rendered_chars,
                "older_entries_count": int(rendered["history"].details.get("older_entries_count", 0)),
                "collapsed_duplicate_reads": int(rendered["history"].details.get("collapsed_duplicate_reads", 0)),
                "reused_file_summary_count": int(rendered["history"].details.get("reused_file_summary_count", 0)),
                "summarized_tool_count": int(rendered["history"].details.get("summarized_tool_count", 0)),
                "rendered_turns": int(rendered["history"].details.get("rendered_turns", 0)),
            },
            "skills": self._skills_metadata(),
            "current_request": {
                "text": user_message,
                "raw_chars": len(user_message),
                "rendered_chars": len(user_message),
                "section_chars": len(rendered[CURRENT_REQUEST_SECTION].rendered),
            },
            "context_usage": ContextUsageAnalyzer(self.agent).analyze(rendered),
        }
        if repo_map_render is not None:
            metadata["map_context"] = {
                "section_rendered": repo_map_render.section_rendered,
                "contract_rendered": repo_map_render.contract_rendered,
                "fallback_notice_rendered": repo_map_render.fallback_notice_rendered,
                "map_body_raw_chars": repo_map_render.map_body_raw_chars,
                "map_body_rendered_chars": repo_map_render.map_body_rendered_chars,
                "section_rendered_chars": repo_map_render.section_rendered_chars,
                "section_rendered_hash": repo_map_render.section_rendered_hash,
                "base_prompt_reduction_applied": repo_map_render.base_prompt_reduction_applied,
                "omission_reason": repo_map_render.omission_reason,
            }
        return metadata

    def _skills_metadata(self):
        skills = getattr(self.agent, "skills", {})
        items = [skill.metadata() for skill in skillslib.list_skills(skills, user_invocable_only=False)]
        return {
            "available_count": len(items),
            "user_invocable_count": sum(1 for item in items if item["user_invocable"]),
            "items": items,
        }
