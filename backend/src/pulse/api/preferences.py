from fastapi import APIRouter

from pulse.api.deps import CurrentUser, SessionDep
from pulse.domain import resolve_alerts
from pulse.schemas import Preferences

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("")
async def get_preferences(user: CurrentUser) -> Preferences:
    return Preferences(alerts=resolve_alerts(user.alert_prefs))


@router.put("")
async def update_preferences(
    body: Preferences, session: SessionDep, user: CurrentUser
) -> Preferences:
    merged = resolve_alerts(user.alert_prefs) | body.alerts
    user.alert_prefs = {kind.value: enabled for kind, enabled in merged.items()}
    await session.commit()
    return Preferences(alerts=merged)
