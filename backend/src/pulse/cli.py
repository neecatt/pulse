"""``pulse`` command-line entry point."""

import argparse
import asyncio
import contextlib
import getpass
import re
import sys
from collections.abc import AsyncIterator

import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pulse.auth.passwords import hash_password
from pulse.config import get_settings
from pulse.constants import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, USERNAME_PATTERN
from pulse.db import create_engine, create_session_factory, init_db
from pulse.models import User
from pulse.services.auth import revoke_sessions
from pulse.services.push_keys import generate_push_keys


def main() -> None:
    parser = argparse.ArgumentParser(prog="pulse")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the API server")
    serve.add_argument("--host", help="defaults to PULSE_HOST (127.0.0.1)")
    serve.add_argument("--port", type=int, help="defaults to PULSE_PORT (8000)")
    serve.add_argument("--reload", action="store_true", help="restart on code changes (dev)")

    commands.add_parser(
        "gen-vapid", help="print a VAPID key pair (optional: Pulse makes one in data_dir)"
    )

    create = commands.add_parser("create-user", help="add a user (asks for the password)")
    create.add_argument("username")
    create.add_argument("--admin", action="store_true", help="give the user admin rights")

    reset = commands.add_parser(
        "reset-password", help="set a user's password and sign them out everywhere"
    )
    reset.add_argument("username")

    args = parser.parse_args()
    if args.command == "serve":
        settings = get_settings()
        uvicorn.run(
            "pulse.main:create_app",
            factory=True,
            host=args.host or settings.host,
            port=args.port or settings.port,
            reload=args.reload,
            # Behind a reverse proxy: take the client address and https scheme
            # from X-Forwarded-* headers, but only from these proxies.
            proxy_headers=True,
            forwarded_allow_ips=settings.trusted_proxies,
            server_header=False,  # don't advertise the server software
        )
    elif args.command == "gen-vapid":
        _print_vapid_keys()
    elif args.command == "create-user":
        sys.exit(asyncio.run(_create_user(args.username, admin=args.admin)))
    elif args.command == "reset-password":
        sys.exit(asyncio.run(_reset_password(args.username)))


async def _create_user(username: str, *, admin: bool) -> int:
    if not re.fullmatch(USERNAME_PATTERN, username):
        print("Usernames are 3-64 letters, digits, '.', '_' or '-'.", file=sys.stderr)
        return 1
    password = _ask_password()
    async with _db() as session:
        if await session.scalar(select(User.id).where(User.username == username)):
            print(f"User {username!r} already exists.", file=sys.stderr)
            return 1
        session.add(User(username=username, password_hash=hash_password(password), is_admin=admin))
        await session.commit()
    print(f"Created {'admin ' if admin else ''}user {username!r}.")
    return 0


async def _reset_password(username: str) -> int:
    async with _db() as session:
        user = await session.scalar(select(User).where(User.username == username))
        if user is None:
            print(f"No user {username!r}.", file=sys.stderr)
            return 1
        if user.password_from_env:
            print("This password is set by PULSE_ADMIN_PASSWORD; change it there.", file=sys.stderr)
            return 1
        user.password_hash = hash_password(_ask_password())
        await revoke_sessions(session, user.id)
        await session.commit()
    print(f"Password for {username!r} updated; all their sessions were signed out.")
    return 0


def _ask_password() -> str:
    while True:
        password = getpass.getpass("Password: ")
        if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
            print(f"Use at least {PASSWORD_MIN_LENGTH} characters.", file=sys.stderr)
        elif getpass.getpass("Repeat password: ") != password:
            print("Passwords don't match.", file=sys.stderr)
        else:
            return password


@contextlib.asynccontextmanager
async def _db() -> AsyncIterator[AsyncSession]:
    """Database session for CLI commands, creating tables if needed."""
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url)
    try:
        await init_db(engine)
        async with create_session_factory(engine)() as session:
            yield session
    finally:
        await engine.dispose()


def _print_vapid_keys() -> None:
    keys = generate_push_keys()
    print(f"PULSE_VAPID_PRIVATE_KEY={keys.private_key}")
    print(f"PULSE_VAPID_PUBLIC_KEY={keys.public_key}")
