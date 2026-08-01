"""Small cross-file reference for the authentication fixture."""

from src.auth import authenticate


def parse_token(raw_token: str) -> bool:
    return authenticate(raw_token)
