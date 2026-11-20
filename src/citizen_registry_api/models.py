"""Database tables (SQLAlchemy ORM models).

These classes describe how data is STORED. What the API accepts and returns
is defined separately in schemas.py.

DPDP design notes:
- Aadhaar is never stored in plain text: only a keyed hash (for lookups) and the last 4 digits.
- Personal fields are nullable so a record can be anonymised on erasure
  while its ID (and audit trail) stays intact.
- Consent is recorded per purpose, with the privacy-notice version shown to the citizen.
"""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Predictable constraint names, e.g. "fk_consents_citizen_id_citizens".
# Alembic needs named constraints to change or drop them later.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Parent class for all tables."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class ConsentPurpose(str, enum.Enum):
    """The specific reasons a citizen can consent to (DPDP: purpose limitation)."""

    SCHEME_ELIGIBILITY = "scheme_eligibility"
    SERVICE_DELIVERY = "service_delivery"
    SMS_EMAIL_UPDATES = "sms_email_updates"
    ANONYMISED_RESEARCH = "anonymised_research"


class Citizen(Base):
    __tablename__ = "citizens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # --- Personal data (nullable so it can be wiped on erasure) ---
    full_name: Mapped[str | None] = mapped_column(String(200))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    mobile: Mapped[str | None] = mapped_column(String(15))
    email: Mapped[str | None] = mapped_column(String(254))
    district: Mapped[str | None] = mapped_column(String(100))

    # --- Aadhaar: never stored in plain text ---
    aadhaar_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True
    )  # HMAC-SHA256 hex
    aadhaar_last4: Mapped[str | None] = mapped_column(
        String(4)
    )  # for display: XXXX-XXXX-1234

    # --- Housekeeping ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    erased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    consents: Mapped[list["Consent"]] = relationship(back_populates="citizen")


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    citizen_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("citizens.id"), index=True)
    purpose: Mapped[ConsentPurpose] = mapped_column(
        # native_enum=False -> stored as VARCHAR + CHECK; easier to extend than a Postgres ENUM
        Enum(
            ConsentPurpose,
            native_enum=False,
            create_constraint=True,
            length=50,
            name="purpose",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    notice_version: Mapped[str] = mapped_column(
        String(20)
    )  # which privacy notice they saw
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    citizen: Mapped[Citizen] = relationship(back_populates="consents")

    __table_args__ = (
        # At most ONE active (not withdrawn) consent per citizen per purpose.
        Index(
            "uq_consents_active_per_purpose",
            "citizen_id",
            "purpose",
            unique=True,
            postgresql_where=text("withdrawn_at IS NULL"),
        ),
    )


class AuditLog(Base):
    """Append-only record of who accessed or changed personal data, and why.

    Rule: never put personal data itself in here — only IDs and actions.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor: Mapped[str] = mapped_column(String(100))  # which client/user did it
    action: Mapped[str] = mapped_column(
        String(50)
    )  # e.g. "citizen.read", "consent.withdraw"
    citizen_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("citizens.id"), index=True
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
