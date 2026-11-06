from fastapi import APIRouter, HTTPException, status

from pulse.api.deps import CurrentUser, ServicesDep, SessionDep
from pulse.schemas import SiteStats
from pulse.services.stats import site_stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
async def get_site_stats(
    session: SessionDep, user: CurrentUser, services: ServicesDep
) -> SiteStats:
    """Visitors, demos, sign-ups and active users, for admins."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return await site_stats(session, services.clock())
