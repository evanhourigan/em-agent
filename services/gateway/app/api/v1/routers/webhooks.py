import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ....core.config import get_settings
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

    # Send Slack notification for deployment workflow completions
    if x_github_event == "workflow_run":
        try:
            import json
            from datetime import datetime

            from ...services.slack_client import SlackClient

            payload_json = json.loads(body)
            action = payload_json.get("action")
            workflow_run = payload_json.get("workflow_run", {})

            # Only notify on completed workflows
            if action == "completed":
                workflow_name = workflow_run.get("name", "Unknown Workflow")
                conclusion = workflow_run.get("conclusion", "unknown")

                # Filter for deployment workflows
                if "deploy" in workflow_name.lower() or "production" in workflow_name.lower():
                    repo = payload_json.get("repository", {})
                    repo_name = repo.get("full_name", "unknown")

                    # Calculate duration
                    duration_seconds = None
                    created_at_str = workflow_run.get("created_at")
                    updated_at_str = workflow_run.get("updated_at")
                    if created_at_str and updated_at_str:
                        try:
                            created_at = datetime.fromisoformat(
                                created_at_str.replace("Z", "+00:00")
                            )
                            updated_at = datetime.fromisoformat(
                                updated_at_str.replace("Z", "+00:00")
                            )
                            duration_seconds = int((updated_at - created_at).total_seconds())
                        except Exception:
                            pass

                    # Get workflow URL
                    workflow_url = workflow_run.get("html_url")

                    # Send notification (async, don't block webhook response)
                    slack_client = SlackClient()
                    asyncio.create_task(
                        asyncio.to_thread(
                            slack_client.post_deployment_notification,
                            workflow_name=workflow_name,
                            conclusion=conclusion,
                            repo_name=repo_name,
                            duration_seconds=duration_seconds,
                            workflow_url=workflow_url,
                        )
                    )
        except Exception:
            # Don't fail webhook if Slack notification fails
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
            select(EventRaw).where(EventRaw.source == "shortcut", EventRaw.delivery_id == delivery)
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
            select(EventRaw).where(EventRaw.source == "linear", EventRaw.delivery_id == delivery)
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
            select(EventRaw).where(EventRaw.source == "pagerduty", EventRaw.delivery_id == delivery)
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
            select(EventRaw).where(EventRaw.source == "slack", EventRaw.delivery_id == delivery)
        ).scalar_one_or_none()
        if exists:
            return {"status": "ok", "id": exists.id}

    # Signature verification (optional)
    secret = request.app.state.__dict__.get("slack_webhook_secret")
    if secret and x_slack_signature and x_slack_request_timestamp:
        # Slack signature verification
        sig_basestring = f"v0:{x_slack_request_timestamp}:{body.decode('utf-8')}"
        expected = (
            "v0="
            + hmac.new(
                secret.encode("utf-8"), sig_basestring.encode("utf-8"), hashlib.sha256
            ).hexdigest()
        )
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


