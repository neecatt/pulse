"""Passkey (WebAuthn) registration and sign-in, alongside passwords."""

import json
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from pulse.api.auth import client_address, issue_session_cookie, limit_signups
from pulse.api.deps import CurrentUser, ServicesDep, SessionDep, require_verified
from pulse.auth.webauthn import relying_party
from pulse.constants import PASSKEY_MAX_PER_USER, PASSKEY_RP_NAME
from pulse.models import LoginSession, Passkey, User, utcnow
from pulse.schemas import (
    Me,
    PasskeyLogin,
    PasskeyOptions,
    PasskeyOut,
    PasskeyRegistration,
    PasskeySignupStart,
)

router = APIRouter(prefix="/auth/passkeys", tags=["auth"])

_REGISTER = "register"
_LOGIN = "login"
_SIGNUP = "signup"
_TAKEN = "That username is taken."


@router.post("/reauth/options")
async def reauth_options(
    request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> PasskeyOptions:
    if user.is_guest:
        raise HTTPException(403, "Demo accounts cannot confirm account changes.")
    passkeys = list(await session.scalars(select(Passkey).where(Passkey.user_id == user.id)))
    if not passkeys:
        raise HTTPException(409, "Add a passkey in Settings or confirm with your password.")
    rp = relying_party(request, services.settings)
    options = generate_authentication_options(
        rp_id=rp.id,
        user_verification=UserVerificationRequirement.REQUIRED,
        allow_credentials=[PublicKeyCredentialDescriptor(id=p.credential_id) for p in passkeys],
    )
    challenge_id = services.passkey_challenges.issue(
        options.challenge, f"reauth:{request.state.login_session_hash}", user.id
    )
    return PasskeyOptions(challenge_id=challenge_id, options=json.loads(options_to_json(options)))


@router.post("/reauth/verify", status_code=204)
async def reauth_verify(
    body: PasskeyLogin,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> None:
    pending = services.passkey_challenges.take(
        body.challenge_id, f"reauth:{request.state.login_session_hash}"
    )
    if pending is None or pending.user_id != user.id:
        raise HTTPException(400, "This confirmation expired. Try again.")
    passkey = await _find_passkey(session, body.credential)
    if passkey is None or passkey.user_id != user.id or user.is_guest:
        raise HTTPException(403, "Use a passkey registered to your Pulse account.")
    rp = relying_party(request, services.settings)
    try:
        verified = verify_authentication_response(
            credential=body.credential,
            expected_challenge=pending.challenge,
            expected_rp_id=rp.id,
            expected_origin=rp.origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as exc:
        raise HTTPException(403, "The passkey couldn't be verified. Try again.") from exc
    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = utcnow()
    login = await session.get(LoginSession, request.state.login_session_id)
    assert login is not None
    login.reauthenticated_at = utcnow()
    await session.commit()


@router.get("")
async def list_passkeys(session: SessionDep, user: CurrentUser) -> list[PasskeyOut]:
    rows = await session.scalars(
        select(Passkey).where(Passkey.user_id == user.id).order_by(Passkey.created_at)
    )
    return [PasskeyOut.model_validate(p) for p in rows]


@router.post("/register/options")
async def registration_options(
    request: Request, session: SessionDep, user: CurrentUser, services: ServicesDep
) -> PasskeyOptions:
    """Start adding a passkey to the signed-in account."""
    if user.is_guest:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Demo accounts are temporary. Create your own account to keep using Pulse.",
        )
    await require_verified(request, session)
    existing = list(await session.scalars(select(Passkey).where(Passkey.user_id == user.id)))
    if len(existing) >= PASSKEY_MAX_PER_USER:
        raise HTTPException(status.HTTP_409_CONFLICT, "You have the maximum number of passkeys.")
    rp = relying_party(request, services.settings)
    options = generate_registration_options(
        rp_id=rp.id,
        rp_name=PASSKEY_RP_NAME,
        user_id=_user_handle(user.id),
        user_name=user.username,
        authenticator_selection=_DISCOVERABLE,
        exclude_credentials=[PublicKeyCredentialDescriptor(id=p.credential_id) for p in existing],
    )
    challenge_id = services.passkey_challenges.issue(
        options.challenge, f"{_REGISTER}:{request.state.login_session_hash}", user.id
    )
    return PasskeyOptions(challenge_id=challenge_id, options=json.loads(options_to_json(options)))


# Discoverable credentials allow signing in without typing a username.
_DISCOVERABLE = AuthenticatorSelectionCriteria(
    resident_key=ResidentKeyRequirement.REQUIRED,
    user_verification=UserVerificationRequirement.PREFERRED,
)


@router.post("/signup/options")
async def signup_options(
    body: PasskeySignupStart, request: Request, session: SessionDep, services: ServicesDep
) -> PasskeyOptions:
    """Start creating an account with a passkey: no password, no email. The account
    only exists once the passkey is verified."""
    if not services.settings.allow_signup:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sign-ups are disabled on this server.")
    limit_signups(request, services)
    if await session.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, _TAKEN)
    rp = relying_party(request, services.settings)
    options = generate_registration_options(
        rp_id=rp.id,
        rp_name=PASSKEY_RP_NAME,
        # No user id exists yet; the handle is opaque, and sign-in finds the
        # account by the credential, not by this.
        user_id=secrets.token_bytes(8),
        user_name=body.username,
        authenticator_selection=_DISCOVERABLE,
    )
    challenge_id = services.passkey_challenges.issue(
        options.challenge, _SIGNUP, username=body.username
    )
    return PasskeyOptions(challenge_id=challenge_id, options=json.loads(options_to_json(options)))


@router.post("/signup/verify", status_code=status.HTTP_201_CREATED)
async def signup(
    body: PasskeyRegistration,
    request: Request,
    response: Response,
    session: SessionDep,
    services: ServicesDep,
) -> Me:
    pending = services.passkey_challenges.take(body.challenge_id, _SIGNUP)
    if pending is None or pending.username is None or not services.settings.allow_signup:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This sign-up expired. Try again.")
    rp = relying_party(request, services.settings)
    try:
        verified = verify_registration_response(
            credential=body.credential,
            expected_challenge=pending.challenge,
            expected_rp_id=rp.id,
            expected_origin=rp.origin,
        )
    except InvalidRegistrationResponse as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The passkey couldn't be verified."
        ) from exc
    if await session.scalar(select(User.id).where(User.username == pending.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, _TAKEN)  # taken in the meantime
    user = User(username=pending.username)
    session.add(user)
    try:
        await session.flush()
        session.add(
            Passkey(
                user_id=user.id,
                credential_id=verified.credential_id,
                public_key=verified.credential_public_key,
                sign_count=verified.sign_count,
                transports=_transports(body.credential),
                name=(body.name or "").strip() or "Passkey",
            )
        )
        await session.flush()
    except IntegrityError as exc:  # same username, or a passkey already registered
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That username or passkey is already in use."
        ) from exc
    await services.site.signup(session, client_address(request))
    await issue_session_cookie(user, request, response, session, services.settings)
    return Me.model_validate(user)


