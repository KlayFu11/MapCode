from pico.features.map_engine.prompt_analyzer import (
    analyze_prompt,
    extract_effective_symbol_hits,
    extract_mentioned_idents,
)
from pico.features.map_engine.models import CacheEvidence
from pico.features.map_engine.models import FileRecord
from pico.features.map_engine.symbol_index import SymbolIndex


def _symbol_index(
    paths: tuple[str, ...],
    all_defs: frozenset[str] = frozenset(),
) -> SymbolIndex:
    file_records = {
        path: FileRecord(
            path=path,
            mtime_ns=1,
            size=1,
            parser_version="test",
            query_version="test",
            schema_version="test",
        )
        for path in paths
    }
    return SymbolIndex(
        all_defs=all_defs,
        definitions_by_symbol={},
        definitions_by_file={},
        references_by_file={},
        file_records=file_records,
        index_snapshot_id="test",
        skipped_files=(),
        cache_status=CacheEvidence(
            read_status="miss",
            write_status="not_needed",
            reused_files=(),
            parsed_files=(),
            skipped_files=(),
        ),
    )


def test_extract_mentioned_idents_keeps_first_seen_order_across_separators():
    text = "Use pico/core/runtime.py, Runtime! pico/core/runtime.py; run_turn Runtime"

    assert extract_mentioned_idents(text) == (
        "Use",
        "pico",
        "core",
        "runtime",
        "py",
        "Runtime",
        "run_turn",
    )


def test_extract_mentioned_idents_preserves_case_and_does_not_filter_tokens():
    text = "class 123 x JWTAuth jwtauth if X 123"

    assert extract_mentioned_idents(text) == (
        "class",
        "123",
        "x",
        "JWTAuth",
        "jwtauth",
        "if",
        "X",
    )


def test_extract_effective_symbol_hits_is_case_sensitive():
    mentioned_idents = ("JWTAuth", "jwtauth", "run", "Run", "class")
    all_defs = {"JWTAuth", "Run", "class"}

    assert extract_effective_symbol_hits(mentioned_idents, all_defs) == (
        "JWTAuth",
        "Run",
        "class",
    )


def test_extract_effective_symbol_hits_keeps_prompt_order_and_dedupes():
    mentioned_idents = (
        "Parser",
        "Runtime",
        "Parser",
        "ToolRegistry",
        "runtime",
        "Runtime",
        "Runner",
    )
    all_defs = {"Runtime", "Parser", "ToolRegistry", "Runner"}

    assert extract_effective_symbol_hits(mentioned_idents, all_defs) == (
        "Parser",
        "Runtime",
        "ToolRegistry",
        "Runner",
    )


def test_analyze_prompt_matches_exact_repo_paths_in_prompt_order(tmp_path):
    repo_root = tmp_path / "repo"
    symbol_index = _symbol_index(
        (
            "pico/core/runtime.py",
            "pico/core/session.py",
        )
    )
    text = (
        "Check `pico/core/runtime.py`, "
        "then './pico/core/session.py', "
        "'pico\\core\\session.py', "
        f'and "{repo_root / "pico/core/runtime.py"}".'
    )

    analysis = analyze_prompt(text, symbol_index, repo_root)

    assert analysis.mentioned_files == (
        "pico/core/runtime.py",
        "pico/core/session.py",
    )
    assert analysis.branch == "specific"


def test_analyze_prompt_rejects_outside_directory_and_prefix_paths(tmp_path):
    repo_root = tmp_path / "repo"
    outside_path = tmp_path / "outside" / "external.py"
    symbol_index = _symbol_index(
        (
            "pico/core/runtime.py",
            "pico/core/session.py",
        )
    )

    analysis = analyze_prompt(
        f"Check {outside_path}, pico/core/, ./pico/core, and pico/core/run.",
        symbol_index,
        repo_root,
    )

    assert analysis.mentioned_files == ()
    assert analysis.path_ident_hits == ("pico", "core")
    assert analysis.branch == "specific"


def test_analyze_prompt_matches_unique_basename_with_exact_case_only(tmp_path):
    symbol_index = _symbol_index(
        (
            "app/Auth.py",
            "legacy/Auth.py",
            "services/UserService.py",
        )
    )

    analysis = analyze_prompt(
        "Review UserService.py, userservice.py, and Auth.py.",
        symbol_index,
        tmp_path,
    )

    assert analysis.mentioned_files == ("services/UserService.py",)


def test_analyze_prompt_matches_unique_stem_case_insensitive_with_length_guard(
    tmp_path,
):
    symbol_index = _symbol_index(
        (
            "app/payment_handler.py",
            "pkg/auth.py",
            "old/session_store.py",
            "new/session_store.py",
        )
    )

    analysis = analyze_prompt(
        "Review payment_HANDLER, auth, and SESSION_STORE.",
        symbol_index,
        tmp_path,
    )

    assert analysis.mentioned_files == ("app/payment_handler.py",)


def test_analyze_prompt_keeps_directory_style_tokens_out_of_mentioned_files(
    tmp_path,
):
    symbol_index = _symbol_index(
        (
            "pico/core/runtime.py",
            "pico/tools/standalone.py",
            "tests/test_runtime.py",
        )
    )

    analysis = analyze_prompt("Explain pico/ package.", symbol_index, tmp_path)

    assert analysis.mentioned_files == ()
    assert analysis.path_ident_hits == ("pico",)
    assert analysis.path_ident_hit_files["pico"] == (
        "pico/core/runtime.py",
        "pico/tools/standalone.py",
    )
    assert analysis.branch == "specific"


def test_analyze_prompt_preserves_path_ident_order_case_and_sorted_files(tmp_path):
    symbol_index = _symbol_index(
        (
            "pico/core/runtime.py",
            "pico/core/session.py",
            "pico/tools/runner.py",
            "tests/core/test_runtime.py",
        )
    )

    analysis = analyze_prompt("Trace PICO then core.", symbol_index, tmp_path)

    assert analysis.path_ident_hits == ("PICO", "core")
    assert tuple(analysis.path_ident_hit_files) == ("PICO", "core")
    assert analysis.path_ident_hit_files["PICO"] == (
        "pico/core/runtime.py",
        "pico/core/session.py",
        "pico/tools/runner.py",
    )
    assert analysis.path_ident_hit_files["core"] == (
        "pico/core/runtime.py",
        "pico/core/session.py",
        "tests/core/test_runtime.py",
    )
    assert analysis.mentioned_files == ()
    assert analysis.branch == "specific"


def test_analyze_prompt_uses_effective_symbol_hits_for_specific_branch(tmp_path):
    symbol_index = _symbol_index(
        ("pico/core/runtime.py",),
        all_defs=frozenset({"Coordinator"}),
    )

    analysis = analyze_prompt("Explain Coordinator.", symbol_index, tmp_path)

    assert analysis.effective_symbol_hits == ("Coordinator",)
    assert analysis.path_ident_hits == ()
    assert analysis.mentioned_files == ()
    assert analysis.branch == "specific"


def test_analyze_prompt_uses_fuzzy_branch_without_effective_hits(tmp_path):
    symbol_index = _symbol_index(
        ("pico/core/runtime.py",),
        all_defs=frozenset({"Runtime"}),
    )

    analysis = analyze_prompt("Explain unknown behavior.", symbol_index, tmp_path)

    assert analysis.mentioned_files == ()
    assert analysis.effective_symbol_hits == ()
    assert analysis.path_ident_hits == ()
    assert analysis.path_ident_hit_files == {}
    assert analysis.branch == "fuzzy"