@router.post("/datadog")
async def datadog_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
) -> dict:
    """
    Datadog webhook handler for monitors, events, and metrics.

    Supports:
    - Monitor alerts (triggered, recovered, no data)
    - Events (deployments, config changes, incidents)
    - Custom webhooks
    - APM trace alerts

    See: https://docs.datadoghq.com/integrations/webhooks/
    """
    settings = get_settings()
    if not settings.integrations_datadog_enabled:
        raise HTTPException(status_code=503, detail="Datadog integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # Datadog sends different structures for monitors vs events
        # Monitor alerts have 'alert_id', events have 'event_id'
        event_id = (
            payload_json.get("id") or payload_json.get("alert_id") or payload_json.get("event_id")
        )
        event_type = payload_json.get("event_type", "alert")  # alert, event, metric, etc.

        # Extract alert/monitor info if present
        if "alert_type" in payload_json:
            event_type = (
                f"monitor_{payload_json['alert_type']}"  # e.g., monitor_error, monitor_warning
            )

        # Use event_id or timestamp for delivery_id
        delivery = f"datadog-{event_id}" if event_id else f"datadog-{int(time.time() * 1000)}"
    except Exception:
        delivery = f"datadog-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(EventRaw.source == "datadog", EventRaw.delivery_id == delivery)
        ).scalar_one_or_none()
        if exists:
            return {"status": "ok", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="datadog",
        event_type=event_type,
        delivery_id=delivery,
        signature=None,  # Datadog doesn't use signature verification
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
                subject="events.datadog",
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


@router.post("/sentry")
async def sentry_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    sentry_hook_resource: str | None = Header(None, alias="Sentry-Hook-Resource"),
) -> dict:
    """
    Sentry webhook handler for errors, issues, and releases.

    Supports:
    - issue.created
    - issue.resolved
    - issue.assigned
    - issue.ignored
    - event.alert
    - event.created

    See: https://docs.sentry.io/product/integrations/integration-platform/webhooks/
    """
    settings = get_settings()
    if not settings.integrations_sentry_enabled:
        raise HTTPException(status_code=503, detail="Sentry integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # Sentry webhook format
        action = payload_json.get("action", "unknown")  # e.g., created, resolved, assigned
        resource = sentry_hook_resource or "unknown"  # issue, event, installation

        # Extract issue/event ID for idempotency
        data = payload_json.get("data", {})
        issue_id = data.get("issue", {}).get("id") if isinstance(data.get("issue"), dict) else None
        event_id = (
            data.get("event", {}).get("event_id") if isinstance(data.get("event"), dict) else None
        )

        # Construct event type
        event_type = f"{resource}.{action}"  # e.g., issue.created, event.alert

        # Use issue_id or event_id for delivery_id
        unique_id = issue_id or event_id or int(time.time() * 1000)
        delivery = f"sentry-{resource}-{unique_id}"
    except Exception:
        delivery = f"sentry-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(EventRaw.source == "sentry", EventRaw.delivery_id == delivery)
        ).scalar_one_or_none()
        if exists:
            return {"status": "ok", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="sentry",
        event_type=event_type,
        delivery_id=delivery,
        signature=None,  # Sentry uses separate signature header if needed
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
                subject="events.sentry",
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


@router.post("/circleci")
async def circleci_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    circleci_signature: str | None = Header(None, alias="Circleci-Signature"),
) -> dict:
    """
    CircleCI webhook handler for pipeline and workflow events.

    Supports:
    - workflow-completed: Pipeline workflow completion
    - job-completed: Individual job completion
    - ping: Webhook verification

    See: https://circleci.com/docs/webhooks/
    """
    settings = get_settings()
    if not settings.integrations_circleci_enabled:
        raise HTTPException(status_code=503, detail="CircleCI integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # CircleCI webhook format
        event_type = payload_json.get("type", "unknown")  # workflow-completed, job-completed, ping

        # Handle ping events
        if event_type == "ping":
            return {"status": "ok", "message": "pong"}

        # Extract workflow/job info
        workflow = payload_json.get("workflow", {})
        pipeline = payload_json.get("pipeline", {})

        workflow_id = workflow.get("id") or pipeline.get("id")

        # Use workflow_id for delivery_id
        delivery = (
            f"circleci-{workflow_id}" if workflow_id else f"circleci-{int(time.time() * 1000)}"
        )
    except Exception:
        delivery = f"circleci-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(EventRaw.source == "circleci", EventRaw.delivery_id == delivery)
        ).scalar_one_or_none()
        if exists:
            return {"status": "ok", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="circleci",
        event_type=event_type,
        delivery_id=delivery,
        signature=circleci_signature,
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
                subject="events.circleci",
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


@router.post("/jenkins")
async def jenkins_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
) -> dict:
    """
    Jenkins webhook handler for build and job events.

    Supports:
    - Build completion events
    - Job status updates
    - Pipeline events

    See: https://plugins.jenkins.io/generic-webhook-trigger/
    """
    settings = get_settings()
    if not settings.integrations_jenkins_enabled:
        raise HTTPException(status_code=503, detail="Jenkins integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # Jenkins webhook format (varies by plugin)
        # Common fields: build, name, url, status, result
        build_info = payload_json.get("build", {})
        build_number = build_info.get("number") or payload_json.get("number")
        job_name = payload_json.get("name") or build_info.get("full_url", "").split("/")[-2]

        # Event type based on status/result
        result = payload_json.get("result") or build_info.get("status", "unknown")
        event_type = f"build_{result.lower()}" if result else "build_unknown"

        # Use job_name + build_number for delivery_id
        if job_name and build_number:
            delivery = f"jenkins-{job_name}-{build_number}"
        else:
            delivery = f"jenkins-{int(time.time() * 1000)}"
    except Exception:
        delivery = f"jenkins-{int(time.time() * 1000)}"
        event_type = "build_unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(EventRaw.source == "jenkins", EventRaw.delivery_id == delivery)
        ).scalar_one_or_none()
        if exists:
            return {"status": "ok", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="jenkins",
        event_type=event_type,
        delivery_id=delivery,
        signature=None,
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
                subject="events.jenkins",
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


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    x_gitlab_event: str | None = Header(None, alias="X-Gitlab-Event"),
    x_gitlab_token: str | None = Header(None, alias="X-Gitlab-Token"),
) -> dict:
    """
    GitLab webhook handler for pipeline, job, and deployment events.

    Supports:
    - Pipeline Hook: Pipeline status events
    - Job Hook: Job completion events
    - Deployment Hook: Deployment events
    - Push Hook: Code push events
    - Merge Request Hook: MR events

    See: https://docs.gitlab.com/ee/user/project/integrations/webhooks.html
    """
    settings = get_settings()
    if not settings.integrations_gitlab_enabled:
        raise HTTPException(status_code=503, detail="GitLab integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # GitLab webhook format
        object_kind = payload_json.get(
            "object_kind", "unknown"
        )  # pipeline, build, deployment, etc.

        # Extract ID based on object kind
        if object_kind == "pipeline":
            event_id = payload_json.get("object_attributes", {}).get("id")
            event_type = (
                f"pipeline_{payload_json.get('object_attributes', {}).get('status', 'unknown')}"
            )
        elif object_kind == "build":
            event_id = payload_json.get("build_id")
            event_type = f"job_{payload_json.get('build_status', 'unknown')}"
        elif object_kind == "deployment":
            event_id = payload_json.get("deployment_id")
            event_type = f"deployment_{payload_json.get('status', 'unknown')}"
        else:
            event_id = payload_json.get("id") or payload_json.get("object_attributes", {}).get("id")
            event_type = object_kind

        # Use event_id for delivery_id
        delivery = f"gitlab-{event_id}" if event_id else f"gitlab-{int(time.time() * 1000)}"
    except Exception:
        delivery = f"gitlab-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(EventRaw.source == "gitlab", EventRaw.delivery_id == delivery)
        ).scalar_one_or_none()
        if exists:
            return {"status": "ok", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="gitlab",
        event_type=event_type,
        delivery_id=delivery,
        signature=None,
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
                subject="events.gitlab",
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


@router.post("/kubernetes")
async def kubernetes_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
) -> dict:
    """
    Kubernetes webhook handler for pod and deployment events.

    Supports:
    - Deployment events (created, updated, deleted)
    - Pod events (running, succeeded, failed)
    - ReplicaSet events
    - Service events

    Can be configured as Kubernetes admission webhook or event handler.
    See: https://kubernetes.io/docs/reference/access-authn-authz/webhook/
    """
    settings = get_settings()
    if not settings.integrations_kubernetes_enabled:
        raise HTTPException(status_code=503, detail="Kubernetes integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # Kubernetes event format
        # Can be admission review or event object
        kind = payload_json.get("kind", "unknown")

        if kind == "AdmissionReview":
            # Admission webhook format
            req = payload_json.get("request", {})
            obj = req.get("object", {})
            event_type = (
                f"{req.get('operation', 'unknown').lower()}_{obj.get('kind', 'unknown').lower()}"
            )
            event_id = req.get("uid")
        else:
            # Event object format
            obj = payload_json.get("object", {}) or payload_json
            metadata = obj.get("metadata", {})
            event_type = f"{payload_json.get('type', 'unknown').lower()}_{obj.get('kind', 'unknown').lower()}"
            event_id = metadata.get("uid") or metadata.get("name")

        # Use event_id for delivery_id
        delivery = f"k8s-{event_id}" if event_id else f"k8s-{int(time.time() * 1000)}"
    except Exception:
        delivery = f"k8s-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(
                EventRaw.source == "kubernetes", EventRaw.delivery_id == delivery
            )
        ).scalar_one_or_none()
        if exists:
            return {"status": "ok", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="kubernetes",
        event_type=event_type,
        delivery_id=delivery,
        signature=None,
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
                subject="events.kubernetes",
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


@router.post("/argocd")
async def argocd_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
) -> dict:
    """
    ArgoCD webhook handler for GitOps deployment events.

    Supports:
    - Application sync events (Synced, OutOfSync, Degraded)
    - Deployment status changes
    - Health status updates
    - Rollback events

    See: https://argo-cd.readthedocs.io/en/stable/operator-manual/notifications/
    """
    settings = get_settings()
    if not settings.integrations_argocd_enabled:
        raise HTTPException(status_code=503, detail="ArgoCD integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # ArgoCD notification format
        app = payload_json.get("app", {}) or payload_json.get("application", {})
        app_name = app.get("metadata", {}).get("name") or app.get("name")

        # Event type from sync status
        status = app.get("status", {})
        sync_status = status.get("sync", {}).get("status", "unknown")

        event_type = f"sync_{sync_status.lower()}"

        # Use app name + timestamp for delivery_id (ArgoCD doesn't have unique event IDs)
        delivery = f"argocd-{app_name}-{int(time.time() * 1000)}"
    except Exception:
        delivery = f"argocd-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Store event (no idempotency check since ArgoCD sends updates for same app)
    evt = EventRaw(
        source="argocd",
        event_type=event_type,
        delivery_id=delivery,
        signature=None,
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
                subject="events.argocd",
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


@router.post("/ecs")
async def ecs_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
) -> dict:
    """
    AWS ECS webhook handler for container deployment events.

    Supports ECS events via EventBridge:
    - Task state changes (RUNNING, STOPPED)
    - Service deployment events
    - Container instance state changes

    See: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_eventbridge.html
    """
    settings = get_settings()
    if not settings.integrations_ecs_enabled:
        raise HTTPException(status_code=503, detail="ECS integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # AWS EventBridge format
        detail_type = payload_json.get("detail-type", "unknown")
        detail = payload_json.get("detail", {})

        # Extract event info
        if "ECS Task State Change" in detail_type:
            task_arn = detail.get("taskArn", "")
            last_status = detail.get("lastStatus", "unknown")
            event_type = f"task_{last_status.lower()}"
            event_id = task_arn.split("/")[-1] if task_arn else None
        elif "ECS Service Action" in detail_type or "ECS Deployment State Change" in detail_type:
            event_type = detail.get("eventName", "deployment").lower()
            event_id = detail.get("deploymentId") or payload_json.get("id")
        else:
            event_type = detail_type.replace(" ", "_").lower()
            event_id = payload_json.get("id")

        # Use event_id for delivery_id
        delivery = f"ecs-{event_id}" if event_id else f"ecs-{int(time.time() * 1000)}"
    except Exception:
        delivery = f"ecs-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(EventRaw.source == "ecs", EventRaw.delivery_id == delivery)
        ).scalar_one_or_none()
        if exists:
            return {"status": "ok", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="ecs",
        event_type=event_type,
        delivery_id=delivery,
        signature=None,
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
                subject="events.ecs",
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


@router.post("/heroku")
async def heroku_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    heroku_webhook_id: str | None = Header(None, alias="Heroku-Webhook-Id"),
) -> dict:
    """
    Heroku webhook handler for app deployment events.

    Supports:
    - App deployment events (succeeded, failed)
    - Release events (created, updated)
    - Dyno state changes
    - Build events

    See: https://devcenter.heroku.com/articles/app-webhooks
    """
    settings = get_settings()
    if not settings.integrations_heroku_enabled:
        raise HTTPException(status_code=503, detail="Heroku integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # Heroku webhook format
        action = payload_json.get("action", "unknown")  # create, update, destroy
        resource = payload_json.get("resource", "unknown")  # release, build, dyno, etc.

        data = payload_json.get("data", {})
        event_id = data.get("id") or heroku_webhook_id

        event_type = f"{resource}_{action}"

        # Use event_id or webhook_id for delivery_id
        delivery = f"heroku-{event_id}" if event_id else f"heroku-{int(time.time() * 1000)}"
    except Exception:
        delivery = (
            f"heroku-{heroku_webhook_id}"
            if heroku_webhook_id
            else f"heroku-{int(time.time() * 1000)}"
        )
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(EventRaw.source == "heroku", EventRaw.delivery_id == delivery)
        ).scalar_one_or_none()
        if exists:
            return {"status": "ok", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="heroku",
        event_type=event_type,
        delivery_id=delivery,
        signature=None,
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
                subject="events.heroku",
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


@router.post("/codecov")
async def codecov_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
) -> dict:
    """
    Codecov webhook handler for code coverage events.

    Supports:
    - Coverage upload events
    - Coverage change notifications
    - Status check updates
    - Pull request coverage reports

    See: https://docs.codecov.com/docs/notifications#webhooks
    """
    settings = get_settings()
    if not settings.integrations_codecov_enabled:
        raise HTTPException(status_code=503, detail="Codecov integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # Codecov webhook format
        event_type = payload_json.get("event", "unknown")  # coverage, status, etc.

        # Extract coverage info
        commit = payload_json.get("commit", {})

        commit_sha = commit.get("commitid") or commit.get("sha")

        # Use commit_sha for delivery_id
        delivery = (
            f"codecov-{commit_sha}-{event_type}"
            if commit_sha
            else f"codecov-{int(time.time() * 1000)}"
        )
    except Exception:
        delivery = f"codecov-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(EventRaw.source == "codecov", EventRaw.delivery_id == delivery)
        ).scalar_one_or_none()
        if exists:
            return {"status": "ok", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="codecov",
        event_type=event_type,
        delivery_id=delivery,
        signature=None,
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
                subject="events.codecov",
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


@router.post("/sonarqube")
async def sonarqube_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    x_sonar_webhook_hmac: str | None = Header(None, alias="X-Sonar-Webhook-HMAC-SHA256"),
) -> dict:
    """
    SonarQube webhook handler for code quality events.

    Supports:
    - Quality Gate status changes
    - Analysis completion events
    - Issue creation/resolution
    - Security hotspot updates

    See: https://docs.sonarqube.org/latest/project-administration/webhooks/
    """
    settings = get_settings()
    if not settings.integrations_sonarqube_enabled:
        raise HTTPException(status_code=503, detail="SonarQube integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # SonarQube webhook format
        project = payload_json.get("project", {})
        quality_gate = payload_json.get("qualityGate", {})

        project_key = project.get("key")
        qg_status = quality_gate.get("status", "unknown")  # OK, ERROR, WARN

        # Event type based on quality gate status
        event_type = f"quality_gate_{qg_status.lower()}"

        # Extract task info for idempotency
        task_id = (
            payload_json.get("taskId") or payload_json.get("serverUrl", "").split("task?id=")[-1]
        )

        # Use task_id or project_key for delivery_id
        delivery = (
            f"sonarqube-{task_id}"
            if task_id
            else f"sonarqube-{project_key}-{int(time.time() * 1000)}"
        )
    except Exception:
        delivery = f"sonarqube-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(EventRaw.source == "sonarqube", EventRaw.delivery_id == delivery)
        ).scalar_one_or_none()
        if exists:
            return {"status": "ok", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="sonarqube",
        event_type=event_type,
        delivery_id=delivery,
        signature=x_sonar_webhook_hmac,
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
                subject="events.sonarqube",
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


@router.post("/newrelic")
async def newrelic_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
) -> dict:
    """
    New Relic webhook handler for alerts, APM events, and deployment markers.

    Supports:
    - Alert notifications (open, close, acknowledge)
    - APM events (error rate, throughput, response time)
    - Deployment markers
    - Infrastructure alerts
    - Synthetics monitor events

    See: https://docs.newrelic.com/docs/alerts-applied-intelligence/notifications/notification-integrations/
    """
    settings = get_settings()
    if not settings.integrations_newrelic_enabled:
        raise HTTPException(status_code=503, detail="New Relic integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # New Relic sends different formats for different event types
        # Alert notifications have 'condition_name', deployments have 'deployment'
        incident_id = payload_json.get("incident_id") or payload_json.get("current_state", {}).get(
            "incident_id"
        )
        condition_name = payload_json.get("condition_name")

        # Determine event type
        if "deployment" in payload_json:
            event_type = "deployment"
        elif "current_state" in payload_json:
            # Alert notification format
            state = payload_json.get("current_state", {}).get("state", "unknown")
            event_type = f"alert_{state}"  # alert_open, alert_closed, alert_acknowledged
        elif condition_name:
            event_type = "alert"
        else:
            event_type = payload_json.get("event_type", "unknown")

        # Use incident_id or timestamp for delivery_id
        delivery = (
            f"newrelic-{incident_id}" if incident_id else f"newrelic-{int(time.time() * 1000)}"
        )
    except Exception:
        delivery = f"newrelic-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(EventRaw.source == "newrelic", EventRaw.delivery_id == delivery)
        ).scalar_one_or_none()
        if exists:
            return {"status": "duplicate", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="newrelic",
        event_type=event_type,
        delivery_id=delivery,
        signature=None,
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
                subject="events.newrelic",
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


@router.post("/prometheus")
async def prometheus_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
) -> dict:
    """
    Prometheus Alertmanager webhook handler for alerts.

    Supports:
    - Alert notifications (firing, resolved)
    - Grouped alerts from Alertmanager
    - Custom alert labels and annotations

    Expected format: Prometheus Alertmanager webhook format
    See: https://prometheus.io/docs/alerting/latest/configuration/#webhook_config
    """
    settings = get_settings()
    if not settings.integrations_prometheus_enabled:
        raise HTTPException(status_code=503, detail="Prometheus integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # Alertmanager webhook format
        # status: "firing" or "resolved"
        status = payload_json.get("status", "unknown")  # firing, resolved
        group_key = payload_json.get("groupKey", "")

        # Event type based on overall status
        event_type = f"alert_{status}"  # alert_firing, alert_resolved

        # Use groupKey + status for delivery_id (alerts can transition states)
        if group_key:
            # Hash the group key to keep delivery_id reasonable length
            import hashlib

            group_hash = hashlib.md5(group_key.encode()).hexdigest()[:12]
            delivery = f"prometheus-{group_hash}-{status}"
        else:
            delivery = f"prometheus-{int(time.time() * 1000)}"
    except Exception:
        delivery = f"prometheus-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(
                EventRaw.source == "prometheus", EventRaw.delivery_id == delivery
            )
        ).scalar_one_or_none()
        if exists:
            return {"status": "duplicate", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="prometheus",
        event_type=event_type,
        delivery_id=delivery,
        signature=None,
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
                subject="events.prometheus",
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


@router.post("/cloudwatch")
async def cloudwatch_webhook(
    request: Request,
    session: Session = Depends(get_db_session),
    x_amz_sns_message_type: str | None = Header(None, alias="x-amz-sns-message-type"),
    x_amz_sns_message_id: str | None = Header(None, alias="x-amz-sns-message-id"),
) -> dict:
    """
    AWS CloudWatch webhook handler via SNS.

    Supports:
    - CloudWatch Alarm notifications (ALARM, OK, INSUFFICIENT_DATA)
    - EventBridge events via SNS
    - SNS subscription confirmation

    CloudWatch alarms are typically delivered via SNS topics.
    See: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html
    """
    settings = get_settings()
    if not settings.integrations_cloudwatch_enabled:
        raise HTTPException(status_code=503, detail="CloudWatch integration is disabled")

    body = await request.body()

    # Parse payload to extract event info
    import json
    import time

    try:
        payload_json = json.loads(body)

        # Handle SNS subscription confirmation
        if x_amz_sns_message_type == "SubscriptionConfirmation":
            # Return the subscribe URL for manual confirmation
            # In production, you might auto-confirm by fetching the SubscribeURL
            subscribe_url = payload_json.get("SubscribeURL", "")
            return {
                "status": "subscription_confirmation_required",
                "subscribe_url": subscribe_url,
                "message": "Please confirm the SNS subscription by visiting the SubscribeURL",
            }

        # SNS wraps the actual message in a "Message" field (as string)
        message_str = payload_json.get("Message", "{}")
        if isinstance(message_str, str):
            try:
                message = json.loads(message_str)
            except json.JSONDecodeError:
                message = {"raw": message_str}
        else:
            message = message_str

        # CloudWatch Alarm format
        alarm_name = message.get("AlarmName")
        new_state = message.get("NewStateValue", "unknown")  # ALARM, OK, INSUFFICIENT_DATA

        # EventBridge format
        detail_type = message.get("detail-type")

        # Determine event type
        if alarm_name:
            event_type = (
                f"alarm_{new_state.lower()}"  # alarm_alarm, alarm_ok, alarm_insufficient_data
            )
        elif detail_type:
            # EventBridge event
            event_type = f"eventbridge_{detail_type.lower().replace(' ', '_')}"
        else:
            event_type = "unknown"

        # Use SNS message ID or alarm name + state for delivery_id
        if x_amz_sns_message_id:
            delivery = f"cloudwatch-{x_amz_sns_message_id}"
        elif alarm_name:
            delivery = f"cloudwatch-{alarm_name}-{new_state}-{int(time.time())}"
        else:
            delivery = f"cloudwatch-{int(time.time() * 1000)}"
    except Exception:
        delivery = f"cloudwatch-{int(time.time() * 1000)}"
        event_type = "unknown"

    # Idempotency check
    if delivery:
        exists = session.execute(
            select(EventRaw).where(
                EventRaw.source == "cloudwatch", EventRaw.delivery_id == delivery
            )
        ).scalar_one_or_none()
        if exists:
            return {"status": "duplicate", "id": exists.id}

    # Store event
    evt = EventRaw(
        source="cloudwatch",
        event_type=event_type,
        delivery_id=delivery,
        signature=None,
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
                subject="events.cloudwatch",
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
