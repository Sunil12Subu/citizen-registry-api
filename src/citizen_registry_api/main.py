"""Application entry point: creates the FastAPI app and plugs everything together.

Run locally with:  uv run uvicorn citizen_registry_api.main:app --reload
"""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from citizen_registry_api import __version__
from citizen_registry_api.errors import ConflictError, NotFoundError
from citizen_registry_api.routers import citizens, consents, rights

app = FastAPI(
    title="Citizen Registry API",
    version=__version__,
    description=(
        "Reference backend for citizen records under India's DPDP Act 2023: "
        "consent per purpose, audit trail, masked identifiers. Synthetic data only."
    ),
)

app.include_router(citizens.router)
app.include_router(consents.router)
app.include_router(rights.router)


@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    """Liveness check for Docker / load balancers. No authentication needed."""
    return {"status": "ok"}


# --- Turn domain errors into HTTP responses --------------------------------------
@app.exception_handler(NotFoundError)
def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)}
    )


@app.exception_handler(ConflictError)
def _conflict(_: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)}
    )


@app.exception_handler(RequestValidationError)
def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Same as FastAPI's default 422 response, minus the submitted values.

    FastAPI normally echoes back each invalid input, which could put an Aadhaar
    or phone number into proxy and gateway logs. We keep only where and why.
    """
    errors = [
        {"loc": err["loc"], "msg": err["msg"], "type": err["type"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=jsonable_encoder({"detail": errors}),
    )
