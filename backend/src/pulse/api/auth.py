import hmac

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from pulse.api.deps import CurrentUser, ServicesDep, SessionDep
from pulse.auth.passwords import hash_password, verify_password
from pulse.config import Settings
from pulse.constants import SESSION_COOKIE
from pulse.models import LoginSession, User
from pulse.schemas import (
    AuthStatus,
    Credentials,
    Login,
    LoginSessionOut,
    Me,
    PasswordChange,
    Setup,
)
from pulse.services.auth import (
    authenticate,
    resolve_session,
    revoke_sessions,
    start_session,
    user_count,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status")
async def auth_status(request: Request, session: SessionDep, services: ServicesDep) -> AuthStatus:
    """Always 200, so a signed-out browser learns what to show without an error."""
    token = request.cookies.get(SESSION_COOKIE)
    resolved = await resolve_session(session, token, services.settings) if token else None
    return AuthStatus(
        setup_required=await user_count(session) == 0,
        signup_allowed=services.settings.allow_signup,
        user=Me.model_validate(resolved[0]) if resolved else None,
    )


@router.post("/setup", status_code=status.HTTP_201_CREATED)
async def setup(
    body: Setup,
    request: Request,
    response: Response,
    session: SessionDep,
    services: ServicesDep,
) -> Me:
    """Create the first (admin) account, with the setup code from the server log.

    Only works while there are no accounts."""
    if await user_count(session) > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Pulse is already set up; sign in instead.")
    code = services.setup_code
    if code is None or not hmac.compare_digest(_normalise(body.setup_code), _normalise(code)):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Wrong setup code. It's printed in the server log."
        )
    return await _create_and_sign_in(
        body, request, response, session, services.settings, admin=True
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    body: Credentials,
    request: Request,
    response: Response,
    session: SessionDep,
    services: ServicesDep,
) -> Me:
    if not services.settings.allow_signup:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sign-ups are disabled on this server.")
    if await session.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is taken.")
    return await _create_and_sign_in(
        body, request, response, session, services.settings, admin=False
    )


@router.post("/login")
async def login(
    body: Login,
    request: Request,
    response: Response,
    session: SessionDep,
    services: ServicesDep,
) -> Me:
    limiter = services.login_limiter
    keys = (f"ip:{_client_address(request)}", f"user:{body.username.strip().lower()}")
    if limiter.blocked(*keys):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed sign-ins. Try again in a few minutes.",
        )
    user = await authenticate(session, body.username.strip(), body.password)
    if user is None:
        limiter.record_failure(*keys)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password.")
    limiter.reset(*keys)
    await _sign_in(user, request, response, session, services.settings)
    return Me.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, session: SessionDep, user: CurrentUser
) -> None:
    current = await session.get(LoginSession, request.state.login_session_id)
    if current is not None:
        await session.delete(current)
        await session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
async def me(user: CurrentUser) -> Me:
    return Me.model_validate(user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange, request: Request, session: SessionDep, user: CurrentUser
) -> None:
    """Change your password and sign out your other devices."""
    if user.password_from_env:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This password is set by PULSE_ADMIN_PASSWORD; change it there and restart Pulse.",
        )
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is wrong.")
    user.password_hash = hash_password(body.new_password)
    await revoke_sessions(session, user.id, keep=request.state.login_session_id)
    await session.commit()


@router.get("/sessions")
async def list_sessions(
    request: Request, session: SessionDep, user: CurrentUser
) -> list[LoginSessionOut]:
    rows = await session.scalars(
        select(LoginSession)
        .where(LoginSession.user_id == user.id)
        .order_by(LoginSession.last_seen_at.desc())
    )
    current = request.state.login_session_id
    return [
        LoginSessionOut.model_validate(r).model_copy(update={"current": r.id == current})
        for r in rows
    ]


@router.post("/sessions/revoke-others", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_other_sessions(request: Request, session: SessionDep, user: CurrentUser) -> None:
    await revoke_sessions(session, user.id, keep=request.state.login_session_id)
    await session.commit()


async def _create_and_sign_in(
    body: Credentials,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: Settings,
    *,
    admin: bool,
) -> Me:
    user = User(username=body.username, password_hash=hash_password(body.password), is_admin=admin)
    session.add(user)
    await session.flush()
    await _sign_in(user, request, response, session, settings)
    return Me.model_validate(user)


async def _sign_in(
    user: User, request: Request, response: Response, session: SessionDep, settings: Settings
) -> None:
    token = await start_session(session, user, settings, request.headers.get("user-agent"))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 86400,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_secure(request, settings),
    )


def _secure(request: Request, settings: Settings) -> bool:
    if settings.secure_cookies == "auto":
        return request.url.scheme == "https"
    return settings.secure_cookies == "always"


def _normalise(code: str) -> str:
    return code.strip().upper().replace("-", "").replace(" ", "")


def _client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"
