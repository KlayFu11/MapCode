from pico.features.map_engine.context_renderer import focused_definition_candidates
from pico.features.map_engine.models import DefinitionRecord


def _definition(name: str, path: str, line: int = 0) -> DefinitionRecord:
    return DefinitionRecord(name=name, path=path, line=line, kind="function")


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
