"""Audit trail: record who accessed or changed personal data.

The audit row is added to the SAME session as the change it describes, so both are
saved together by one commit, or neither is. There is never a change without its log entry.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from citizen_registry_api.models import AuditLog


def log_event(
    session: Session,
    *,
    actor: str,
    action: str,
    citizen_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an audit entry to the current transaction (the caller commits).

    `details` must never contain personal data: store field NAMES, counts, filters - not values.
    """
    session.add(
        AuditLog(
            actor=actor, action=action, citizen_id=citizen_id, details=details or {}
        )
    )
