"""Криптографічне ядро CNUCoin.

Функція хешування: SHA-256 (FIPS 180-4).
ЕЦП: ECDSA на кривій secp256k1 (та сама крива, що й у Bitcoin/Ethereum).

Обидва алгоритми зафіксовані для всієї системи, як вимагає ЛР №1.
"""
from __future__ import annotations

import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

HASH_ALGORITHM = "SHA-256"
SIGNATURE_ALGORITHM = "ECDSA (secp256k1) + SHA-256"


def sha256(data: str | bytes) -> str:
    """Хеш-образ у вигляді 64 шістнадцяткових символів."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def generate_keypair() -> tuple[str, str]:
    """Генерує пару ключів ЕЦП. Повертає (приватний PEM, публічний PEM)."""
    private_key = ec.generate_private_key(ec.SECP256K1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def address_from_public_key(public_pem: str) -> str:
    """Ідентифікатор користувача = однократний SHA-256 від публічного ключа."""
    return sha256(public_pem)


def sign(private_pem: str, message: str) -> str:
    """Підписує повідомлення; повертає підпис DER у hex."""
    key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    signature = key.sign(message.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    return signature.hex()


def verify(public_pem: str, message: str, signature_hex: str | None) -> bool:
    """Перевіряє ЕЦП. Будь-яка помилка формату трактується як недійсний підпис."""
    if not signature_hex:
        return False
    try:
        key = serialization.load_pem_public_key(public_pem.encode())
        key.verify(bytes.fromhex(signature_hex), message.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False
