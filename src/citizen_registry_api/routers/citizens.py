"""HTTP endpoints for citizen records.

Each endpoint is thin: read the request, call a service function, return the result.
All endpoints require the X-API-Key header (via ActorDep).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from citizen_registry_api.dependencies import ActorDep, SessionDep, SettingsDep
from citizen_registry_api.schemas import (
    AadhaarLookup,
    CitizenCreate,
    CitizenOut,
    CitizenUpdate,
)
from citizen_registry_api.services import citizens as service

router = APIRouter(prefix="/citizens", tags=["Citizens"])


@router.post("", response_model=CitizenOut, status_code=status.HTTP_201_CREATED)
def create_citizen(
    body: CitizenCreate, session: SessionDep, actor: ActorDep, settings: SettingsDep
):
    """Register a new citizen. Returns 409 if the Aadhaar is already registered."""
    return service.create_citizen(
        session, body, actor=actor, secret=settings.id_hash_secret.get_secret_value()
    )


@router.get("", response_model=list[CitizenOut])
def list_citizens(
    session: SessionDep,
    actor: ActorDep,
    district: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """List citizens, newest first. Paginated: max 100 per page."""
    return service.list_citizens(
        session, actor=actor, district=district, limit=limit, offset=offset
    )


# POST, not GET: a GET would put the Aadhaar in the URL, and URLs end up in server logs.
@router.post("/lookup", response_model=CitizenOut)
def lookup_by_aadhaar(
    body: AadhaarLookup, session: SessionDep, actor: ActorDep, settings: SettingsDep
):
    """Find a citizen by Aadhaar number."""
    return service.find_by_aadhaar(
        session,
        body.aadhaar,
        actor=actor,
        secret=settings.id_hash_secret.get_secret_value(),
    )


@router.get("/{citizen_id}", response_model=CitizenOut)
def get_citizen(citizen_id: uuid.UUID, session: SessionDep, actor: ActorDep):
    """Get one citizen by ID."""
    return service.get_citizen(session, citizen_id, actor=actor)


@router.patch("/{citizen_id}", response_model=CitizenOut)
def update_citizen(
    citizen_id: uuid.UUID, body: CitizenUpdate, session: SessionDep, actor: ActorDep
):
    """Correct a citizen's details. Send only the fields to change."""
    return service.update_citizen(session, citizen_id, body, actor=actor)
