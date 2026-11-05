from fastapi import APIRouter, Header, status
from sqlalchemy import delete, select

from pulse.api.deps import CurrentUser, ServicesDep, SessionDep
from pulse.models import PushSubscription
from pulse.schemas import PushConfig, PushSubscriptionIn, PushTestResult, PushUnsubscribe

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/config")
async def push_config(services: ServicesDep) -> PushConfig:
    return PushConfig(public_key=services.notifier.public_key)


@router.post("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe(
    body: PushSubscriptionIn,
    session: SessionDep,
    user: CurrentUser,
    user_agent: str | None = Header(default=None),
) -> None:
    existing = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    sub = existing or PushSubscription(endpoint=body.endpoint)
    sub.user_id = user.id
    sub.p256dh = body.keys.p256dh
    sub.auth = body.keys.auth
    sub.user_agent = user_agent[:255] if user_agent else None
    session.add(sub)
    await session.commit()


@router.delete("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(body: PushUnsubscribe, session: SessionDep, user: CurrentUser) -> None:
    await session.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user.id, PushSubscription.endpoint == body.endpoint
        )
    )
    await session.commit()


@router.post("/test")
async def send_test(
    session: SessionDep, user: CurrentUser, services: ServicesDep
) -> PushTestResult:
    return PushTestResult(delivered=await services.notifier.send_test(session, user.id))
