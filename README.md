# Citizen Registry API

[![CI](https://github.com/Sunil12Subu/citizen-registry-api/actions/workflows/ci.yml/badge.svg)](https://github.com/Sunil12Subu/citizen-registry-api/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

A reference REST API for storing citizen records in line with **India's Digital Personal Data
Protection (DPDP) Act, 2023**: consent per purpose, a complete audit trail, data-principal rights
(access, correction, erasure), and Aadhaar numbers that are **never stored in plain text**.

> ⚠️ Uses **synthetic data only**. A portfolio and reference project, not legal advice or a
> certified compliance product.

---

## Why this project

Government systems hold sensitive personal data for millions of citizens. Having built BI
platforms across 35 Tamil Nadu government departments, I wanted to show how the **backend
behind such a system** can be built so that privacy rules are enforced by design: in the
schema, the API layer and the tests, not left to a policy document.

## DPDP principles → implementation

| DPDP principle | How this API enforces it |
|---|---|
| Purpose limitation | Consent is recorded **per purpose**, with the privacy-notice version shown |
| Consent can be withdrawn | `POST .../withdraw` keeps the history; the DB allows only one *active* consent per purpose |
| Right to access | `GET /citizens/{id}/export` returns everything held, including consent history |
| Right to correction | `PATCH /citizens/{id}` changes only the fields sent |
| Right to erasure | `POST /citizens/{id}/erase` wipes all personal fields and withdraws consents; the audit trail survives |
| Accountability | Every read and write is audited (who, what, when), **with no personal data in the log** |
| Data minimisation & security | Aadhaar stored only as an HMAC-SHA256 hash + last 4 digits; responses show `XXXX-XXXX-1234` |

## Architecture

```
            ┌──────────────────────────────────────────────┐
 Client ──► │ FastAPI app                                  │
 X-API-Key  │                                              │
            │  routers/      thin HTTP layer               │
            │     │          (validation via schemas.py)   │
            │     ▼                                        │
            │  services/     business rules                │
            │     │          citizens · consents · rights  │
            │     ├────────► audit.py (same transaction)   │
            │     ▼                                        │
            │  models.py     SQLAlchemy 2.0 ORM            │
            └─────┬────────────────────────────────────────┘
                  ▼
            PostgreSQL 16  ◄── Alembic migrations
            citizens · consents · audit_logs
```

- **Routers** only translate HTTP ↔ Python. **Services** hold the rules and know nothing about
  HTTP, so they can be reused by a CLI or a background job.
- Each change and its audit entry are committed in **one transaction**: there is never a change
  without its log entry.

## Security design

- **Aadhaar:** validated with the Verhoeff checksum, then stored only as a *keyed* hash (HMAC).
  A plain SHA-256 of a 12-digit number can be brute-forced in hours; without the secret key,
  the HMAC can't be.
- **Lookups by Aadhaar use POST**, so the number never appears in URLs or server logs.
- **No personal data in errors:** validation errors never echo the submitted values.
- **Mass-assignment protection:** unknown fields are rejected (`extra="forbid"`).
- **IDOR protection:** a consent can only be changed through its own citizen's URL.
- **Secrets** live only in environment variables (`.env` locally, never committed); the API key
  is compared in constant time.
- **Container** runs as a non-root user; the database port is bound to `127.0.0.1`.

## API overview

All endpoints except `/health` require the `X-API-Key` header.
Interactive docs: **http://127.0.0.1:8000/docs**

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/citizens` | Register a citizen (409 on duplicate Aadhaar) |
| `GET` | `/citizens` | List, filter by district, paginated (max 100) |
| `GET` | `/citizens/{id}` | Get one citizen |
| `PATCH` | `/citizens/{id}` | Correct details |
| `POST` | `/citizens/lookup` | Find by Aadhaar (sent in the body) |
| `POST` | `/citizens/{id}/consents` | Grant consent for a purpose |
| `GET` | `/citizens/{id}/consents` | Consent history |
| `POST` | `/citizens/{id}/consents/{consent_id}/withdraw` | Withdraw consent |
| `GET` | `/citizens/{id}/export` | Right to access |
| `POST` | `/citizens/{id}/erase` | Right to erasure |

### Example

```bash
curl -X POST http://127.0.0.1:8000/citizens \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"full_name": "Priya Raman", "date_of_birth": "1990-05-14",
       "district": "Coimbatore", "mobile": "+91 98400 12345",
       "aadhaar": "2345 6789 0124"}'
```

```json
{
  "id": "a5ca6a2e-a06c-4f90-ba92-8f269606d215",
  "full_name": "Priya Raman",
  "mobile": "9840012345",
  "aadhaar_masked": "XXXX-XXXX-0124",
  "is_erased": false,
  "...": "..."
}
```

## Quick start (Docker)

Requires Docker Desktop.

```bash
git clone https://github.com/Sunil12Subu/citizen-registry-api.git
cd citizen-registry-api
cp .env.example .env        # then replace every "change-me" value
docker compose up -d --build
```

Open http://127.0.0.1:8000/docs, click **Authorize** and paste your `API_KEY`.
Compose starts PostgreSQL, runs the migrations, then starts the API.

## Local development

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
uv sync                                   # create .venv and install everything
docker compose up -d db                   # database only
uv run alembic upgrade head               # create tables
uv run uvicorn citizen_registry_api.main:app --reload
```

## Tests

65 tests: fast unit tests plus integration tests that run real HTTP requests against a
real PostgreSQL test database, built with the project's own Alembic migrations.

```bash
docker exec registry-db createdb -U registry_user registry_test   # once
uv run pytest -v
uv run ruff check .
```

Highlights:
- the raw Aadhaar never appears anywhere in the stored row
- the audit log contains no names, phone numbers or Aadhaar numbers
- erasure is verified **in the database**, not just in the API response
- one citizen cannot withdraw another citizen's consent

**CI** (GitHub Actions) runs on every push: Ruff lint · tests against PostgreSQL 16 ·
`alembic check` (models and migrations in sync) · Docker image build.

## Project structure

```
src/citizen_registry_api/
├── main.py            app setup, error handlers
├── config.py          settings from environment (.env)
├── db.py              engine and sessions
├── models.py          database tables
├── schemas.py         request/response shapes and validation
├── security.py        Aadhaar validation, HMAC, masking, API key
├── dependencies.py    shared FastAPI dependencies
├── errors.py          domain errors → 404 / 409
├── routers/           citizens · consents · rights
└── services/          citizens · consents · rights · audit
migrations/            Alembic migrations
tests/                 unit + integration tests
```

## Known limitations & next steps

Honest scope for a reference project:
- **One shared API key** rather than per-user accounts and roles (next: OAuth2 / JWT with roles).
- **No rate limiting** (next: a gateway or middleware).
- Fields other than Aadhaar are not encrypted at rest (next: column-level encryption for mobile and email).
- Audit-log immutability is enforced by code, not yet by database permissions.

## Tech stack

Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 · Alembic · PostgreSQL 16 · pytest ·
Ruff · uv · Docker · GitHub Actions

## License

[MIT](LICENSE) © 2026 Sunil Subramaniam Sreedhar