"""API request and response shapes (Pydantic models).

models.py  = how data is STORED in the database.
schemas.py = what the API ACCEPTS (input) and RETURNS (output).

Keeping them separate means the API can never accidentally expose a stored field
(like aadhaar_hash), and clients can never set fields they shouldn't (like erased_at).
"""

import re
import uuid
from datetime import date, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    field_validator,
)

from citizen_registry_api.models import ConsentPurpose
from citizen_registry_api.security import mask_aadhaar, normalize_aadhaar

_MOBILE_PATTERN = re.compile(r"[6-9]\d{9}")  # Indian mobile: 10 digits starting 6-9


def _normalize_mobile(value: str | None) -> str | None:
    """Accept '+91 98400 12345', '098400-12345' etc.; store as '9840012345'."""
    if value is None:
        return None
    digits = re.sub(r"[\s-]", "", value)
    digits = re.sub(r"^(\+91|91|0)(?=\d{10}$)", "", digits)
    if not _MOBILE_PATTERN.fullmatch(digits):
        raise ValueError("Invalid Indian mobile number")
    return digits


def _check_date_of_birth(value: date | None) -> date | None:
    if value is not None and not (date(1900, 1, 1) <= value <= date.today()):
        raise ValueError("Date of birth must be between 1900-01-01 and today")
    return value


# --- Inputs ---------------------------------------------------------------------
class _Input(BaseModel):
    """Base for all request bodies."""

    # forbid: reject unknown fields, e.g. a client sending "aadhaar_hash" or "erased_at"
    # str_strip_whitespace: "  Priya  " -> "Priya"
    # hide_input_in_errors: error messages never repeat what was sent (no Aadhaar in logs)
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        hide_input_in_errors=True,
    )


class CitizenCreate(_Input):
    full_name: str = Field(min_length=1, max_length=200, examples=["Priya Raman"])
    date_of_birth: date = Field(examples=["1990-05-14"])
    district: str = Field(min_length=1, max_length=100, examples=["Coimbatore"])
    mobile: str | None = Field(default=None, examples=["+91 98400 12345"])
    email: EmailStr | None = None
    # Write-only: accepted on create, NEVER returned. Synthetic example (valid checksum).
    aadhaar: str = Field(examples=["2345 6789 0124"])

    _dob = field_validator("date_of_birth")(_check_date_of_birth)
    _mobile = field_validator("mobile")(_normalize_mobile)

    @field_validator("aadhaar")
    @classmethod
    def _aadhaar(cls, value: str) -> str:
        return normalize_aadhaar(value)


class CitizenUpdate(_Input):
    """Partial update (PATCH): send only the fields you want to change (DPDP right to correction).

    Aadhaar is deliberately not editable here; a wrong Aadhaar is a new registration.
    """

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    date_of_birth: date | None = None
    district: str | None = Field(default=None, min_length=1, max_length=100)
    mobile: str | None = None
    email: EmailStr | None = None

    _dob = field_validator("date_of_birth")(_check_date_of_birth)
    _mobile = field_validator("mobile")(_normalize_mobile)


class ConsentGrant(_Input):
    purpose: ConsentPurpose
    # Which version of the privacy notice the citizen was shown, e.g. "v1.0" or "v2.3"
    notice_version: str = Field(pattern=r"^v\d+\.\d+$", examples=["v1.0"])


# --- Outputs --------------------------------------------------------------------
class _Output(BaseModel):
    """Base for all responses. from_attributes lets us build them straight from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class CitizenOut(_Output):
    id: uuid.UUID
    full_name: str | None
    date_of_birth: date | None
    district: str | None
    mobile: str | None
    email: str | None
    created_at: datetime
    updated_at: datetime
    erased_at: datetime | None

    # Read from the database row, used to build the mask, then hidden from the response
    aadhaar_last4: str | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def aadhaar_masked(self) -> str | None:
        return mask_aadhaar(self.aadhaar_last4)

    @computed_field
    @property
    def is_erased(self) -> bool:
        return self.erased_at is not None


class ConsentOut(_Output):
    id: uuid.UUID
    citizen_id: uuid.UUID
    purpose: ConsentPurpose
    notice_version: str
    granted_at: datetime
    withdrawn_at: datetime | None

    @computed_field
    @property
    def is_active(self) -> bool:
        return self.withdrawn_at is None


class CitizenDataExport(BaseModel):
    """DPDP right to access: everything we hold about one citizen, in one response."""

    citizen: CitizenOut
    consents: list[ConsentOut]
    exported_at: datetime
