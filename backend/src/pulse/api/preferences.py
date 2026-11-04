from fastapi import APIRouter

from pulse.api.deps import CurrentUser, ServicesDep, SessionDep
from pulse.domain import resolve_alerts
from pulse.models import User
from pulse.schemas import Monitoring, Preferences, PreferencesUpdate

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("")
async def get_preferences(user: CurrentUser, services: ServicesDep) -> Preferences:
    return _preferences(user, services)


@router.patch("")
async def update_preferences(
    body: PreferencesUpdate, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> Preferences:
    alerts = resolve_alerts(user.alert_prefs) | body.alerts
    user.alert_prefs = {kind.value: enabled for kind, enabled in alerts.items()}
    changes = body.monitoring.model_dump(exclude_none=True)
    user.monitoring_prefs = {**user.monitoring_prefs, **changes}
    await session.commit()
    if "live_refresh_seconds" in changes or "idle_refresh_seconds" in changes:
        services.poller.trigger()  # apply the new pace now
    return _preferences(user, services)


def _preferences(user: User, services: ServicesDep) -> Preferences:
    return Preferences(
        alerts=resolve_alerts(user.alert_prefs),
        monitoring=Monitoring.resolve(user.monitoring_prefs, services.settings),
    )
