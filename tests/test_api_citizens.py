"""Integration tests: real HTTP requests -> real app -> real PostgreSQL (test database).

These repeat the manual /docs walkthrough automatically, plus the privacy checks
that are hard to verify by eye.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from citizen_registry_api.main import app
from citizen_registry_api.security import verhoeff_check_digit


def make_aadhaar(first11: str) -> str:
    return first11 + verhoeff_check_digit(first11)


AADHAAR = make_aadhaar("23456789012")  # synthetic, checksum-valid
BAD_AADHAAR = AADHAAR[:11] + str((int(AADHAAR[11]) + 1) % 10)  # wrong check digit


def new_citizen(**overrides) -> dict:
    body = {
        "full_name": "Priya Raman",
        "date_of_birth": "1990-05-14",
        "district": "Coimbatore",
        "mobile": "+91 98400 12345",
        "aadhaar": f"{AADHAAR[:4]} {AADHAAR[4:8]} {AADHAAR[8:]}",
    }
    body.update(overrides)
    return body


@pytest.fixture
def priya(client: TestClient) -> dict:
    """A citizen that already exists, for tests that need one."""
    resp = client.post("/citizens", json=new_citizen())
    assert resp.status_code == 201
    return resp.json()


# --- Basics ----------------------------------------------------------------------
def test_health_needs_no_api_key():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_citizen_endpoints_require_api_key(client: TestClient):
    anonymous = TestClient(app)  # same app and overrides, but no X-API-Key header
    assert anonymous.get("/citizens").status_code == 401


# --- Create ----------------------------------------------------------------------
def test_create_returns_clean_masked_record(priya: dict):
    assert priya["mobile"] == "9840012345"
    assert priya["aadhaar_masked"] == f"XXXX-XXXX-{AADHAAR[-4:]}"
    assert priya["is_erased"] is False
    for hidden in ("aadhaar", "aadhaar_hash", "aadhaar_last4"):
        assert hidden not in priya


def test_duplicate_aadhaar_returns_409(client: TestClient, priya: dict):
    resp = client.post("/citizens", json=new_citizen(full_name="Someone Else"))
    assert resp.status_code == 409


def test_raw_aadhaar_is_never_stored(
    client: TestClient, priya: dict, db_session: Session
):
    """Turn the whole row into text and make sure the 12 digits appear nowhere."""
    row = db_session.execute(
        text("SELECT row_to_json(c)::text FROM citizens c")
    ).scalar_one()
    assert AADHAAR not in row


def test_invalid_aadhaar_returns_422_without_echoing_it(client: TestClient):
    resp = client.post("/citizens", json=new_citizen(aadhaar=BAD_AADHAAR))
    assert resp.status_code == 422
    assert BAD_AADHAAR not in resp.text
    assert resp.json()["detail"][0]["loc"] == ["body", "aadhaar"]


# --- Read ------------------------------------------------------------------------
def test_get_existing_citizen(client: TestClient, priya: dict):
    resp = client.get(f"/citizens/{priya['id']}")
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Priya Raman"


def test_get_unknown_citizen_returns_404(client: TestClient):
    assert client.get(f"/citizens/{uuid.uuid4()}").status_code == 404


def test_get_with_malformed_id_returns_422(client: TestClient):
    assert client.get("/citizens/not-a-uuid").status_code == 422


def test_lookup_by_aadhaar(client: TestClient, priya: dict):
    resp = client.post("/citizens/lookup", json={"aadhaar": AADHAAR})
    assert resp.status_code == 200
    assert resp.json()["id"] == priya["id"]


def test_lookup_unknown_aadhaar_returns_404(client: TestClient, priya: dict):
    other = make_aadhaar("98765432109")
    assert client.post("/citizens/lookup", json={"aadhaar": other}).status_code == 404


# --- List ------------------------------------------------------------------------
def test_list_filters_by_district(client: TestClient):
    client.post("/citizens", json=new_citizen())
    client.post(
        "/citizens",
        json=new_citizen(
            full_name="Arun Kumar",
            district="Madurai",
            aadhaar=make_aadhaar("34567890123"),
        ),
    )
    names = [c["full_name"] for c in client.get("/citizens?district=Madurai").json()]
    assert names == ["Arun Kumar"]


def test_list_rejects_oversized_page(client: TestClient):
    assert client.get("/citizens?limit=500").status_code == 422


def test_list_skips_erased_citizens(
    client: TestClient, priya: dict, db_session: Session
):
    db_session.execute(
        text("UPDATE citizens SET erased_at = now() WHERE id = :id"),
        {"id": priya["id"]},
    )
    db_session.commit()
    assert client.get("/citizens").json() == []


# --- Update ----------------------------------------------------------------------
def test_patch_changes_only_sent_fields(client: TestClient, priya: dict):
    resp = client.patch(f"/citizens/{priya['id']}", json={"district": "Madurai"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["district"] == "Madurai"
    assert body["full_name"] == "Priya Raman"  # untouched
    assert body["updated_at"] > priya["updated_at"]


def test_patch_cannot_change_aadhaar(client: TestClient, priya: dict):
    resp = client.patch(f"/citizens/{priya['id']}", json={"aadhaar": AADHAAR})
    assert resp.status_code == 422


def test_patch_erased_citizen_returns_409(
    client: TestClient, priya: dict, db_session: Session
):
    db_session.execute(
        text("UPDATE citizens SET erased_at = now() WHERE id = :id"),
        {"id": priya["id"]},
    )
    db_session.commit()
    resp = client.patch(f"/citizens/{priya['id']}", json={"district": "Madurai"})
    assert resp.status_code == 409


# --- Audit trail -----------------------------------------------------------------
def test_every_action_is_audited_without_personal_data(
    client: TestClient, priya: dict, db_session: Session
):
    client.get(f"/citizens/{priya['id']}")
    client.patch(f"/citizens/{priya['id']}", json={"mobile": "9876543210"})
    client.post("/citizens/lookup", json={"aadhaar": AADHAAR})

    rows = db_session.execute(
        text("SELECT action, details::text FROM audit_logs ORDER BY id")
    ).all()
    assert [r.action for r in rows] == [
        "citizen.create",
        "citizen.read",
        "citizen.update",
        "citizen.lookup",
    ]
    audit_text = " ".join(r.details for r in rows)
    for personal in ("Priya", "9840012345", "9876543210", AADHAAR):
        assert personal not in audit_text