@router.post("/register/verify", status_code=status.HTTP_201_CREATED)
async def register(
    body: PasskeyRegistration,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    services: ServicesDep,
) -> PasskeyOut:
    await require_verified(request, session)
    pending = services.passkey_challenges.take(
        body.challenge_id, f"{_REGISTER}:{request.state.login_session_hash}"
    )
    if pending is None or pending.user_id != user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This request expired. Try again.")
    rp = relying_party(request, services.settings)
    try:
        verified = verify_registration_response(
            credential=body.credential,
            expected_challenge=pending.challenge,
            expected_rp_id=rp.id,
            expected_origin=rp.origin,
        )
    except InvalidRegistrationResponse as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The passkey couldn't be verified."
        ) from exc
    passkey = Passkey(
        user_id=user.id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=_transports(body.credential),
        name=(body.name or "").strip() or "Passkey",
    )
    session.add(passkey)
    await session.commit()
    return PasskeyOut.model_validate(passkey)


@router.delete("/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_passkey(
    passkey_id: int, request: Request, session: SessionDep, user: CurrentUser
) -> None:
    passkey = await session.get(Passkey, passkey_id)
    if passkey is None or passkey.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "passkey not found")
    await require_verified(request, session)
    await session.delete(passkey)
    await session.commit()


@router.post("/login/options")
async def login_options(request: Request, services: ServicesDep) -> PasskeyOptions:
    """Start a passkey sign-in. No username needed: the browser offers its passkeys."""
    rp = relying_party(request, services.settings)
    options = generate_authentication_options(
        rp_id=rp.id, user_verification=UserVerificationRequirement.PREFERRED
    )
    challenge_id = services.passkey_challenges.issue(options.challenge, _LOGIN)
    return PasskeyOptions(challenge_id=challenge_id, options=json.loads(options_to_json(options)))


@router.post("/login/verify")
async def login(
    body: PasskeyLogin,
    request: Request,
    response: Response,
    session: SessionDep,
    services: ServicesDep,
) -> Me:
    pending = services.passkey_challenges.take(body.challenge_id, _LOGIN)
    if pending is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This sign-in expired. Try again.")
    passkey = await _find_passkey(session, body.credential)
    if passkey is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "This passkey isn't registered here. Sign in with your password, then add it.",
        )
    rp = relying_party(request, services.settings)
    try:
        verified = verify_authentication_response(
            credential=body.credential,
            expected_challenge=pending.challenge,
            expected_rp_id=rp.id,
            expected_origin=rp.origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
        )
    except InvalidAuthenticationResponse as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "The passkey couldn't be verified."
        ) from exc
    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = utcnow()
    user = passkey.user
    await issue_session_cookie(user, request, response, session, services.settings)
    return Me.model_validate(user)


async def _find_passkey(session: SessionDep, credential: dict[str, Any]) -> Passkey | None:
    raw_id = credential.get("rawId") or credential.get("id")
    if not isinstance(raw_id, str):
        return None
    try:
        credential_id = base64url_to_bytes(raw_id)
    except (ValueError, TypeError):
        return None
    passkey = await session.scalar(select(Passkey).where(Passkey.credential_id == credential_id))
    if passkey is not None:
        await session.refresh(passkey, ["user"])
    return passkey


def _user_handle(user_id: int) -> bytes:
    """Opaque WebAuthn user handle (no personal data)."""
    return user_id.to_bytes(8, "big")


def _transports(credential: dict[str, Any]) -> list[str]:
    response = credential.get("response")
    raw = response.get("transports", []) if isinstance(response, dict) else []
    known = {t.value for t in AuthenticatorTransport}
    return [t for t in raw if isinstance(t, str) and t in known]
