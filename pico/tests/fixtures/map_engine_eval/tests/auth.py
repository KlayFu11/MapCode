"""Regression-shaped test path retained for selector preference cases."""

from src.auth import JWTAuth


def test_valid_token_is_accepted() -> None:
    assert JWTAuth().validate_token("valid.fixture")
