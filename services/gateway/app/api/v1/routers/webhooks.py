import hashlib
import hmac
import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ....models.events import EventRaw
from ...deps import get_db_session

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _hmac_sha256(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256)
    return "sha256=" + mac.hexdigest()


@router.post("/github")
async def github_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    x_github_delivery: Optional[str] = Header(None, alias="X-GitHub-Delivery"),
) -> dict:
    body = await request.body()

    # Idempotency: skip if we have this delivery id already
    if x_github_delivery:
        exists = session.execute(
            select(EventRaw).where(
                EventRaw.source == "github", EventRaw.delivery_id == x_github_delivery
            )
        ).scalar_one_or_none()
        if exists:
            return {"status": "duplicate", "id": exists.id}

    # Signature check if secret configured (optional at this stage)
    secret = request.app.state.__dict__.get("github_webhook_secret")
    if secret and x_hub_signature_256:
        expected = _hmac_sha256(secret, body)
        if not hmac.compare_digest(expected, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="invalid signature")

    evt = EventRaw(
        source="github",
        event_type=x_github_event or "unknown",
        delivery_id=x_github_delivery or "",
        signature=x_hub_signature_256,
        headers=dict(request.headers),
        payload=body.decode("utf-8", errors="replace"),
    )
    session.add(evt)
    session.commit()
    return {"status": "ok", "id": evt.id}


@router.post("/jira")
async def jira_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    x_atlassian_webhook_identifier: Optional[str] = Header(
        None, alias="X-Atlassian-Webhook-Identifier"
    ),
) -> dict:
    body = await request.body()
    delivery = x_atlassian_webhook_identifier or ""
    if delivery:
        exists = session.execute(
            select(EventRaw).where(EventRaw.source == "jira", EventRaw.delivery_id == delivery)
        ).scalar_one_or_none()
        if exists:
            return {"status": "duplicate", "id": exists.id}

    evt = EventRaw(
        source="jira",
        event_type="unknown",
        delivery_id=delivery,
        signature=None,
        headers=dict(request.headers),
        payload=body.decode("utf-8", errors="replace"),
    )
    session.add(evt)
    session.commit()
    return {"status": "ok", "id": evt.id}
