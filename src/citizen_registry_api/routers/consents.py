"""HTTP endpoints for consent, nested under a citizen: /citizens/{citizen_id}/consents."""

import uuid

from fastapi import APIRouter, status

from citizen_registry_api.dependencies import ActorDep, SessionDep
from citizen_registry_api.schemas import ConsentGrant, ConsentOut
from citizen_registry_api.services import consents as service

router = APIRouter(prefix="/citizens/{citizen_id}/consents", tags=["Consents"])


@router.post("", response_model=ConsentOut, status_code=status.HTTP_201_CREATED)
def grant_consent(
    citizen_id: uuid.UUID, body: ConsentGrant, session: SessionDep, actor: ActorDep
):
    """Record consent for one purpose. Returns 409 if it is already active."""
    return service.grant_consent(session, citizen_id, body, actor=actor)


@router.get("", response_model=list[ConsentOut])
def list_consents(citizen_id: uuid.UUID, session: SessionDep, actor: ActorDep):
    """Full consent history (active and withdrawn)."""
    return service.list_consents(session, citizen_id, actor=actor)


# POST .../withdraw rather than DELETE: nothing is deleted, the consent is marked as withdrawn.
@router.post("/{consent_id}/withdraw", response_model=ConsentOut)
def withdraw_consent(
    citizen_id: uuid.UUID, consent_id: uuid.UUID, session: SessionDep, actor: ActorDep
):
    """Withdraw a consent. The record is kept as history."""
    return service.withdraw_consent(session, citizen_id, consent_id, actor=actor)
