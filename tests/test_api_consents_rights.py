"""Integration tests for consent and DPDP rights (export, erasure)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from citizen_registry_api.security import verhoeff_check_digit

AADHAAR = "23456789012" + verhoeff_check_digit(
    "23456789012"
)  # synthetic, checksum-valid
CONSENT = {"purpose": "service_delivery", "notice_version": "v1.0"}


@pytest.fixture
def citizen_id(client: TestClient) -> str:
    body = {
        "full_name": "Priya Raman",
        "date_of_birth": "1990-05-14",
        "district": "Coimbatore",
        "mobile": "9840012345",
        "email": "priya@example.com",
        "aadhaar": AADHAAR,
    }
    resp = client.post("/citizens", json=body)
    assert resp.status_code == 201
    return resp.json()["id"]


def grant(client: TestClient, citizen_id: str, **overrides):
    return client.post(
        f"/citizens/{citizen_id}/consents", json={**CONSENT, **overrides}
    )


# --- Consent ---------------------------------------------------------------------
def test_grant_consent(client: TestClient, citizen_id: str):
    resp = grant(client, citizen_id)
    assert resp.status_code == 201
    assert resp.json()["is_active"] is True
    assert resp.json()["purpose"] == "service_delivery"


def test_same_purpose_twice_returns_409(client: TestClient, citizen_id: str):
    grant(client, citizen_id)
    assert grant(client, citizen_id).status_code == 409


def test_different_purposes_are_independent(client: TestClient, citizen_id: str):
    grant(client, citizen_id)
    assert grant(client, citizen_id, purpose="sms_email_updates").status_code == 201


def test_consent_for_unknown_citizen_returns_404(client: TestClient):
    assert grant(client, str(uuid.uuid4())).status_code == 404


def test_withdraw_then_grant_again_keeps_history(client: TestClient, citizen_id: str):
    first = grant(client, citizen_id).json()
    resp = client.post(f"/citizens/{citizen_id}/consents/{first['id']}/withdraw")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    assert grant(client, citizen_id, notice_version="v2.0").status_code == 201
    history = client.get(f"/citizens/{citizen_id}/consents").json()
    assert [(c["notice_version"], c["is_active"]) for c in history] == [
        ("v1.0", False),
        ("v2.0", True),
    ]


def test_withdraw_twice_returns_409(client: TestClient, citizen_id: str):
    consent = grant(client, citizen_id).json()
    url = f"/citizens/{citizen_id}/consents/{consent['id']}/withdraw"
    client.post(url)
    assert client.post(url).status_code == 409


def test_cannot_withdraw_another_citizens_consent(client: TestClient, citizen_id: str):
    consent = grant(client, citizen_id).json()
    other = client.post(
        "/citizens",
        json={
            "full_name": "Arun Kumar",
            "date_of_birth": "1985-01-01",
            "district": "Madurai",
            "aadhaar": "34567890123" + verhoeff_check_digit("34567890123"),
        },
    ).json()
    resp = client.post(f"/citizens/{other['id']}/consents/{consent['id']}/withdraw")
    assert resp.status_code == 404


# --- Right to access (export) ----------------------------------------------------
def test_export_contains_citizen_and_consents(client: TestClient, citizen_id: str):
    grant(client, citizen_id)
    resp = client.get(f"/citizens/{citizen_id}/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["citizen"]["full_name"] == "Priya Raman"
    assert len(body["consents"]) == 1
    assert "exported_at" in body
    assert "aadhaar_hash" not in resp.text


# --- Right to erasure ------------------------------------------------------------
def test_erase_wipes_personal_data_and_withdraws_consents(
    client: TestClient, citizen_id: str, db_session: Session
):
    grant(client, citizen_id)
    grant(client, citizen_id, purpose="sms_email_updates")

    resp = client.post(f"/citizens/{citizen_id}/erase")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_erased"] is True
    for field in (
        "full_name",
        "date_of_birth",
        "mobile",
        "email",
        "district",
        "aadhaar_masked",
    ):
        assert body[field] is None

    # Check the database itself, not just the API response
    row = db_session.execute(
        text("SELECT row_to_json(c)::text FROM citizens c")
    ).scalar_one()
    for personal in (
        "Priya",
        "9840012345",
        "priya@example.com",
        "Coimbatore",
        AADHAAR[-4:],
    ):
        assert personal not in row

    consents = client.get(f"/citizens/{citizen_id}/consents").json()
    assert all(not c["is_active"] for c in consents)


def test_erase_twice_returns_409(client: TestClient, citizen_id: str):
    client.post(f"/citizens/{citizen_id}/erase")
    assert client.post(f"/citizens/{citizen_id}/erase").status_code == 409


def test_erased_citizen_cannot_get_new_consent(client: TestClient, citizen_id: str):
    client.post(f"/citizens/{citizen_id}/erase")
    assert grant(client, citizen_id).status_code == 409


def test_same_aadhaar_can_register_again_after_erasure(
    client: TestClient, citizen_id: str
):
    client.post(f"/citizens/{citizen_id}/erase")
    resp = client.post(
        "/citizens",
        json={
            "full_name": "Priya Raman",
            "date_of_birth": "1990-05-14",
            "district": "Coimbatore",
            "aadhaar": AADHAAR,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["id"] != citizen_id


def test_audit_trail_survives_erasure(
    client: TestClient, citizen_id: str, db_session: Session
):
    grant(client, citizen_id)
    client.post(f"/citizens/{citizen_id}/erase")
    actions = (
        db_session.execute(
            text("SELECT action FROM audit_logs WHERE citizen_id = :id ORDER BY id"),
            {"id": citizen_id},
        )
        .scalars()
        .all()
    )
    assert actions == ["citizen.create", "consent.grant", "citizen.erase"]
