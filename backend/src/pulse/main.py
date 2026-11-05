import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from pulse import __version__
from pulse.api import api_router
from pulse.auth.rate_limit import LoginRateLimiter
from pulse.auth.webauthn import ChallengeStore
from pulse.config import Settings, get_settings
from pulse.constants import AGENT_REPORT_PATH, MAX_AGENT_REPORT_BYTES, MAX_REQUEST_BYTES
from pulse.db import create_engine, create_session_factory, init_db
from pulse.domain import Clock
from pulse.middleware import (
    BodySizeLimitMiddleware,
    OriginCheckMiddleware,
    SecurityHeadersMiddleware,
)
from pulse.models import utcnow
from pulse.services.auth import make_setup_code, sync_admin_from_env
from pulse.services.broadcaster import Broadcaster
from pulse.services.container import Services
from pulse.services.notifier import Notifier
from pulse.services.poller import Poller
from pulse.services.push_keys import load_push_keys
from pulse.slurm import SlurmClient, create_slurm_client


def create_app(
    settings: Settings | None = None,
    *,
    slurm_client: SlurmClient | None = None,
    clock: Clock = utcnow,
    run_poller: bool = True,
) -> FastAPI:
    """App factory. Run with ``uvicorn --factory pulse.main:create_app``."""
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = create_engine(settings.database_url)
        await init_db(engine)
        sessions = create_session_factory(engine)
        await sync_admin_from_env(sessions, settings)

        slurm = slurm_client or create_slurm_client(settings)
        notifier = Notifier(settings, load_push_keys(settings))
        broadcaster = Broadcaster()
        poller = Poller(sessions, slurm, notifier, broadcaster, settings, clock)
        limiter = LoginRateLimiter(settings.login_max_failures, settings.login_window_seconds)
        setup_code = await make_setup_code(sessions)
        app.state.services = Services(
            settings,
            sessions,
            slurm,
            notifier,
            broadcaster,
            poller,
            limiter,
            setup_code,
            ChallengeStore(),
        )

        task = asyncio.create_task(poller.run_forever()) if run_poller else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await slurm.close()
            await engine.dispose()

    app = FastAPI(title="Pulse", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(OriginCheckMiddleware, allowed_origins=settings.cors_origins)
    app.add_middleware(SecurityHeadersMiddleware)
    # Outermost: oversized bodies are refused before any other work.
    app.add_middleware(
        BodySizeLimitMiddleware,
        default_limit=MAX_REQUEST_BYTES,
        limits={AGENT_REPORT_PATH: MAX_AGENT_REPORT_BYTES},
    )
    app.include_router(api_router, prefix="/api")
    if settings.static_dir is not None:
        # Serve the built web app from the same process: one port, one command.
        app.mount("/", SpaStaticFiles(directory=settings.static_dir, html=True), name="web")
    return app


class SpaStaticFiles(StaticFiles):
    """Static files with a fallback to index.html for client-side routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)
