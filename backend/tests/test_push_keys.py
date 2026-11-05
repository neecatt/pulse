"""Web Push keys: from the environment, or generated once and kept in data_dir."""

import base64
import stat
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from pulse.config import Settings
from pulse.services.push_keys import load_push_keys


def _settings(data_dir: Path, **overrides: str) -> Settings:
    return Settings(data_dir=data_dir, _env_file=None, **overrides)  # type: ignore[call-arg, arg-type]


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def test_keys_are_generated_once_and_kept(tmp_path: Path) -> None:
    first = load_push_keys(_settings(tmp_path))
    assert load_push_keys(_settings(tmp_path)) == first  # reused after a restart

    key_file = tmp_path / "vapid.json"
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600  # private key stays private

    # A valid pair: the public key is the private key's point on P-256.
    private = ec.derive_private_key(int.from_bytes(_decode(first.private_key)), ec.SECP256R1())
    public = private.public_key().public_numbers()
    point = _decode(first.public_key)
    assert point[0] == 4 and len(point) == 65
    assert int.from_bytes(point[1:33]) == public.x and int.from_bytes(point[33:]) == public.y


def test_environment_keys_win(tmp_path: Path) -> None:
    keys = load_push_keys(
        _settings(tmp_path, vapid_public_key="public", vapid_private_key="private")
    )
    assert (keys.public_key, keys.private_key) == ("public", "private")
    assert not (tmp_path / "vapid.json").exists()  # nothing generated


def test_half_configured_keys_are_refused(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Set both PULSE_VAPID_PUBLIC_KEY"):
        load_push_keys(_settings(tmp_path, vapid_public_key="public"))
