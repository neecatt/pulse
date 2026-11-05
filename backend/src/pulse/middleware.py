"""ASGI middleware. Plain ASGI rather than BaseHTTPMiddleware, which interferes
with streaming responses such as the live update stream."""

import json
import logging
from urllib.parse import urlsplit

from fastapi import HTTPException, status
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pulse.constants import CONTENT_SECURITY_POLICY, HSTS_MAX_AGE_SECONDS

logger = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_PROXY_HINT = (
    "Pulse sees plain HTTP but the browser is on HTTPS: it's behind a proxy whose "
    "X-Forwarded-Proto header isn't trusted. Set PULSE_TRUSTED_PROXIES (e.g. * when "
    "the proxy is the only way in)."
)


class SecurityHeadersMiddleware:
    """Hardening headers on every response; HSTS only when served over HTTPS."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        https = scope.get("scheme") == "https"

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
                if https:
                    headers.setdefault(
                        "Strict-Transport-Security", f"max-age={HSTS_MAX_AGE_SECONDS}"
                    )
            await send(message)

        await self._app(scope, receive, send_with_headers)


class RequestTooLarge(HTTPException):
    def __init__(self, limit: int) -> None:
        super().__init__(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Request body is larger than {limit // 1024} KB.",
        )


class BodySizeLimitMiddleware:
    """Refuse request bodies over a size limit, before the app buffers them.

    A declared Content-Length over the limit is rejected straight away; bodies
    without one (chunked) are counted as they arrive and cut off at the limit.
    """

    def __init__(self, app: ASGIApp, default_limit: int, limits: dict[str, int]) -> None:
        self._app = app
        self._default = default_limit
        self._limits = limits

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        limit = self._limits.get(scope["path"], self._default)
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            await _json_response(send, 413, RequestTooLarge(limit).detail)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestTooLarge(limit)  # FastAPI turns this into a 413
            return message

        await self._app(scope, limited_receive, send)


class OriginCheckMiddleware:
    """Reject state-changing requests sent from other websites (CSRF).

    Browsers always send an Origin header on cross-site POST/PUT/PATCH/DELETE, so
    such requests must come from this site or a configured CORS origin. Requests
    without Origin (curl, the login-node agent) are unaffected; they can't carry
    a victim's cookies anyway.
    """

    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        self._app = app
        self._allowed = {o.rstrip("/") for o in allowed_origins}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS:
            headers = dict(scope["headers"])
            origin = headers.get(b"origin", b"").decode()
            own = _own_origin(scope, headers)
            if origin and origin != own and origin not in self._allowed:
                behind_untrusted_proxy = _same_host_upgraded(origin, own)
                if behind_untrusted_proxy:
                    logger.warning(_PROXY_HINT)
                await _forbidden(send, hint=_PROXY_HINT if behind_untrusted_proxy else None)
                return
        await self._app(scope, receive, send)


def _same_host_upgraded(origin: str, own: str) -> bool:
    """The browser is on https:// for the very host Pulse thinks is http://."""
    browser, server = urlsplit(origin), urlsplit(own)
    return (
        browser.scheme == "https"
        and server.scheme == "http"
        and browser.hostname == server.hostname
    )


def _own_origin(scope: Scope, headers: dict[bytes, bytes]) -> str:
    host = headers.get(b"host", b"").decode()
    return f"{scope.get('scheme', 'http')}://{host}"


async def _forbidden(send: Send, hint: str | None = None) -> None:
    detail = "Cross-site request blocked." + (f" {hint}" if hint else "")
    await _json_response(send, 403, detail)


async def _json_response(send: Send, status_code: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})
