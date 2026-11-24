"""DPDP data-principal rights: access (export) and erasure.

(Correction is PATCH /citizens/{id}, in services/citizens.py.)
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from citizen_registry_api.errors import ConflictError, NotFoundError
from citizen_registry_api.models import Citizen, Consent
from citizen_registry_api.schemas import CitizenDataExport, CitizenOut, ConsentOut
from citizen_registry_api.services.audit import log_event

# Every personal-data column on Citizen. Erasure sets all of these to NULL.
PERSONAL_FIELDS = (
    "full_name",
    "date_of_birth",
    "mobile",
    "email",
    "district",
    "aadhaar_hash",
    "aadhaar_last4",
)


def export_citizen_data(
    session: Session, citizen_id: uuid.UUID, *, actor: str
) -> CitizenDataExport:
    """Right to access: everything we hold about one citizen, in one response."""
    citizen = session.get(Citizen, citizen_id)
    if citizen is None:
        raise NotFoundError("Citizen not found")
    consents = session.scalars(
        select(Consent)
        .where(Consent.citizen_id == citizen_id)
        .order_by(Consent.granted_at)
    )
    export = CitizenDataExport(
        citizen=CitizenOut.model_validate(citizen),
        consents=[ConsentOut.model_validate(c) for c in consents],
        exported_at=datetime.now(UTC),
    )
    log_event(session, actor=actor, action="citizen.export", citizen_id=citizen_id)
    session.commit()
    return export


def erase_citizen(session: Session, citizen_id: uuid.UUID, *, actor: str) -> Citizen:
    """Right to erasure: wipe personal data, withdraw all consents, keep the anonymous shell.

    The row (its ID) and the audit trail stay, so records of past access remain meaningful.
    Clearing aadhaar_hash also means the same person could register again later.
    """
    citizen = session.get(Citizen, citizen_id)
    if citizen is None:
        raise NotFoundError("Citizen not found")
    if citizen.erased_at is not None:
        raise ConflictError("This record has already been erased")

    for field in PERSONAL_FIELDS:
        setattr(citizen, field, None)
    citizen.erased_at = func.now()

    # Any consent still active is withdrawn: there is no longer anyone to process data for
    withdrawn = session.execute(
        update(Consent)
        .where(Consent.citizen_id == citizen_id, Consent.withdrawn_at.is_(None))
        .values(withdrawn_at=func.now())
    ).rowcount

    log_event(
        session,
        actor=actor,
        action="citizen.erase",
        citizen_id=citizen_id,
        details={"consents_withdrawn": withdrawn},
    )
    session.commit()
    session.refresh(citizen)
    return citizen
