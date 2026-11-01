"""Криптографія AidChain: SHA-256 та ЕЦП Ed25519 (RFC 8032)."""
from __future__ import annotations

import hashlib
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

_RAW = serialization.Encoding.Raw


def sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> str:
    """Детермінована серіалізація: однакові дані -> однакові байти -> однаковий хеш."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def address(public_hex: str) -> str:
    """Адреса учасника: перші 160 біт SHA-256 від публічного ключа."""
    return sha256(bytes.fromhex(public_hex))[:40]


class KeyPair:
    def __init__(self, private_key: Ed25519PrivateKey):
        self._key = private_key

    @classmethod
    def generate(cls) -> "KeyPair":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_hex(cls, private_hex: str) -> "KeyPair":
        return cls(Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex)))

    @property
    def private_hex(self) -> str:
        return self._key.private_bytes(_RAW, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex()

    @property
    def public_hex(self) -> str:
        return self._key.public_key().public_bytes(_RAW, serialization.PublicFormat.Raw).hex()

    @property
    def address(self) -> str:
        return address(self.public_hex)

    def sign(self, message: str) -> str:
        return self._key.sign(message.encode("utf-8")).hex()


def verify(public_hex: str, message: str, signature_hex: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex)).verify(
            bytes.fromhex(signature_hex), message.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError):
        return False
