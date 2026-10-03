"""Additional regression tests for the October business-rule update.
Run together with the existing suite: python -m pytest -q
"""

from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def setup_function():
    client.post("/reset")


def test_transit_can_reschedule():
    response = client.post(
        "/eligibility",
        json={"tracking_number": "EX400181AE", "intent": "reschedule"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is True
    assert data["reason"] == "TRANSIT_ELIGIBLE"


def test_invalid_tracking_is_not_guessed():
    response = client.get("/shipment/EX40023AE")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["result"] == "INVALID_TRACKING_FORMAT"


def test_missing_phone_can_be_collected_without_changing_source_file():
    lookup = client.get("/shipment/EX401184AE").json()
    assert lookup["success"] is True
    assert lookup["needs_phone_collection"] is True

    collected = client.post(
        "/collect-phone",
        json={
            "tracking_number": "EX401184AE",
            "phone_number": "+971501234567",
        },
    ).json()
    assert collected["success"] is True
    assert collected["verification_token"]
    assert collected["identity_assurance"] == "LIMITED_MVP"


def test_obvious_fake_phone_is_rejected():
    response = client.post(
        "/collect-phone",
        json={
            "tracking_number": "EX401184AE",
            "phone_number": "0000000000",
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["reason"] == "INVALID_PHONE"


def test_invalid_weight_creates_review_and_can_be_resolved():
    lookup = client.get("/shipment/EX400402AE").json()
    assert lookup["success"] is False
    assert lookup["result"] == "NEEDS_REVIEW"
    assert lookup["issue"]["code"] == "INVALID_WEIGHT"

    status = client.get("/review/EX400402AE").json()
    assert status["success"] is True
    assert status["status"] == "UNDER_REVIEW"

    resolved = client.post("/review/EX400402AE/resolve").json()
    assert resolved["success"] is True
    assert resolved["status"] == "RESOLVED"

    after = client.get("/shipment/EX400402AE").json()
    assert after["success"] is True


def test_fake_verification_token_still_rejected():
    response = client.post(
        "/reschedule",
        json={
            "tracking_number": "EX400238AE",
            "new_delivery_date": "2099-10-10",
            "verification_token": "fake-token",
            "customer_confirmed": True,
        },
    )
    assert response.status_code == 401
