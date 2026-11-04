"""``pulse`` command-line entry point."""

import argparse
import base64

import uvicorn
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01


def main() -> None:
    parser = argparse.ArgumentParser(prog="pulse")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    commands.add_parser("gen-vapid", help="print a new VAPID key pair for Web Push")

    args = parser.parse_args()
    if args.command == "serve":
        uvicorn.run(
            "pulse.main:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    elif args.command == "gen-vapid":
        _print_vapid_keys()


def _print_vapid_keys() -> None:
    vapid = Vapid01()
    vapid.generate_keys()
    private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    public = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    print(f"PULSE_VAPID_PRIVATE_KEY={_b64url(private)}")
    print(f"PULSE_VAPID_PUBLIC_KEY={_b64url(public)}")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
