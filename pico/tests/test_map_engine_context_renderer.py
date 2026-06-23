from dataclasses import dataclass

from pico.features.map_engine.config import BROAD_MAP_BUDGET_TOKENS
from pico.features.map_engine.config import FOCUSED_MAP_BUDGET_TOKENS
from pico.features.map_engine.context_renderer import focused_definition_candidates
from pico.features.map_engine.context_renderer import render_ranked_context
from pico.features.map_engine.models import DefinitionRecord
from pico.features.map_engine.models import PromptAnalysis
from pico.features.map_engine.models import RankContributorEvidence


@dataclass(frozen=True)
class RankedFileScore:
    path: str
    node_pagerank: float = 0.0
    pagerank_norm: float = 0.0
    definition_rank_sum: float = 0.0
    top_rank_contributors: tuple[RankContributorEvidence, ...] = ()


def _definition(name: str, path: str, line: int = 0) -> DefinitionRecord:
    return DefinitionRecord(name=name, path=path, line=line, kind="function")


def _analysis(
    *,
    effective_symbol_hits: tuple[str, ...] = (),
    path_ident_hit_files: dict[str, tuple[str, ...]] | None = None,
) -> PromptAnalysis:
    path_ident_hit_files = path_ident_hit_files or {}
    return PromptAnalysis(
        branch="specific",
        mentioned_files=(),
        mentioned_idents=(),
        effective_symbol_hits=effective_symbol_hits,
        path_ident_hits=tuple(path_ident_hit_files),
        path_ident_hit_files=path_ident_hit_files,
    )


def test_render_ranked_context_uses_tree_context_for_tagged_file():
    service = _definition("Service", "pkg/service.py", line=0)
    run = _definition("run", "pkg/service.py", line=5)

    result = render_ranked_context(
        ranked_files=(RankedFileScore("pkg/service.py"),),
        ranked_definitions=(service, run),
        definitions_by_file={"pkg/service.py": (service, run)},
        analysis=_analysis(),
        source_by_path={
            "pkg/service.py": "\n".join(
                [
                    "class Service:",
                    "    def call(self):",
                    "        return run()",
                    "",
                    "",
                    "def run():",
                    "    return 'ok'",
                ]
            ),
        },
    )

    assert "pkg/service.py:" in result.repo_map_text
    assert "class Service" in result.repo_map_text
    assert "def run" in result.repo_map_text
    assert result.rendered_files[0].rendered_symbols == ("Service", "run")
    assert result.rendered_symbols == ("Service", "run")


def test_render_ranked_context_preserves_ranked_file_order():
    result = render_ranked_context(
        ranked_files=(
            RankedFileScore("zeta.py", node_pagerank=0.7),
            RankedFileScore("alpha.py", node_pagerank=0.4),
        ),
        ranked_definitions=(),
        definitions_by_file={},
        analysis=_analysis(),
        source_by_path={},
    )

    assert tuple(file.path for file in result.rendered_files) == (
        "zeta.py",
        "alpha.py",
    )
    assert tuple(file.render_rank for file in result.rendered_files) == (1, 2)
    assert result.repo_map_text.index("zeta.py:") < result.repo_map_text.index(
        "alpha.py:"
    )


def test_render_ranked_context_outputs_path_for_file_without_tags():
    result = render_ranked_context(
        ranked_files=(RankedFileScore("pkg/empty.py"),),
        ranked_definitions=(),
        definitions_by_file={},
        analysis=_analysis(),
        source_by_path={"pkg/empty.py": "# no definitions"},
    )

    assert result.repo_map_text == "pkg/empty.py:"
    assert result.rendered_files[0].path == "pkg/empty.py"
    assert result.rendered_files[0].rendered_symbols == ()


def test_render_ranked_context_uses_ranked_definitions_as_render_candidates():
    helper = _definition("helper", "pkg/helper.py", line=0)

    result = render_ranked_context(
        ranked_files=(RankedFileScore("pkg/helper.py"),),
        ranked_definitions=(),
        definitions_by_file={"pkg/helper.py": (helper,)},
        analysis=_analysis(effective_symbol_hits=("helper",)),
        source_by_path={"pkg/helper.py": "def helper():\n    return None\n"},
    )

    assert result.repo_map_text == "pkg/helper.py:"
    assert result.rendered_files[0].prompt_symbol_hits == ("helper",)
    assert result.rendered_files[0].rendered_symbols == ()


def test_render_ranked_context_falls_back_to_path_when_tree_context_fails():
    invalid = _definition("Invalid", "pkg/invalid.unknown", line=0)

    result = render_ranked_context(
        ranked_files=(RankedFileScore("pkg/invalid.unknown"),),
        ranked_definitions=(invalid,),
        definitions_by_file={"pkg/invalid.unknown": (invalid,)},
        analysis=_analysis(),
        source_by_path={"pkg/invalid.unknown": "def invalid():\n    pass\n"},
    )

    assert result.repo_map_text == "pkg/invalid.unknown:"
    assert result.rendered_files[0].rendered_symbols == ()


