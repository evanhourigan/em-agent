def map_github_identity(login: str | None, email: str | None) -> dict | None:
    if not login and not email:
        return None
    return {
        "external_type": "github",
        "external_id": login or email or "",
        "display_name": login or email,
    }


def map_slack_identity(
    user_id: str | None, email: str | None, real_name: str | None
) -> dict | None:
    if not user_id and not email:
        return None
    return {
        "external_type": "slack",
        "external_id": user_id or email or "",
        "display_name": real_name or email or user_id,
    }
