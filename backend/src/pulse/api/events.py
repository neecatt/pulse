from fastapi import APIRouter, Query
from sqlalchemy import select

from pulse.api.deps import CurrentUser, SessionDep
from pulse.models import Event
from pulse.schemas import EventOut
from pulse.services.teams import visible_account_ids

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
async def list_events(
    session: SessionDep,
    user: CurrentUser,
    account_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[EventOut]:
    query = (
        select(Event)
        .where(Event.account_id.in_(visible_account_ids(user.id)))
        .order_by(Event.created_at.desc(), Event.id.desc())
        .limit(limit)
    )
    if account_id is not None:
        query = query.where(Event.account_id == account_id)
    return [EventOut.model_validate(e) for e in await session.scalars(query)]