def test_render_ranked_context_projects_path_idents_to_file_evidence():
    service = _definition("Service", "pkg/service.py", line=0)

    result = render_ranked_context(
        ranked_files=(RankedFileScore("pkg/service.py"),),
        ranked_definitions=(service,),
        definitions_by_file={"pkg/service.py": (service,)},
        analysis=_analysis(
            path_ident_hit_files={
                "Pico": ("pkg/other.py", "pkg/service.py"),
                "service": ("pkg/service.py",),
                "missing": ("pkg/missing.py",),
            },
        ),
        source_by_path={"pkg/service.py": "class Service:\n    pass\n"},
    )

    evidence = result.rendered_files[0]
    assert evidence.prompt_path_ident_hits == ("Pico", "service")
    assert "path_ident_match" in evidence.reason_codes


def test_render_ranked_context_records_omitted_file_evidence():
    omitted = _definition("Omitted", "pkg/omitted.py", line=0)

    result = render_ranked_context(
        ranked_files=(),
        ranked_definitions=(),
        definitions_by_file={"pkg/omitted.py": (omitted,)},
        analysis=_analysis(
            effective_symbol_hits=("Omitted",),
            path_ident_hit_files={"omitted": ("pkg/omitted.py",)},
        ),
        source_by_path={},
        omitted_files=(RankedFileScore("pkg/omitted.py", node_pagerank=0.3),),
        omission_reason="not_rendered",
    )

    evidence = result.omitted_files[0]
    assert evidence.path == "pkg/omitted.py"
    assert evidence.omission_reason == "not_rendered"
    assert evidence.prompt_symbol_hits == ("Omitted",)
    assert evidence.prompt_path_ident_hits == ("omitted",)
    assert "path_ident_match" in evidence.reason_codes


def test_render_ranked_context_records_prompt_symbol_hits_by_file():
    service = _definition("Service", "pkg/service.py", line=0)
    helper = _definition("helper", "pkg/helper.py", line=0)
    unrendered = _definition("Unrendered", "pkg/service.py", line=3)

    result = render_ranked_context(
        ranked_files=(RankedFileScore("pkg/service.py"),),
        ranked_definitions=(service,),
        definitions_by_file={
            "pkg/service.py": (service, unrendered),
            "pkg/helper.py": (helper,),
        },
        analysis=_analysis(effective_symbol_hits=("helper", "Unrendered", "Service")),
        source_by_path={"pkg/service.py": "class Service:\n    pass\n"},
    )

    evidence = result.rendered_files[0]
    assert evidence.prompt_symbol_hits == ("Unrendered", "Service")
    assert evidence.rendered_symbols == ("Service",)


def test_render_ranked_context_records_default_focused_rendering_evidence():
    result = render_ranked_context(
        ranked_files=(RankedFileScore("pkg/empty.py"),),
        ranked_definitions=(),
        definitions_by_file={},
        analysis=_analysis(),
        source_by_path={},
    )

    assert result.rendering.target_tokens == FOCUSED_MAP_BUDGET_TOKENS
    assert result.rendering.target_chars == FOCUSED_MAP_BUDGET_TOKENS * 4
    assert result.rendering.used_chars == len(result.repo_map_text)
    assert result.rendering.estimated_tokens == (len(result.repo_map_text) + 3) // 4
    assert result.rendering.budget_reduction_applied is False
    assert result.rendering.focus_truncated is False


def test_render_ranked_context_uses_broad_rendering_budget():
    result = render_ranked_context(
        ranked_files=(RankedFileScore("pkg/empty.py"),),
        ranked_definitions=(),
        definitions_by_file={},
        analysis=_analysis(),
        source_by_path={},
        mode="broad",
    )

    assert result.rendering.target_tokens == BROAD_MAP_BUDGET_TOKENS
    assert result.rendering.target_chars == BROAD_MAP_BUDGET_TOKENS * 4


def test_render_ranked_context_omits_complete_blocks_after_budget_exhaustion():
    target_chars = FOCUSED_MAP_BUDGET_TOKENS * 4
    large_path = "a" * (target_chars - 3)
    omitted_path = "pkg/omitted.py"
    explicit_path = "pkg/explicit.py"

    result = render_ranked_context(
        ranked_files=(
            RankedFileScore(large_path),
            RankedFileScore(omitted_path, node_pagerank=0.2),
        ),
        ranked_definitions=(),
        definitions_by_file={},
        analysis=_analysis(),
        source_by_path={},
        omitted_files=(RankedFileScore(explicit_path, node_pagerank=0.1),),
        omission_reason="not_rendered",
    )

    assert tuple(file.path for file in result.rendered_files) == (large_path,)
    assert tuple(file.render_rank for file in result.rendered_files) == (1,)
    assert result.repo_map_text == f"{large_path}:"
    assert len(result.repo_map_text) == target_chars - 2
    assert tuple(file.path for file in result.omitted_files) == (
        explicit_path,
        omitted_path,
    )
    assert tuple(file.omission_reason for file in result.omitted_files) == (
        "not_rendered",
        "map_budget_exhausted",
    )
    assert result.rendering.budget_reduction_applied is True
    assert result.rendering.used_chars == len(result.repo_map_text)
    assert result.rendering.estimated_tokens == (len(result.repo_map_text) + 3) // 4


