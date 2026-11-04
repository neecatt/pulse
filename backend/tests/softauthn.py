"""A minimal software passkey (WebAuthn authenticator) for tests.

It does what a phone or laptop does when creating and using a passkey: makes a
P-256 key pair, then signs the server's challenge, producing the same JSON a
browser sends. Attestation format "none", like most real passkeys.
"""

import base64
import hashlib
import json
import secrets
import struct
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

_UP, _UV, _AT = 0x01, 0x04, 0x40  # user present, user verified, attested data


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64url(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class SoftAuthenticator:
    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.credential_id = secrets.token_bytes(16)
        self._key = ec.generate_private_key(ec.SECP256R1())
        self._user_handle = b""
        self._rp_id = ""
        self._counter = 0

    def create(self, options: dict[str, Any]) -> dict[str, Any]:
        """navigator.credentials.create() for the given creation options."""
        self._rp_id = options["rp"]["id"]
        self._user_handle = unb64url(options["user"]["id"])
        numbers = self._key.public_key().public_numbers()
        cose_key = cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )
        auth_data = (
            hashlib.sha256(self._rp_id.encode()).digest()
            + bytes([_UP | _UV | _AT])
            + struct.pack(">I", 0)
            + bytes(16)  # AAGUID
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + cose_key
        )
        client_data = self._client_data("webauthn.create", options["challenge"])
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "attestationObject": b64url(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
        }

    def get(self, options: dict[str, Any], *, origin: str | None = None) -> dict[str, Any]:
        """navigator.credentials.get() for the given request options."""
        self._counter += 1
        auth_data = (
            hashlib.sha256(options.get("rpId", self._rp_id).encode()).digest()
            + bytes([_UP | _UV])
            + struct.pack(">I", self._counter)
        )
        client_data = self._client_data("webauthn.get", options["challenge"], origin)
        signature = self._key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(signature),
                "userHandle": b64url(self._user_handle),
            },
            "clientExtensionResults": {},
        }

    def _client_data(self, kind: str, challenge: str, origin: str | None = None) -> bytes:
        return json.dumps(
            {
                "type": kind,
                "challenge": challenge,
                "origin": origin or self.origin,
                "crossOrigin": False,
            }
        ).encode()
