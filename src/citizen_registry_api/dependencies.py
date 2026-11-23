"""Shortcuts for the dependencies most endpoints need.

Instead of repeating `Annotated[Session, Depends(get_session)]` in every endpoint,
we write `session: SessionDep`.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from citizen_registry_api.config import Settings, get_settings
from citizen_registry_api.db import get_session
from citizen_registry_api.security import require_api_key

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ActorDep = Annotated[str, Depends(require_api_key)]  # also enforces the API key
