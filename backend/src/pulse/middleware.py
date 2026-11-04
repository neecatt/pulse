"""ASGI middleware. Plain ASGI rather than BaseHTTPMiddleware, which interferes
with streaming responses such as the live update stream."""

import json

from starlette.types import ASGIApp, Receive, Scope, Send

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


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
            if origin and origin != _own_origin(scope, headers) and origin not in self._allowed:
                await _forbidden(send)
                return
        await self._app(scope, receive, send)


def _own_origin(scope: Scope, headers: dict[bytes, bytes]) -> str:
    host = headers.get(b"host", b"").decode()
    return f"{scope.get('scheme', 'http')}://{host}"


async def _forbidden(send: Send) -> None:
    body = json.dumps({"detail": "Cross-site request blocked."}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})
