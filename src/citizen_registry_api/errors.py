"""Domain errors raised by services and turned into HTTP responses in main.py.

Services raise these instead of HTTPException, so business logic doesn't depend on the web layer.
"""


class NotFoundError(Exception):
    """The requested record does not exist (-> 404)."""


class ConflictError(Exception):
    """The request clashes with the current state, e.g. a duplicate or an erased record (-> 409)."""
