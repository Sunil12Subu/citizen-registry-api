"""Business logic for consent (DPDP: consent is per purpose, and can be withdrawn at any time).

Withdrawing never deletes anything: it sets withdrawn_at, so the full consent history stays
available as evidence of what the citizen agreed to, and when.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from citizen_registry_api.errors import ConflictError, NotFoundError
from citizen_registry_api.models import Citizen, Consent
from citizen_registry_api.schemas import ConsentGrant
from citizen_registry_api.services.audit import log_event


def _get_active_citizen(session: Session, citizen_id: uuid.UUID) -> Citizen:
    """Shared check: the citizen must exist and must not be erased."""
    citizen = session.get(Citizen, citizen_id)
    if citizen is None:
        raise NotFoundError("Citizen not found")
    if citizen.erased_at is not None:
        raise ConflictError("This record has been erased")
    return citizen


def grant_consent(
    session: Session, citizen_id: uuid.UUID, data: ConsentGrant, *, actor: str
) -> Consent:
    """Record consent for one purpose. Raises ConflictError if it is already active."""
    _get_active_citizen(session, citizen_id)
    consent = Consent(
        citizen_id=citizen_id, purpose=data.purpose, notice_version=data.notice_version
    )
    session.add(consent)
    try:
        # The partial unique index (one ACTIVE consent per purpose) is checked here.
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            f"Consent for '{data.purpose.value}' is already active"
        ) from exc

    log_event(
        session,
        actor=actor,
        action="consent.grant",
        citizen_id=citizen_id,
        details={"purpose": data.purpose.value, "notice_version": data.notice_version},
    )
    session.commit()
    session.refresh(consent)
    return consent


def list_consents(
    session: Session, citizen_id: uuid.UUID, *, actor: str
) -> list[Consent]:
    """All consents for a citizen, active and withdrawn, oldest first."""
    if session.get(Citizen, citizen_id) is None:
        raise NotFoundError("Citizen not found")
    consents = list(
        session.scalars(
            select(Consent)
            .where(Consent.citizen_id == citizen_id)
            .order_by(Consent.granted_at)
        )
    )
    log_event(session, actor=actor, action="consent.list", citizen_id=citizen_id)
    session.commit()
    return consents


def withdraw_consent(
    session: Session, citizen_id: uuid.UUID, consent_id: uuid.UUID, *, actor: str
) -> Consent:
    """Withdraw one consent. Raises NotFoundError / ConflictError (already withdrawn)."""
    consent = session.get(Consent, consent_id)
    # Also check it belongs to THIS citizen, so one citizen's URL can't touch another's consent
    if consent is None or consent.citizen_id != citizen_id:
        raise NotFoundError("Consent not found")
    if consent.withdrawn_at is not None:
        raise ConflictError("Consent is already withdrawn")

    consent.withdrawn_at = func.now()
    log_event(
        session,
        actor=actor,
        action="consent.withdraw",
        citizen_id=citizen_id,
        details={"purpose": consent.purpose.value},
    )
    session.commit()
    session.refresh(consent)
    return consent
