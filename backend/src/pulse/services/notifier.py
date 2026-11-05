"""Deliver events to a user's devices via Web Push (VAPID)."""

import asyncio
import json
import logging
from collections.abc import Sequence
from typing import Any

import requests
from pywebpush import WebPushException, webpush
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pulse.config import Settings
from pulse.constants import DEFAULT_VAPID_SUBJECT, PUSH_EXPIRED_STATUSES, PUSH_SERVICE_HOSTS
from pulse.domain import resolve_alerts
from pulse.models import Event, PushSubscription, User
from pulse.net import is_push_endpoint
from pulse.services.push_keys import PushKeys

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, settings: Settings, keys: PushKeys) -> None:
        self._settings = settings
        self._keys = keys
        self._subject = settings.vapid_subject or settings.public_url or DEFAULT_VAPID_SUBJECT
        self._push_hosts = (*PUSH_SERVICE_HOSTS, *settings.push_extra_hosts)
        # Never follow redirects: a push service doesn't send them, and following one
        # could lead the server to an address it was never allowed to reach.
        self._http = requests.Session()
        self._http.max_redirects = 0

    @property
    def public_key(self) -> str:
        return self._keys.public_key

    def accepts(self, endpoint: str) -> bool:
        """Whether Pulse will deliver to this push endpoint (see PUSH_SERVICE_HOSTS)."""
        return is_push_endpoint(endpoint, self._push_hosts)

    async def send_events(
        self,
        session: AsyncSession,
        user_id: int,
        events: Sequence[Event],
        shared_by: str | None = None,
    ) -> None:
        """Push each event the user has alerts enabled for to all their devices.
        ``shared_by`` names the account's owner when it's a teammate's account."""
        if not events:
            return
        user = await self._load_user(session, user_id)
        alerts = resolve_alerts(user.alert_prefs)
        payloads = [_event_payload(e, shared_by) for e in events if alerts[e.kind]]
        await self._fan_out(session, user, payloads)

    async def send_test(self, session: AsyncSession, user_id: int) -> int:
        """Send a test notification; returns the number of devices reached."""
        user = await self._load_user(session, user_id)
        payload = {"title": "Pulse", "body": "Notifications are working.", "url": "/"}
        return await self._fan_out(session, user, [payload])

    async def _fan_out(
        self, session: AsyncSession, user: User, payloads: list[dict[str, Any]]
    ) -> int:
        reached = 0
        for subscription in list(user.push_subscriptions):
            for payload in payloads:
                delivered, expired = await self._deliver(subscription, payload)
                if expired:
                    await session.delete(subscription)
                    break
                reached += delivered
        await session.commit()
        return reached

    async def _deliver(self, sub: PushSubscription, payload: dict[str, Any]) -> tuple[bool, bool]:
        """Returns (delivered, subscription_expired)."""
        if not self.accepts(sub.endpoint):  # stored before endpoints were checked
            logger.warning("dropping push subscription %s to an unsupported host", sub.id)
            return False, True
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=self._keys.private_key,
                # pywebpush mutates the claims dict, so build a fresh one per call.
                vapid_claims={"sub": self._subject},
                ttl=self._settings.push_ttl_seconds,
                timeout=self._settings.push_timeout_seconds,
                requests_session=self._http,
            )
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in PUSH_EXPIRED_STATUSES:
                return False, True
            logger.warning("push to subscription %s failed: %s", sub.id, exc)
            return False, False
        except ValueError as exc:  # keys a browser would never send; it can't ever work
            logger.warning("dropping malformed push subscription %s: %s", sub.id, exc)
            return False, True
        except OSError as exc:  # push service unreachable (requests errors are OSErrors)
            logger.warning("push to subscription %s failed: %s", sub.id, exc)
            return False, False
        return True, False

    @staticmethod
    async def _load_user(session: AsyncSession, user_id: int) -> User:
        # populate_existing: the user may already be in the session without its
        # subscriptions loaded, and async sessions can't lazy-load them later.
        user = await session.get(
            User,
            user_id,
            options=[selectinload(User.push_subscriptions)],
            populate_existing=True,
        )
        if user is None:
            raise LookupError(f"user {user_id} not found")
        return user


def _event_payload(event: Event, shared_by: str | None = None) -> dict[str, Any]:
    account = event.account
    label = f"{account.username}@{account.cluster}"
    return {
        "title": f"{shared_by} · {label}" if shared_by else label,
        "body": event.message,
        "url": f"/jobs/{event.job_id}" if event.job_id else "/",
        "tag": f"job-{event.job_id}" if event.job_id else f"event-{event.id}",
        "kind": event.kind.value,
    }
