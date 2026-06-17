from pico.features.map_engine import config


def test_map_engine_fixed_token_budgets_match_spec():
    assert config.FOCUSED_MAP_BUDGET_TOKENS == 4_096
    assert config.BROAD_MAP_BUDGET_TOKENS == 8_192

    effective_focused_budget = config.FOCUSED_MAP_BUDGET_TOKENS

    assert effective_focused_budget == 4_096
    assert "CHAR_BUDGET" not in vars(config)
    assert "FOCUSED_MAP_WITH_FILES_BUDGET_TOKENS" not in vars(config)


def test_selector_catalog_limits_belong_to_map_engine_config():
    assert config.SELECTOR_CATALOG_MAX_TOKENS == 4_096
    assert config.SELECTOR_CATALOG_MAX_FILES == 200
    assert config.SELECTOR_CATALOG_MAX_DEFS_PER_FILE == 20

    assert not hasattr(config, "MAX_SELECTOR_SUGGESTED_FILES")
    assert not hasattr(config, "SELECTOR_REASONING_MAX_CHARS")


def test_map_engine_version_constants_are_stable_cache_inputs():
    assert config.MAP_ENGINE_SCHEMA_VERSION == "mapcode.map-engine.v1"
    assert config.PARSER_VERSION == "mapcode-python-tags-v1"
    assert config.QUERY_VERSION == "mapcode-python-query-v1"
    assert config.RANKING_POLICY_VERSION == "mapcode-pagerank-v1"


def test_pagerank_parameters_match_spec():
    assert config.PAGERANK_ALPHA == 0.85
    assert config.PAGERANK_MAX_ITER == 100
    assert config.PAGERANK_TOL == 1e-6


def test_aider_style_multiplier_parameters_match_spec():
    assert config.IDENT_BOOST == 10.0
    assert config.STRUCTURED_IDENT_BOOST == 10.0
    assert config.PRIVATE_IDENT_PENALTY == 0.1
    assert config.COMMON_IDENT_PENALTY == 0.1
    assert config.COMMON_IDENT_DEFINER_THRESHOLD == 5
    assert config.STRUCTURED_IDENT_MIN_LENGTH == 8
    assert config.FOCUS_OUTBOUND_BOOST == 50.0
    assert config.TOP_RANKED_FILES_LIMIT == 5
