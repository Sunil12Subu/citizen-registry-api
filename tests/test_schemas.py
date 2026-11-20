"""Unit tests for schemas.py. No database needed."""

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from citizen_registry_api.schemas import (
    CitizenCreate,
    CitizenOut,
    CitizenUpdate,
    ConsentGrant,
)
from citizen_registry_api.security import verhoeff_check_digit

AADHAAR = "23456789012" + verhoeff_check_digit(
    "23456789012"
)  # synthetic, checksum-valid


def valid_payload(**overrides):
    data = {
        "full_name": "  Priya Raman  ",
        "date_of_birth": "1990-05-14",
        "district": "Coimbatore",
        "mobile": "+91 98400 12345",
        "email": "priya@example.com",
        "aadhaar": f"{AADHAAR[:4]} {AADHAAR[4:8]} {AADHAAR[8:]}",
    }
    data.update(overrides)
    return data


# --- CitizenCreate --------------------------------------------------------------
def test_valid_citizen_is_cleaned_up():
    c = CitizenCreate(**valid_payload())
    assert c.full_name == "Priya Raman"  # whitespace stripped
    assert c.mobile == "9840012345"  # +91 and spaces removed
    assert c.aadhaar == AADHAAR  # spaces removed, checksum passed


@pytest.mark.parametrize("mobile", ["12345", "5840012345", "+91 98400"])
def test_bad_mobile_is_rejected(mobile):
    with pytest.raises(ValidationError, match="Invalid Indian mobile number"):
        CitizenCreate(**valid_payload(mobile=mobile))


def test_future_date_of_birth_is_rejected():
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ValidationError, match="Date of birth"):
        CitizenCreate(**valid_payload(date_of_birth=tomorrow))


def test_bad_aadhaar_is_rejected():
    with pytest.raises(ValidationError, match="Invalid Aadhaar number"):
        CitizenCreate(**valid_payload(aadhaar="234567890120"))


def test_unknown_fields_are_rejected():
    """A client must not be able to sneak in internal fields."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CitizenCreate(**valid_payload(erased_at="2026-01-01T00:00:00Z"))


def test_missing_required_field_is_rejected():
    payload = valid_payload()
    del payload["district"]
    with pytest.raises(ValidationError, match="district"):
        CitizenCreate(**payload)


# --- CitizenUpdate --------------------------------------------------------------
def test_update_tracks_only_sent_fields():
    u = CitizenUpdate(district="Madurai")
    assert u.model_dump(exclude_unset=True) == {"district": "Madurai"}


def test_aadhaar_cannot_be_updated():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CitizenUpdate(aadhaar=AADHAAR)


# --- ConsentGrant ---------------------------------------------------------------
def test_unknown_purpose_is_rejected():
    with pytest.raises(ValidationError):
        ConsentGrant(purpose="marketing", notice_version="v1.0")


@pytest.mark.parametrize("version", ["1.0", "v1", "version-2"])
def test_bad_notice_version_is_rejected(version):
    with pytest.raises(ValidationError):
        ConsentGrant(purpose="service_delivery", notice_version=version)


# --- CitizenOut -----------------------------------------------------------------
def fake_row(**overrides):
    """Stands in for a database row (anything with the right attributes works)."""
    now = datetime.now(UTC)
    data = {
        "id": uuid.uuid4(),
        "full_name": "Priya Raman",
        "date_of_birth": date(1990, 5, 14),
        "district": "Coimbatore",
        "mobile": "9840012345",
        "email": None,
        "aadhaar_hash": "a" * 64,
        "aadhaar_last4": AADHAAR[-4:],
        "created_at": now,
        "updated_at": now,
        "erased_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_output_masks_aadhaar_and_hides_internal_fields():
    body = CitizenOut.model_validate(fake_row()).model_dump()
    assert body["aadhaar_masked"] == f"XXXX-XXXX-{AADHAAR[-4:]}"
    assert "aadhaar_hash" not in body
    assert "aadhaar_last4" not in body
    assert body["is_erased"] is False


def test_erased_citizen_output():
    row = fake_row(
        full_name=None,
        date_of_birth=None,
        district=None,
        mobile=None,
        aadhaar_last4=None,
        erased_at=datetime.now(UTC),
    )
    body = CitizenOut.model_validate(row).model_dump()
    assert body["is_erased"] is True
    assert body["aadhaar_masked"] is None
    assert body["full_name"] is None


def test_validation_error_does_not_echo_aadhaar():
    bad = "234567890120"
    with pytest.raises(ValidationError) as exc:
        CitizenCreate(**valid_payload(aadhaar=bad))
    assert bad not in str(exc.value)