def test_render_ranked_context_falls_back_to_path_only_when_focus_block_exceeds_budget():
    focus_path = "pkg/focus.py"
    definitions = tuple(
        _definition(f"func_{index}", focus_path, line=index * 3)
        for index in range(700)
    )
    source = "\n".join(
        f"def func_{index}():\n    return {index}\n"
        for index in range(700)
    )

    result = render_ranked_context(
        ranked_files=(RankedFileScore(focus_path),),
        ranked_definitions=definitions,
        definitions_by_file={focus_path: definitions},
        analysis=_analysis(),
        source_by_path={focus_path: source},
        focus_fnames=(focus_path,),
    )

    assert result.repo_map_text == "pkg/focus.py:"
    assert tuple(file.path for file in result.rendered_files) == (focus_path,)
    assert result.rendered_files[0].render_rank == 1
    assert result.rendered_files[0].rendered_symbols == ()
    assert result.omitted_files == ()
    assert result.rendered_symbols == ()
    assert result.rendering.budget_reduction_applied is True
    assert result.rendering.focus_truncated is True


def test_render_ranked_context_marks_focus_truncated_when_focus_file_is_omitted():
    target_chars = FOCUSED_MAP_BUDGET_TOKENS * 4
    large_path = "a" * (target_chars - 3)
    focus_path = "pkg/focus.py"

    result = render_ranked_context(
        ranked_files=(
            RankedFileScore(large_path),
            RankedFileScore(focus_path),
        ),
        ranked_definitions=(),
        definitions_by_file={},
        analysis=_analysis(),
        source_by_path={},
        focus_fnames=(focus_path,),
    )

    assert tuple(file.path for file in result.rendered_files) == (large_path,)
    assert result.omitted_files[0].path == focus_path
    assert result.omitted_files[0].omission_reason == "map_budget_exhausted"
    assert result.rendering.focus_truncated is True


def test_focused_definition_candidates_prefixes_exact_hits():
    hit = _definition("hit", "hit.py")
    ranked_first = _definition("ranked_first", "ranked_first.py")

    result = focused_definition_candidates(
        ranked_definitions=(ranked_first, hit),
        definitions_by_symbol={"hit": (hit,)},
        effective_symbol_hits=("hit",),
    )

    assert result == (hit, ranked_first)


def test_focused_definition_candidates_keeps_multi_symbol_order():
    alpha = _definition("alpha", "alpha.py")
    beta = _definition("beta", "beta.py")
    ranked_first = _definition("ranked_first", "ranked_first.py")

    result = focused_definition_candidates(
        ranked_definitions=(ranked_first, beta, alpha),
        definitions_by_symbol={
            "alpha": (alpha,),
            "beta": (beta,),
        },
        effective_symbol_hits=("beta", "alpha"),
    )

    assert result == (beta, alpha, ranked_first)


def test_focused_definition_candidates_keeps_snapshot_definition_order():
    first = _definition("target", "target.py", line=20)
    second = _definition("target", "target.py", line=2)
    ranked_first = _definition("ranked_first", "ranked_first.py")

    result = focused_definition_candidates(
        ranked_definitions=(ranked_first, second, first),
        definitions_by_symbol={"target": (first, second)},
        effective_symbol_hits=("target",),
    )

    assert result == (first, second, ranked_first)


def test_focused_definition_candidates_dedupes_stably():
    shared = _definition("shared", "shared.py")
    other = _definition("other", "other.py")

    result = focused_definition_candidates(
        ranked_definitions=(shared, other),
        definitions_by_symbol={
            "shared": (shared,),
            "alias": (shared,),
        },
        effective_symbol_hits=("shared", "alias"),
    )

    assert result == (shared, other)


def test_focused_definition_candidates_ignores_missing_symbols():
    hit = _definition("hit", "hit.py")
    ranked_first = _definition("ranked_first", "ranked_first.py")

    result = focused_definition_candidates(
        ranked_definitions=(ranked_first, hit),
        definitions_by_symbol={"hit": (hit,)},
        effective_symbol_hits=("missing", "hit"),
    )

    assert result == (hit, ranked_first)
