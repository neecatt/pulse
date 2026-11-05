"""The VAPID key pair Web Push messages are signed with.

Set in the environment, or generated on first start and kept in data_dir so it
survives restarts: browsers bind each subscription to the public key, so a new
pair would silently stop notifications on every device.
"""

import base64
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01

from pulse.config import Settings
from pulse.constants import VAPID_KEYS_FILE

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PushKeys:
    public_key: str  # base64url, uncompressed P-256 point (what browsers need)
    private_key: str  # base64url, raw 32-byte scalar (what pywebpush signs with)


def generate_push_keys() -> PushKeys:
    vapid = Vapid01()
    vapid.generate_keys()
    private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    public = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return PushKeys(public_key=_b64url(public), private_key=_b64url(private))


def load_push_keys(settings: Settings) -> PushKeys:
    """Keys from the environment if set, else from data_dir (created on first use)."""
    public, private = settings.vapid_public_key, settings.vapid_private_key
    if public and private:
        return PushKeys(public_key=public, private_key=private)
    if public or private:
        raise RuntimeError(
            "Set both PULSE_VAPID_PUBLIC_KEY and PULSE_VAPID_PRIVATE_KEY, "
            "or neither to let Pulse generate them."
        )
    path = settings.data_dir / VAPID_KEYS_FILE
    if path.exists():
        stored = json.loads(path.read_text())
        return PushKeys(public_key=stored["public_key"], private_key=stored["private_key"])
    keys = generate_push_keys()
    _write_private(
        path, json.dumps({"public_key": keys.public_key, "private_key": keys.private_key})
    )
    logger.info("generated Web Push keys in %s", path)
    return keys


def _write_private(path: Path, text: str) -> None:
    """Write a file only Pulse's user can read, without a moment where others could."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(text)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
