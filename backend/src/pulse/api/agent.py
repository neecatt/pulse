from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from pulse.agent import SCRIPT_PATH
from pulse.api.accounts import hash_token
from pulse.api.deps import ServicesDep, SessionDep
from pulse.models import Account, User
from pulse.schemas import AgentReport, AgentReportAck
from pulse.services.agent_reports import snapshot_from_report

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/script", response_class=FileResponse)
async def agent_script() -> FileResponse:
    """The agent users download onto their login node."""
    return FileResponse(SCRIPT_PATH, media_type="text/x-python", filename="pulse-agent.py")


@router.post("/report")
async def agent_report(
    body: AgentReport,
    session: SessionDep,
    services: ServicesDep,
    authorization: Annotated[str, Header()] = "",
) -> AgentReportAck:
    scheme, _, token = authorization.partition(" ")
    account = None
    if scheme.lower() == "bearer" and token:
        account = await session.scalar(
            select(Account).where(
                Account.connection == "agent", Account.agent_token_hash == hash_token(token)
            )
        )
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid agent token")
    user = await session.get(User, account.user_id)
    assert user is not None  # enforced by the foreign key
    next_report_in = services.poller.interval_for(user)
    account_id = account.id
    await session.rollback()  # release the connection before the (separate) ingest

    await services.poller.ingest_and_publish(account_id, snapshot_from_report(body))
    return AgentReportAck(next_report_in=next_report_in)
