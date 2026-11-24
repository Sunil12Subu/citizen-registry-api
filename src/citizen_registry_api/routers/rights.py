"""HTTP endpoints for DPDP data-principal rights: access (export) and erasure."""

import uuid

from fastapi import APIRouter

from citizen_registry_api.dependencies import ActorDep, SessionDep
from citizen_registry_api.schemas import CitizenDataExport, CitizenOut
from citizen_registry_api.services import rights as service

router = APIRouter(prefix="/citizens/{citizen_id}", tags=["Data principal rights"])


@router.get("/export", response_model=CitizenDataExport)
def export_citizen_data(citizen_id: uuid.UUID, session: SessionDep, actor: ActorDep):
    """Right to access: all data held about the citizen, including consent history."""
    return service.export_citizen_data(session, citizen_id, actor=actor)


@router.post("/erase", response_model=CitizenOut)
def erase_citizen(citizen_id: uuid.UUID, session: SessionDep, actor: ActorDep):
    """Right to erasure: wipes personal data and withdraws all consents. Cannot be undone."""
    return service.erase_citizen(session, citizen_id, actor=actor)
