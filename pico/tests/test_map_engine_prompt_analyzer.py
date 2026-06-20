from pico.features.map_engine.prompt_analyzer import (
    extract_effective_symbol_hits,
    extract_mentioned_idents,
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
