"""Password hashing with scrypt (Python standard library, no extra dependency)."""

import base64
import hashlib
import hmac
import secrets

from pulse.constants import SCRYPT_N, SCRYPT_P, SCRYPT_R

_SALT_BYTES = 16
_KEY_BYTES = 32
_SCHEME = "scrypt"


def hash_password(password: str) -> str:
    """Return ``scrypt$n$r$p$salt$hash`` (base64url), safe to store."""
    salt = secrets.token_bytes(_SALT_BYTES)
    key = _derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return "$".join([_SCHEME, str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P), _b64(salt), _b64(key)])


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt, key = stored.split("$")
        if scheme != _SCHEME:
            return False
        candidate = _derive(password, _unb64(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, _unb64(key))


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, dklen=_KEY_BYTES, maxmem=2**26
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
