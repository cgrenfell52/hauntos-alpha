"""Operator authentication helpers for HauntOS."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Any


DEFAULT_OPERATOR_PIN = "1031"
DEFAULT_OPERATOR_PIN_SALT = "hauntos-alpha-default"
PIN_HASH_PREFIX = "pbkdf2_sha256"
PIN_HASH_ROUNDS = 120_000


def auth_enabled(settings: dict[str, Any] | None = None) -> bool:
    """Return True when operator login should protect the app."""
    env_value = os.environ.get("HAUNTOS_AUTH_DISABLED", "")
    if env_value.lower() in {"1", "true", "yes", "on"}:
        return False

    if settings is not None and settings.get("auth_enabled") is False:
        return False

    return True


def hash_pin(pin: str, salt: str | None = None) -> str:
    """Return a salted PBKDF2 hash for a short operator PIN."""
    pin_text = str(pin)
    salt_text = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        pin_text.encode("utf-8"),
        salt_text.encode("utf-8"),
        PIN_HASH_ROUNDS,
    ).hex()
    return f"{PIN_HASH_PREFIX}${PIN_HASH_ROUNDS}${salt_text}${digest}"


def verify_pin(pin: str, settings: dict[str, Any] | None = None) -> bool:
    """Verify a user-submitted PIN against env/settings/default credentials."""
    env_pin = os.environ.get("HAUNTOS_OPERATOR_PIN")
    if env_pin is not None:
        return hmac.compare_digest(str(pin), env_pin)

    stored_hash = None
    if settings is not None:
        candidate = settings.get("operator_pin_hash")
        if isinstance(candidate, str) and candidate:
            stored_hash = candidate

    return verify_pin_hash(str(pin), stored_hash or default_pin_hash())


def verify_pin_hash(pin: str, stored_hash: str) -> bool:
    """Compare a PIN with a stored PBKDF2 hash."""
    try:
        prefix, rounds_text, salt, digest = stored_hash.split("$", 3)
        rounds = int(rounds_text)
    except (ValueError, AttributeError):
        return False

    if prefix != PIN_HASH_PREFIX or rounds <= 0:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        str(pin).encode("utf-8"),
        salt.encode("utf-8"),
        rounds,
    ).hex()
    return hmac.compare_digest(candidate, digest)


def default_pin_hash() -> str:
    """Return the built-in alpha PIN hash."""
    return hash_pin(DEFAULT_OPERATOR_PIN, salt=DEFAULT_OPERATOR_PIN_SALT)
