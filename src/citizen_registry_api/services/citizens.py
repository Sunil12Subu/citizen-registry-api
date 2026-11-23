"""Business logic for citizen records. No HTTP here: functions take plain data and a session."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from citizen_registry_api.errors import ConflictError, NotFoundError
from citizen_registry_api.models import Citizen
from citizen_registry_api.schemas import CitizenCreate, CitizenUpdate
from citizen_registry_api.security import hash_aadhaar
from citizen_registry_api.services.audit import log_event


def create_citizen(
    session: Session, data: CitizenCreate, *, actor: str, secret: str
) -> Citizen:
    """Register a citizen. Raises ConflictError if the Aadhaar is already registered."""
    aadhaar_hash = hash_aadhaar(data.aadhaar, secret)
    if session.scalar(select(Citizen.id).where(Citizen.aadhaar_hash == aadhaar_hash)):
        raise ConflictError("A citizen with this Aadhaar is already registered")

    citizen = Citizen(
        **data.model_dump(exclude={"aadhaar"}),
        aadhaar_hash=aadhaar_hash,
        aadhaar_last4=data.aadhaar[-4:],
    )
    session.add(citizen)
    session.flush()  # sends the INSERT now so citizen.id is available for the audit entry
    log_event(session, actor=actor, action="citizen.create", citizen_id=citizen.id)
    try:
        session.commit()
    except IntegrityError as exc:
        # Safety net: two identical requests at the same moment can both pass the check above.
        # The UNIQUE constraint in the database still stops the second one.
        session.rollback()
        raise ConflictError(
            "A citizen with this Aadhaar is already registered"
        ) from exc
    session.refresh(citizen)  # reload server-generated values (created_at, updated_at)
    return citizen


def get_citizen(session: Session, citizen_id: uuid.UUID, *, actor: str) -> Citizen:
    """Fetch one citizen and log the access. Raises NotFoundError."""
    citizen = session.get(Citizen, citizen_id)
    if citizen is None:
        raise NotFoundError("Citizen not found")
    log_event(session, actor=actor, action="citizen.read", citizen_id=citizen.id)
    session.commit()
    return citizen


def find_by_aadhaar(
    session: Session, aadhaar: str, *, actor: str, secret: str
) -> Citizen:
    """Look up a citizen by Aadhaar (hashed first; the raw number is never queried or stored)."""
    citizen = session.scalar(
        select(Citizen).where(Citizen.aadhaar_hash == hash_aadhaar(aadhaar, secret))
    )
    if citizen is None:
        raise NotFoundError("Citizen not found")
    log_event(session, actor=actor, action="citizen.lookup", citizen_id=citizen.id)
    session.commit()
    return citizen


def list_citizens(
    session: Session, *, actor: str, district: str | None, limit: int, offset: int
) -> list[Citizen]:
    """List citizens (newest first), optionally filtered by district. Erased records are skipped."""
    query = select(Citizen).where(Citizen.erased_at.is_(None))
    if district:
        query = query.where(Citizen.district == district)
    query = query.order_by(Citizen.created_at.desc()).limit(limit).offset(offset)
    citizens = list(session.scalars(query))

    log_event(
        session,
        actor=actor,
        action="citizen.list",
        details={
            "district": district,
            "limit": limit,
            "offset": offset,
            "returned": len(citizens),
        },
    )
    session.commit()
    return citizens


def update_citizen(
    session: Session, citizen_id: uuid.UUID, data: CitizenUpdate, *, actor: str
) -> Citizen:
    """Correct a citizen's details (DPDP right to correction). Only sent fields change."""
    citizen = session.get(Citizen, citizen_id)
    if citizen is None:
        raise NotFoundError("Citizen not found")
    if citizen.erased_at is not None:
        raise ConflictError("This record has been erased and cannot be updated")

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(citizen, field, value)

    # Log WHICH fields changed, never the old or new values
    log_event(
        session,
        actor=actor,
        action="citizen.update",
        citizen_id=citizen.id,
        details={"fields": sorted(changes)},
    )
    session.commit()
    session.refresh(citizen)
    return citizen
