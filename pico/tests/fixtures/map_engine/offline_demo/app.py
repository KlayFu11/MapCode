from pkg.auth import JWTAuth
from pkg.private_tools import _private_token
from pkg.service import build_user_context
from pkg.service import load_user_profile


def run_auth_flow(token: str) -> dict[str, str]:
    auth = JWTAuth()
    profile = load_user_profile(token)
    secret = _private_token(token)
    subject = auth.validate_token(token)
    return build_user_context(subject, profile, secret)


def preview_profile(token: str) -> str:
    profile = load_user_profile(token)
    return profile["name"]
