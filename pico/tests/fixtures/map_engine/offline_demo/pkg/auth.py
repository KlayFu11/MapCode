from pkg.private_tools import _private_token

AUTH_REALM = "fixture"


class JWTAuth:
    def validate_token(self, token: str) -> str:
        if not token:
            return "anonymous"
        return _private_token(token)
