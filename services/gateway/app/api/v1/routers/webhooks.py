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
    """
    GitHub webhook handler for all event types.

    Supported events include:
    - pull_request: PR lifecycle (opened, merged, closed, etc.)
    - push: Code pushes and commits
    - issues: Issue lifecycle (opened, closed, labeled, assigned, etc.)
    - workflow_run: GitHub Actions CI/CD runs
    - Any other GitHub webhook event

    See: https://docs.github.com/en/webhooks/webhook-events-and-payloads
    """
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


@router.post("/linear")
async def linear_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    linear_signature: str | None = Header(None, alias="Linear-Signature"),
) -> dict:
    """
    Linear webhook handler.

    Handles issue updates, creation, deletion, comments, projects, etc.
    See: https://developers.linear.app/docs/graphql/webhooks

    Linear sends:
    - Linear-Signature: HMAC-SHA256 signature (optional verification)
    - Payload with: action, data, type, url, createdAt
    - Types: Issue, Comment, Project, Cycle, etc.
    - Actions: create, update, remove
    """
    body = await request.body()

    # Parse payload to extract event info
    import json

    try:
        payload_json = json.loads(body)
        action = payload_json.get("action", "unknown")
        event_type = payload_json.get("type", "unknown")

        # Extract ID from data object
        data = payload_json.get("data", {})
        entity_id = data.get("id", "")

        # Use type + action + entity_id as delivery_id for idempotency
        # Example: "linear-Issue-create-abc-123"
        delivery = f"linear-{event_type}-{action}-{entity_id}"
    except Exception:
        # If parsing fails, use a timestamp-based ID
        import time

        delivery = f"linear-{int(time.time() * 1000)}"
        action = "unknown"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(
                EventRaw.source == "linear", EventRaw.delivery_id == delivery
            )
        ).scalar_one_or_none()
        if exists:
            return {"status": "duplicate", "id": exists.id}

    # Signature verification (optional)
    secret = request.app.state.__dict__.get("linear_webhook_secret")
    if secret and linear_signature:
        expected = _hmac_sha256(secret, body)
        if not hmac.compare_digest(expected, linear_signature):
            raise HTTPException(status_code=401, detail="invalid signature")

    # Store event
    evt = EventRaw(
        source="linear",
        event_type=f"{event_type}:{action}",  # e.g., "Issue:create"
        delivery_id=delivery,
        signature=linear_signature,
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
                subject="events.linear",
                payload={
                    "id": evt.id,
                    "event_type": evt.event_type,
                    "delivery_id": evt.delivery_id,
                    "action": action,
                    "type": event_type,
                },
            )
        )
    except Exception:
        pass

    return {"status": "ok", "id": evt.id}


@router.post("/pagerduty")
async def pagerduty_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    x_pagerduty_signature: str | None = Header(None, alias="X-PagerDuty-Signature"),
) -> dict:
    """
    PagerDuty webhook handler.

    Handles incident events, on-call changes, etc.
    See: https://developer.pagerduty.com/docs/webhooks/v3-overview/

    PagerDuty sends:
    - X-PagerDuty-Signature: HMAC-SHA256 signature (optional verification)
    - Payload with: event (nested object with type, occurred_at, data)
    - Event types: incident.triggered, incident.acknowledged, incident.resolved, etc.
    """
    body = await request.body()

    # Parse payload to extract event info
    import json

    try:
        payload_json = json.loads(body)
        # PagerDuty v3 webhook format
        event = payload_json.get("event", {})
        event_type = event.get("event_type", "unknown")

        # Extract incident data
        data = event.get("data", {})
        incident_id = data.get("id", "")

        # Use event_type + incident_id as delivery_id for idempotency
        # Example: "pagerduty-incident.triggered-PXXXXXX"
        delivery = f"pagerduty-{event_type}-{incident_id}"
    except Exception:
        # If parsing fails, use a timestamp-based ID
        import time

        delivery = f"pagerduty-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(
                EventRaw.source == "pagerduty", EventRaw.delivery_id == delivery
            )
        ).scalar_one_or_none()
        if exists:
            return {"status": "duplicate", "id": exists.id}

    # Signature verification (optional)
    secret = request.app.state.__dict__.get("pagerduty_webhook_secret")
    if secret and x_pagerduty_signature:
        expected = _hmac_sha256(secret, body)
        if not hmac.compare_digest(expected, x_pagerduty_signature):
            raise HTTPException(status_code=401, detail="invalid signature")

    # Store event
    evt = EventRaw(
        source="pagerduty",
        event_type=event_type,
        delivery_id=delivery,
        signature=x_pagerduty_signature,
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
                subject="events.pagerduty",
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


@router.post("/slack")
async def slack_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    x_slack_request_timestamp: str | None = Header(None, alias="X-Slack-Request-Timestamp"),
    x_slack_signature: str | None = Header(None, alias="X-Slack-Signature"),
) -> dict:
    """
    Slack Events API webhook handler.

    Handles Slack events including:
    - message.channels: Messages posted to channels
    - reaction_added/reaction_removed: Emoji reactions
    - app_mention: Bot mentions
    - member_joined_channel: User joins channel
    - file_shared: File uploads
    - Any other Slack event

    See: https://api.slack.com/events-api

    Slack sends:
    - X-Slack-Request-Timestamp: Request timestamp for signature verification
    - X-Slack-Signature: HMAC-SHA256 signature (optional verification)
    - Payload with: type, event, team_id, event_id, etc.
    """
    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # Handle URL verification challenge
        if payload_json.get("type") == "url_verification":
            return {"challenge": payload_json.get("challenge")}

        # Extract event info
        event = payload_json.get("event", {})
        event_type = event.get("type", "unknown")
        event_id = payload_json.get("event_id", "")

        # Use event_id as delivery_id for idempotency
        # Slack's event_id is globally unique
        delivery = f"slack-{event_id}" if event_id else f"slack-{int(time.time() * 1000)}"
    except Exception:
        # If parsing fails, use a timestamp-based ID
        delivery = f"slack-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(
                EventRaw.source == "slack", EventRaw.delivery_id == delivery
            )
        ).scalar_one_or_none()
        if exists:
            return {"status": "ok", "id": exists.id}

    # Signature verification (optional)
    secret = request.app.state.__dict__.get("slack_webhook_secret")
    if secret and x_slack_signature and x_slack_request_timestamp:
        # Slack signature verification
        sig_basestring = f"v0:{x_slack_request_timestamp}:{body.decode('utf-8')}"
        expected = "v0=" + hmac.new(
            secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_slack_signature):
            raise HTTPException(status_code=401, detail="invalid signature")

    # Store event
    evt = EventRaw(
        source="slack",
        event_type=event_type,
        delivery_id=delivery,
        signature=x_slack_signature,
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
                subject="events.slack",
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
