from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from ..core.config import get_settings
from ..core.logging import get_logger
from ..core.metrics import metrics as global_metrics


class SlackClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._webhook_url: Optional[str] = settings.slack_webhook_url
        self._bot_token: Optional[str] = settings.slack_bot_token
        self._default_channel: Optional[str] = settings.slack_default_channel
        self._logger = get_logger(__name__)
        self._max_daily = int(get_settings().max_daily_slack_posts)

    def _with_retry(self, func):
        try:
            return func()
        except httpx.HTTPError:
            try:
                return func()
            except httpx.HTTPError:
                return func()

    def _inc_metric(self, kind: str, ok: bool) -> None:
        m = global_metrics
        if not m:
            return
        try:
            m["slack_posts_total"].labels(kind=kind, ok=str(ok).lower()).inc()
            if not ok:
                m.get("slack_post_errors_total", None) and m["slack_post_errors_total"].labels(
                    kind=kind
                ).inc()
            # quota counter
            m.get("quota_slack_posts_total", None) and m["quota_slack_posts_total"].inc()
        except Exception:
            pass

    def post_text(self, text: str, channel: Optional[str] = None) -> Dict[str, Any]:
        # Trace span if OTel enabled
        try:
            from opentelemetry import trace  # type: ignore

            span = trace.get_tracer(__name__).start_span("slack.post_text")
            span.set_attribute("channel", channel or self._default_channel or "")
        except Exception:
            span = None
        if not self._webhook_url and not self._bot_token:
            self._logger.info("slack.post.dry_run", text=text)
            out = {"ok": False, "dry_run": True, "text": text}
            if span:
                try:
                    span.end()
                except Exception:
                    pass
            return out

        if self._webhook_url:

            def _call():
                with httpx.Client(timeout=10) as client:
                    resp = client.post(self._webhook_url, json={"text": text})
                    ok = resp.status_code < 300
                    self._inc_metric("text", ok)
                    return {"ok": ok}

            res = self._with_retry(_call)
            if span:
                try:
                    span.end()
                except Exception:
                    pass
            return res

        # Bot token path (chat.postMessage)
        headers = {"Authorization": f"Bearer {self._bot_token}"}
        payload = {"channel": channel or self._default_channel, "text": text}

        def _call_api():
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    "https://slack.com/api/chat.postMessage", headers=headers, json=payload
                )
                data = resp.json()
                ok = bool(data.get("ok"))
                self._inc_metric("text", ok)
                return {"ok": ok, "response": data}

        res = self._with_retry(_call_api)
        if span:
            try:
                span.end()
            except Exception:
                pass
        return res

    def post_blocks(
        self, *, text: str, blocks: list[dict[str, Any]], channel: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            from opentelemetry import trace  # type: ignore

            span = trace.get_tracer(__name__).start_span("slack.post_blocks")
            span.set_attribute("channel", channel or self._default_channel or "")
            span.set_attribute("blocks.count", len(blocks))
        except Exception:
            span = None
        if not self._webhook_url and not self._bot_token:
            self._logger.info("slack.post.dry_run", blocks=len(blocks))
            out = {"ok": False, "dry_run": True, "blocks": blocks}
            if span:
                try:
                    span.end()
                except Exception:
                    pass
            return out

        if self._webhook_url:

            def _call():
                with httpx.Client(timeout=10) as client:
                    resp = client.post(self._webhook_url, json={"text": text, "blocks": blocks})
                    ok = resp.status_code < 300
                    self._inc_metric("blocks", ok)
                    return {"ok": ok}

            res = self._with_retry(_call)
            if span:
                try:
                    span.end()
                except Exception:
                    pass
            return res

        headers = {"Authorization": f"Bearer {self._bot_token}"}
        payload = {"channel": channel or self._default_channel, "text": text, "blocks": blocks}

        def _call_api():
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    "https://slack.com/api/chat.postMessage", headers=headers, json=payload
                )
                data = resp.json()
                ok = bool(data.get("ok"))
                self._inc_metric("blocks", ok)
                return {"ok": ok, "response": data}

        res = self._with_retry(_call_api)
        if span:
            try:
                span.end()
            except Exception:
                pass
        return res
