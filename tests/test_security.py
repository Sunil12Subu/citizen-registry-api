"""Unit tests for security.py. No database needed."""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from citizen_registry_api.config import Settings, get_settings
from citizen_registry_api.security import (
    hash_aadhaar,
    mask_aadhaar,
    normalize_aadhaar,
    require_api_key,
    verhoeff_check_digit,
)


def make_aadhaar(first11: str) -> str:
    """Build a synthetic but checksum-valid Aadhaar number from 11 digits."""
    return first11 + verhoeff_check_digit(first11)


VALID = make_aadhaar("23456789012")


# --- normalize_aadhaar -----------------------------------------------------------
def test_valid_aadhaar_is_accepted():
    assert normalize_aadhaar(VALID) == VALID


@pytest.mark.parametrize(
    "formatted",
    [f"{VALID[:4]} {VALID[4:8]} {VALID[8:]}", f"{VALID[:4]}-{VALID[4:8]}-{VALID[8:]}"],
)
def test_spaces_and_hyphens_are_removed(formatted):
    assert normalize_aadhaar(formatted) == VALID


@pytest.mark.parametrize(
    "bad",
    [
        "12345",  # too short
        "1" + VALID[1:],  # starts with 1
        "0" + VALID[1:],  # starts with 0
        VALID[:11] + str((int(VALID[11]) + 1) % 10),  # wrong check digit (typo)
        VALID[:10] + VALID[11] + VALID[10],  # last two digits swapped
        "abcd efgh ijkl",  # not digits
    ],
)
def test_invalid_aadhaar_is_rejected(bad):
    with pytest.raises(ValueError, match="Invalid Aadhaar number"):
        normalize_aadhaar(bad)


def test_error_message_does_not_leak_the_number():
    bad = VALID[:11] + str((int(VALID[11]) + 1) % 10)
    with pytest.raises(ValueError) as exc:
        normalize_aadhaar(bad)
    assert bad not in str(exc.value)


# --- hash_aadhaar ----------------------------------------------------------------
def test_hash_is_deterministic_and_64_hex_chars():
    h1 = hash_aadhaar(VALID, "secret-a")
    assert h1 == hash_aadhaar(VALID, "secret-a")
    assert len(h1) == 64
    assert VALID not in h1


def test_hash_changes_with_secret():
    assert hash_aadhaar(VALID, "secret-a") != hash_aadhaar(VALID, "secret-b")


# --- mask_aadhaar ----------------------------------------------------------------
def test_mask_shows_only_last4():
    assert mask_aadhaar("1234") == "XXXX-XXXX-1234"


def test_mask_of_erased_record_is_none():
    assert mask_aadhaar(None) is None


# --- require_api_key -------------------------------------------------------------
@pytest.fixture
def client():
    """A tiny throwaway app with one protected route, using a known test key."""
    app = FastAPI()

    @app.get("/protected")
    def protected(actor: Annotated[str, Depends(require_api_key)]):
        return {"actor": actor}

    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql+psycopg://unused",
        api_key="test-key",
        id_hash_secret="unused",
    )
    return TestClient(app)


def test_missing_api_key_returns_401(client):
    assert client.get("/protected").status_code == 401


def test_wrong_api_key_returns_401(client):
    assert client.get("/protected", headers={"X-API-Key": "wrong"}).status_code == 401


def test_correct_api_key_is_accepted(client):
    resp = client.get("/protected", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200
    assert resp.json() == {"actor": "api-client"}
