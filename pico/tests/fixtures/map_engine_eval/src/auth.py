"""Authentication definitions used by the fixed retrieval fixture."""


class JWTAuth:
    def validate_token(self, token: str) -> bool:
        return token.startswith("valid.")


def authenticate(token: str) -> bool:
    return JWTAuth().validate_token(token)
