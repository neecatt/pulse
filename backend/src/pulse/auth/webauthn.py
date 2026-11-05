"""Passkeys: one-time WebAuthn challenges and the relying party (this site)."""

import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import Request

from pulse.config import Settings
from pulse.constants import PASSKEY_CHALLENGE_TTL_SECONDS, PASSKEY_MAX_PENDING_CHALLENGES


@dataclass(frozen=True, slots=True)
class RelyingParty:
    """The site a passkey belongs to: its domain (rp_id) and full origin."""

    id: str
    origin: str


def relying_party(request: Request, settings: Settings) -> RelyingParty:
    """Taken from PULSE_PUBLIC_URL, or else from the address the browser used.

    Using the request's own address is safe: a passkey only signs for the origin
    the browser is really on, and that origin is checked against this one.
    """
    if settings.public_url:
        url = urlsplit(settings.public_url.rstrip("/"))
        return RelyingParty(id=url.hostname or "", origin=f"{url.scheme}://{url.netloc}")
    host = request.headers.get("host", "")
    return RelyingParty(
        id=urlsplit(f"//{host}").hostname or "", origin=f"{request.url.scheme}://{host}"
    )


@dataclass(frozen=True, slots=True)
class _Pending:
    challenge: bytes
    purpose: str
    user_id: int | None
    expires: float


class ChallengeStore:
    """Short-lived, single-use challenges, in memory (Pulse runs as one instance)."""

    def __init__(
        self,
        ttl_seconds: int = PASSKEY_CHALLENGE_TTL_SECONDS,
        max_pending: int = PASSKEY_MAX_PENDING_CHALLENGES,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_pending = max_pending
        self._pending: dict[str, _Pending] = {}

    def issue(self, challenge: bytes, purpose: str, user_id: int | None = None) -> str:
        self._expire()
        while len(self._pending) >= self._max_pending:  # a flood; the oldest retries
            del self._pending[next(iter(self._pending))]
        challenge_id = secrets.token_urlsafe(16)
        self._pending[challenge_id] = _Pending(
            challenge, purpose, user_id, time.monotonic() + self._ttl
        )
        return challenge_id

    def take(self, challenge_id: str, purpose: str) -> _Pending | None:
        """Return and forget a challenge; None if unknown, expired or for another purpose."""
        self._expire()
        pending = self._pending.pop(challenge_id, None)
        return pending if pending is not None and pending.purpose == purpose else None

    def _expire(self) -> None:
        now = time.monotonic()
        for key in [k for k, v in self._pending.items() if v.expires <= now]:
            del self._pending[key]
