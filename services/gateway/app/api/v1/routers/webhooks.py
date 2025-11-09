import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ....models.events import EventRaw
from ....services.event_bus import get_event_bus
from ...deps import get_db_session

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _hmac_sha256(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256)
    return "sha256=" + mac.hexdigest()


@router.post("/github")
async def github_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    x_github_delivery: str | None = Header(None, alias="X-GitHub-Delivery"),
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
    # publish
    try:
        import asyncio

        asyncio.create_task(
            get_event_bus().publish_json(
                subject="events.github",
                payload={
                    "id": evt.id,
                    "event_type": evt.event_type,
                    "delivery_id": evt.delivery_id,
                },
            )
        )
    except Exception:
        pass
    return {"status": "ok", "id": evt.id}


@router.post("/jira")
async def jira_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    x_atlassian_webhook_identifier: str | None = Header(
        None, alias="X-Atlassian-Webhook-Identifier"
    ),
) -> dict:
    body = await request.body()
    delivery = x_atlassian_webhook_identifier or ""
    if delivery:
        exists = session.execute(
            select(EventRaw).where(
                EventRaw.source == "jira", EventRaw.delivery_id == delivery
            )
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
    try:
        import asyncio

        asyncio.create_task(
            get_event_bus().publish_json(
                subject="events.jira",
                payload={
                    "id": evt.id,
                    "event_type": evt.event_type,
                    "delivery_id": evt.delivery_id,
                },
            )
        )
    except Exception:
        pass
    return {"status": "ok", "id": evt.id}


@router.post("/shortcut")
async def shortcut_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    x_shortcut_signature: str | None = Header(None, alias="X-Shortcut-Signature"),
) -> dict:
    """
    Shortcut webhook handler.

    Handles story updates, creation, deletion, etc.
    See: https://developer.shortcut.com/api/webhooks

    Shortcut sends:
    - X-Shortcut-Signature: HMAC-SHA256 signature (optional verification)
    - Payload with actions: story-create, story-update, story-delete, etc.
    """
    body = await request.body()

    # Parse payload to extract event info
    import json

    try:
        payload_json = json.loads(body)
        action = payload_json.get("action", "unknown")
        story_id = payload_json.get("id") or payload_json.get("primary_id", "")
        # Use action + story_id as delivery_id for idempotency
        delivery = f"shortcut-{action}-{story_id}"
    except Exception:
        # If parsing fails, use a timestamp-based ID
        import time

        delivery = f"shortcut-{int(time.time() * 1000)}"
        action = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(
                EventRaw.source == "shortcut", EventRaw.delivery_id == delivery
            )
        ).scalar_one_or_none()
        if exists:
            return {"status": "duplicate", "id": exists.id}

    # Signature verification (optional)
    secret = request.app.state.__dict__.get("shortcut_webhook_secret")
    if secret and x_shortcut_signature:
        expected = _hmac_sha256(secret, body)
        if not hmac.compare_digest(expected, x_shortcut_signature):
            raise HTTPException(status_code=401, detail="invalid signature")

    # Store event
    evt = EventRaw(
        source="shortcut",
        event_type=action,
        delivery_id=delivery,
        signature=x_shortcut_signature,
        headers=dict(request.headers),
        payload=body.decode("utf-8", errors="replace"),
    )
    session.add(evt)
    session.commit()

    # Publish to event bus
    try:
        import asyncio

        asyncio.create_task(
            get_event_bus().publish_json(
                subject="events.shortcut",
                payload={
                    "id": evt.id,
                    "event_type": evt.event_type,
                    "delivery_id": evt.delivery_id,
                    "action": action,
                },
            )
        )
    except Exception:
        pass

    return {"status": "ok", "id": evt.id}
