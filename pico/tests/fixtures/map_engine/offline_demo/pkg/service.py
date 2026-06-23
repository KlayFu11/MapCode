def load_user_profile(token: str) -> dict[str, str]:
    return {"name": token or "guest"}


def build_user_context(
    subject: str,
    profile: dict[str, str],
    secret: str,
) -> dict[str, str]:
    return {
        "subject": subject,
        "name": profile["name"],
        "secret": secret,
    }
