"""Security helpers: Aadhaar validation, hashing and masking, plus API-key checking.

The Aadhaar functions are "pure": same input -> same output, no database, no settings.
That makes them easy to test and safe to reuse.
"""

import hashlib
import hmac
import re
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from citizen_registry_api.config import Settings, get_settings

# --- Verhoeff checksum ---------------------------------------------------------
# The 12th digit of every Aadhaar number is a Verhoeff check digit. It catches
# all single-digit typos and swapped neighbouring digits (e.g. 12 -> 21).
_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_check_digit(digits: str) -> str:
    """Return the Verhoeff check digit to append to `digits` (used to make synthetic test data)."""
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def _verhoeff_is_valid(number: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


# --- Aadhaar handling ------------------------------------------------------------
_AADHAAR_PATTERN = re.compile(r"[2-9]\d{11}")  # 12 digits, cannot start with 0 or 1


def normalize_aadhaar(raw: str) -> str:
    """Strip spaces/hyphens and validate. Returns 12 digits or raises ValueError.

    The error message never repeats the input, so Aadhaar numbers don't leak into logs.
    """
    number = re.sub(r"[\s-]", "", raw)
    if not _AADHAAR_PATTERN.fullmatch(number) or not _verhoeff_is_valid(number):
        raise ValueError("Invalid Aadhaar number")
    return number


def hash_aadhaar(aadhaar: str, secret: str) -> str:
    """Keyed hash (HMAC-SHA256) of a normalized Aadhaar number, as 64 hex characters.

    Same number + same secret -> same hash, so we can still find duplicates and do lookups.
    Without the secret, an attacker cannot rebuild the hashes by trying all numbers.
    """
    return hmac.new(secret.encode(), aadhaar.encode(), hashlib.sha256).hexdigest()


def mask_aadhaar(last4: str | None) -> str | None:
    """Display form: 'XXXX-XXXX-1234'. Returns None for erased records."""
    return f"XXXX-XXXX-{last4}" if last4 else None


# --- API key authentication -----------------------------------------------------
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    api_key: Annotated[str | None, Depends(_api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """FastAPI dependency: reject the request with 401 unless a valid X-API-Key is sent.

    Returns the caller's name, which we record in the audit log.
    """
    expected = settings.api_key.get_secret_value()
    # compare_digest takes the same time whether the first or last character differs,
    # so attackers can't guess the key one character at a time by measuring response speed.
    if api_key is None or not secrets.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "APIKey"},
        )
    return "api-client"
