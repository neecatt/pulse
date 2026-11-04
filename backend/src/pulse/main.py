import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from pulse import __version__
from pulse.api import api_router
from pulse.config import Settings, get_settings
from pulse.db import create_engine, create_session_factory, init_db
from pulse.domain import Clock
from pulse.models import User, utcnow
from pulse.services.broadcaster import Broadcaster
from pulse.services.container import Services
from pulse.services.notifier import Notifier
from pulse.services.poller import Poller
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
        await _ensure_default_user(sessions, settings.default_user_email)

        slurm = slurm_client or create_slurm_client(settings)
        notifier = Notifier(settings)
        broadcaster = Broadcaster()
        poller = Poller(sessions, slurm, notifier, broadcaster, settings, clock)
        app.state.services = Services(settings, sessions, slurm, notifier, broadcaster, poller)

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


async def _ensure_default_user(sessions: async_sessionmaker[AsyncSession], email: str) -> None:
    async with sessions() as session:
        if await session.scalar(select(User.id).where(User.email == email)) is None:
            session.add(User(email=email))
            await session.commit()
