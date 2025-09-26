from typing import Optional


def map_github_identity(login: Optional[str], email: Optional[str]) -> Optional[dict]:
    if not login and not email:
        return None
    return {
        "external_type": "github",
        "external_id": login or email or "",
        "display_name": login or email,
    }


def map_slack_identity(
    user_id: Optional[str], email: Optional[str], real_name: Optional[str]
) -> Optional[dict]:
    if not user_id and not email:
        return None
    return {
        "external_type": "slack",
        "external_id": user_id or email or "",
        "display_name": real_name or email or user_id,
    }
