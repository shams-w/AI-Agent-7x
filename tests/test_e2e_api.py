"""End-to-end flows through the HTTP API.

customer message -> /agent/understand -> /shipment -> /eligibility -> /verify
-> /reschedule | /update-address -> re-read /shipment + audit log.

Runs against an isolated runtime directory (see conftest.py).
"""

import json
from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.config import AUDIT_LOG_FILE, CLEANED_FILE

client = TestClient(app)
CLEANED = pd.read_excel(CLEANED_FILE)

TOMORROW = (date.today() + timedelta(days=1)).isoformat()
IN_3_DAYS = (date.today() + timedelta(days=3)).isoformat()


def setup_function():
    assert client.post("/reset").json()["success"] is True


def last4(tracking):
    phone = str(CLEANED[CLEANED.tracking_number == tracking].iloc[0]["phone"])
    phone = phone[:-2] if phone.endswith(".0") else phone
    return "".join(c for c in phone if c.isdigit())[-4:]


def say(message, state=None):
    response = client.post("/agent/understand", json={"message": message, "state": state})
    assert response.status_code == 200
    return response.json()


def shipment(tracking):
    return client.get(f"/shipment/{tracking}").json()


def audit_events(action=None, tracking=None):
    if not AUDIT_LOG_FILE.exists():
        return []
    events = [json.loads(line) for line in AUDIT_LOG_FILE.read_text(encoding="utf-8").splitlines() if line]
    return [
        e for e in events
        if (action is None or e["action"] == action) and (tracking is None or e["tracking_number"] == tracking)
    ]


def verify(tracking, digits):
    return client.post("/verify", json={"tracking_number": tracking, "last4": digits}).json()


# -------------------------------------------------
# Successful flows
# -------------------------------------------------

def test_english_reschedule_full_flow_changes_backend_state():
    msg = say("Hi, I missed my delivery EX400238AE. Can you bring it tomorrow?")
    assert msg["language"] == "en"
    assert msg["intent"] == "reschedule"
    tracking = msg["entities"]["tracking_number"]
    assert tracking == "EX400238AE"
    assert msg["entities"]["delivery_date"] == TOMORROW

    before = shipment(tracking)
    assert before["success"] and before["shipment"]["status"] == "Failed Delivery"
    assert "5467" in before["shipment"]["phone"] and before["shipment"]["phone"].startswith("*")

    eligibility = client.post("/eligibility", json={"tracking_number": tracking, "intent": msg["intent"]}).json()
    assert eligibility["allowed"] is True

    v = verify(tracking, last4(tracking))
    assert v["verified"] is True
    token = v["verification_token"]

    result = client.post("/reschedule", json={
        "tracking_number": tracking, "new_delivery_date": msg["entities"]["delivery_date"],
        "verification_token": token, "customer_confirmed": True,
    }).json()
    assert result["success"] is True

    after = shipment(tracking)["shipment"]
    assert after["status"] == "Scheduled for Redelivery"
    assert str(after["scheduled_redelivery_date"])[:10] == TOMORROW

    events = audit_events("RESCHEDULE_DELIVERY", tracking)
    assert events and events[-1]["success"] is True

    # Token is single-use after a successful change.
    reuse = client.post("/reschedule", json={
        "tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
        "verification_token": token, "customer_confirmed": True,
    })
    assert reuse.status_code == 401


def test_arabic_address_update_full_flow():
    tracking = "EX401159AE"
    msg = say(f"السلام عليكم، عايز أغير عنوان التوصيل للشحنة {tracking}")
    assert msg["language"] == "ar"
    assert msg["intent"] == "address"
    assert msg["entities"]["tracking_number"] == tracking
    assert msg["entities"]["address"] is None  # "للشحنة" must not become an address

    assert client.post("/eligibility", json={"tracking_number": tracking, "intent": "address"}).json()["allowed"]
    token = verify(tracking, last4(tracking))["verification_token"]

    reply = say("فيلا ١٢، شارع الوصل، جميرا، دبي", "WAITING_FOR_NEW_ADDRESS")
    new_address = reply["entities"]["address"]
    assert new_address == "فيلا ١٢، شارع الوصل، جميرا، دبي"

    result = client.post("/update-address", json={
        "tracking_number": tracking, "new_address": new_address,
        "verification_token": token, "customer_confirmed": True,
    }).json()
    assert result["success"] is True
    assert shipment(tracking)["shipment"]["delivery_address"] == new_address
    assert audit_events("UPDATE_DELIVERY_ADDRESS", tracking)[-1]["success"] is True


def test_arabic_reschedule_with_natural_date_in_follow_up():
    tracking = "EX400476AE"
    msg = say(f"مكنتش في البيت لما المندوب جه، رقم الشحنة {tracking}")
    assert (msg["language"], msg["intent"]) == ("ar", "reschedule")
    token = verify(tracking, last4(tracking))["verification_token"]
    date_msg = say("بعد بكرة لو سمحت", "WAITING_FOR_RESCHEDULE_DATE")
    requested = date_msg["entities"]["delivery_date"]
    assert requested == (date.today() + timedelta(days=2)).isoformat()
    result = client.post("/reschedule", json={
        "tracking_number": tracking, "new_delivery_date": requested,
        "verification_token": token, "customer_confirmed": True,
    }).json()
    assert result["success"] is True
    assert str(shipment(tracking)["shipment"]["scheduled_redelivery_date"])[:10] == requested


# -------------------------------------------------
# Missing data (never invented — collected from the customer)
# -------------------------------------------------

def test_formerly_undelivered_shipment_with_missing_phone():
    tracking = "EX400380AE"  # raw status "Undelivered", 3 attempts, no phone
    lookup = shipment(tracking)
    assert lookup["success"] is True
    assert lookup["shipment"]["status"] == "Failed Delivery"
    assert lookup["needs_phone_collection"] is True
    assert lookup["shipment"]["phone"] is None  # nothing invented

    assert verify(tracking, "1234")["reason"] == "PHONE_UNAVAILABLE"

    bad = client.post("/collect-phone", json={"tracking_number": tracking, "phone_number": "12345"}).json()
    assert bad["success"] is False and bad["reason"] == "INVALID_PHONE"

    collected = client.post("/collect-phone", json={"tracking_number": tracking, "phone_number": "050 765 4321"}).json()
    assert collected["success"] is True

    result = client.post("/reschedule", json={
        "tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
        "verification_token": collected["verification_token"], "customer_confirmed": True,
    }).json()
    assert result["success"] is True
    assert shipment(tracking)["shipment"]["status"] == "Scheduled for Redelivery"


def test_missing_address_must_be_provided_before_reschedule():
    tracking = "EX400489AE"
    lookup = shipment(tracking)
    assert lookup["requires_address_first"] is True
    eligibility = client.post("/eligibility", json={"tracking_number": tracking, "intent": "reschedule"}).json()
    assert eligibility["allowed"] is True and eligibility["requires_address_first"] is True

    token = verify(tracking, last4(tracking))["verification_token"]

    blocked = client.post("/reschedule", json={
        "tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
        "verification_token": token, "customer_confirmed": True,
    }).json()
    assert blocked["success"] is False
    assert blocked["decision"]["reason"] == "ADDRESS_REQUIRED"

    repaired = client.post("/repair-address", json={
        "tracking_number": tracking, "new_address": "Apt 1204, Marina Heights, Dubai Marina, Dubai",
        "verification_token": token,
    }).json()
    assert repaired["success"] is True

    done = client.post("/reschedule", json={
        "tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
        "verification_token": token, "customer_confirmed": True,
    }).json()
    assert done["success"] is True
    after = shipment(tracking)["shipment"]
    assert after["delivery_address"] == "Apt 1204, Marina Heights, Dubai Marina, Dubai"
    assert after["status"] == "Scheduled for Redelivery"


# -------------------------------------------------
# Blocked cases — backend state must not change
# -------------------------------------------------

@pytest.mark.parametrize(
    "tracking, status, reason",
    [
        ("EX400319AE", "Delivered", "ALREADY_DELIVERED"),
        ("EX401166AE", "Out for Delivery", "OUT_FOR_DELIVERY"),
        ("EX401452AE", "Returned to Sender", "RETURNED_TO_SENDER"),
    ],
)
@pytest.mark.parametrize("intent", ["reschedule", "address"])
def test_blocked_status_never_changes_state(tracking, status, reason, intent):
    before = shipment(tracking)["shipment"]
    assert before["status"] == status

    eligibility = client.post("/eligibility", json={"tracking_number": tracking, "intent": intent}).json()
    assert eligibility["allowed"] is False and eligibility["reason"] == reason

    # Even a verified caller who skips the UI cannot execute the change.
    token = verify(tracking, last4(tracking))["verification_token"]
    if intent == "reschedule":
        result = client.post("/reschedule", json={
            "tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
            "verification_token": token, "customer_confirmed": True,
        }).json()
    else:
        result = client.post("/update-address", json={
            "tracking_number": tracking, "new_address": "Villa 77, Al Barsha 2, Dubai",
            "verification_token": token, "customer_confirmed": True,
        }).json()
    assert result["success"] is False
    assert result["decision"]["reason"] == reason

    # Prerequisite-address path is not a back door either.
    repair = client.post("/repair-address", json={
        "tracking_number": tracking, "new_address": "Villa 77, Al Barsha 2, Dubai", "verification_token": token,
    }).json()
    assert repair["success"] is False

    assert shipment(tracking)["shipment"] == before


def test_unconfirmed_and_past_date_are_not_executed():
    tracking = "EX400093AE"
    before = shipment(tracking)["shipment"]
    token = verify(tracking, last4(tracking))["verification_token"]

    unconfirmed = client.post("/reschedule", json={
        "tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
        "verification_token": token, "customer_confirmed": False,
    }).json()
    assert unconfirmed["success"] is False
    assert unconfirmed["decision"]["reason"] == "CONFIRMATION_REQUIRED"

    past = client.post("/reschedule", json={
        "tracking_number": tracking, "new_delivery_date": "2020-01-01",
        "verification_token": token, "customer_confirmed": True,
    }).json()
    assert past["success"] is False and past["reason"] == "PAST_DATE"

    assert shipment(tracking)["shipment"] == before


def test_data_issue_reports_the_real_blocker_and_escalates():
    # Missing phone (repairable) + ambiguous last-attempt date "07/06/2026"
    # (blocking). Its Excel-serial shipment date is now converted
    # deterministically, so the reported blocker is the genuinely ambiguous date
    # — never the repairable missing phone.
    result = shipment("EX400645AE")
    assert result["success"] is False
    assert result["issue"]["code"] == "INVALID_LAST_ATTEMPT_DATE"

    # Formerly "Undelivered"; last attempt "11.06.2026" is ambiguous: still escalated.
    result = shipment("EX401305AE")
    assert result["success"] is False
    assert result["issue"]["code"] == "INVALID_LAST_ATTEMPT_DATE"


# -------------------------------------------------
# Verification security
# -------------------------------------------------

def test_invalid_verification_and_lockout():
    tracking = "EX400238AE"
    correct = last4(tracking)
    wrong = "0000" if correct != "0000" else "1111"

    first = verify(tracking, wrong)
    assert first["verified"] is False and first["reason"] == "VERIFICATION_FAILED"
    assert first["attempts_remaining"] == 4
    assert "verification_token" not in first

    assert verify(tracking, "12")["reason"] == "INVALID_VERIFICATION_INPUT"

    fake = client.post("/reschedule", json={
        "tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
        "verification_token": "forged", "customer_confirmed": True,
    })
    assert fake.status_code == 401

    for _ in range(4):
        last = verify(tracking, wrong)
    assert last["reason"] == "TOO_MANY_ATTEMPTS"

    # Correct digits are refused while locked.
    locked = verify(tracking, correct)
    assert locked["verified"] is False and locked["reason"] == "TOO_MANY_ATTEMPTS"

    # Reset clears the lock (demo only).
    client.post("/reset")
    assert verify(tracking, correct)["verified"] is True


def test_token_is_bound_to_one_shipment():
    token = verify("EX400238AE", last4("EX400238AE"))["verification_token"]
    other = client.post("/update-address", json={
        "tracking_number": "EX401159AE", "new_address": "Villa 77, Al Barsha 2, Dubai",
        "verification_token": token, "customer_confirmed": True,
    })
    assert other.status_code == 401


def test_collect_phone_cannot_override_registered_phone():
    tracking = "EX400238AE"
    before = shipment(tracking)["shipment"]
    result = client.post("/collect-phone", json={"tracking_number": tracking, "phone_number": "+971501112233"}).json()
    assert result["success"] is False
    assert result["reason"] == "PHONE_ALREADY_REGISTERED"
    assert "verification_token" not in result
    assert shipment(tracking)["shipment"] == before


def test_repair_address_is_not_a_general_address_change():
    tracking = "EX400238AE"
    before = shipment(tracking)["shipment"]
    token = verify(tracking, last4(tracking))["verification_token"]
    result = client.post("/repair-address", json={
        "tracking_number": tracking, "new_address": "Villa 1, Some Other Street, Dubai", "verification_token": token,
    }).json()
    assert result["success"] is False
    assert result["reason"] == "ADDRESS_REPAIR_NOT_ALLOWED"
    assert shipment(tracking)["shipment"] == before


# -------------------------------------------------
# Data quality: statuses and test records
# -------------------------------------------------

def test_cleaned_statuses_are_normalized():
    statuses = set(CLEANED["status"].dropna().astype(str))
    assert statuses <= {
        "Delivered", "Failed Delivery", "Scheduled for Redelivery", "In Transit",
        "Out for Delivery", "Returned to Sender", "TEST",
    }
    raw = pd.read_excel(CLEANED_FILE.parent.parent / "data" / "FDE_Assignment_Shipment_Dataset.xlsx")
    undelivered = raw[raw["status"].astype(str).str.strip().str.lower() == "undelivered"]["tracking_number"]
    for tracking in undelivered:
        row = CLEANED[CLEANED.tracking_number == tracking].iloc[0]
        assert row["status"] == "Failed Delivery"
        assert int(row["delivery_attempts"]) >= 1
        assert "Undelivered" in row["AI_Notes"]
    # Customer data columns are identical to the raw source (never invented).
    for column in ["tracking_number", "customer_name", "delivery_address", "delivery_attempts", "weight_kg"]:
        pd.testing.assert_series_equal(
            raw[column].astype(str).str.strip(), CLEANED[column].astype(str).str.strip(), check_names=False
        )


def test_undelivered_without_attempts_is_not_guessed():
    from backend.data_agent import resolve_undelivered_status, validate_status

    status, note = resolve_undelivered_status("Undelivered", 0)
    assert status == "Undelivered" and note is None
    assert "Unrecognized shipment status" in validate_status("Undelivered")
    assert "Unrecognized shipment status" in validate_status("Lost somewhere")


def test_test_records_are_blocked_and_hidden():
    test_rows = CLEANED[CLEANED.tracking_number.astype(str).str.upper().str.startswith("TEST")]
    assert len(test_rows) == 8  # 6 with status TEST + 2 disguised as Delivered
    for _, row in test_rows.iterrows():
        assert row["AI_Action"] == "NEEDS_REVIEW"
        assert "Test/dummy record detected" in row["AI_Notes"]
        result = shipment(row["tracking_number"])
        assert result["success"] is False and result["issue"]["code"] == "TEST_RECORD"

    for phone in test_rows["phone"].dropna().unique():
        found = client.post("/find-shipments", json={"phone_number": str(int(phone))}).json()
        assert all(not s["tracking_number"].startswith("TEST") for s in found.get("shipments", []))


def test_unknown_status_is_not_eligible_for_address_change(monkeypatch):
    from backend import shipment_service

    original = shipment_service.get_shipment

    def fake(tracking):
        result = original(tracking)
        result["shipment"]["status"] = "RTS"
        return result

    monkeypatch.setattr(shipment_service, "get_shipment", fake)
    result = shipment_service.can_update_address("EX400238AE")
    assert result["allowed"] is False and result["reason"] == "STATUS_NOT_SUPPORTED"


def test_stale_runtime_copy_is_discarded(tmp_path, monkeypatch):
    import os
    from backend import shipment_service

    cleaned = tmp_path / "cleaned.xlsx"
    runtime = tmp_path / "runtime.xlsx"
    runtime.write_bytes(b"old")
    cleaned.write_bytes(b"new")
    os.utime(runtime, (1_000, 1_000))
    monkeypatch.setattr(shipment_service, "CLEANED_FILE", cleaned)
    monkeypatch.setattr(shipment_service, "RUNTIME_FILE", runtime)

    shipment_service.discard_stale_runtime()
    assert not runtime.exists() and cleaned.exists()


def test_runtime_update_audit_log_and_reset_restore():
    from backend.config import RUNTIME_FILE

    tracking = "EX400238AE"
    original = shipment(tracking)["shipment"]
    log_before = len(audit_events())

    # failed verification, blocked action, successful action -> all audited
    verify(tracking, "0000" if last4(tracking) != "0000" else "1111")
    token = verify(tracking, last4(tracking))["verification_token"]
    client.post("/reschedule", json={"tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
                                     "verification_token": token, "customer_confirmed": False})
    client.post("/reschedule", json={"tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
                                     "verification_token": token, "customer_confirmed": True})

    new_events = audit_events()[log_before:]
    kinds = [(e["action"], e["success"]) for e in new_events if e["tracking_number"] == tracking]
    assert ("VERIFY_CUSTOMER", False) in kinds
    assert ("VERIFY_CUSTOMER", True) in kinds
    assert ("RESCHEDULE_DELIVERY", False) in kinds
    assert ("RESCHEDULE_DELIVERY", True) in kinds
    # The registered phone never appears in logged details (in any common
    # format). Timestamps are excluded: their microseconds can contain any
    # 4 digits by chance, which previously made this check flaky.
    for event in new_events:
        details = json.dumps(event["details"])
        for form in ("971536385467", "0536385467", "536385467", "5467"):
            assert form not in details

    # runtime file really changed; source file did not
    runtime = pd.read_excel(RUNTIME_FILE)
    assert runtime[runtime.tracking_number == tracking].iloc[0]["status"] == "Scheduled for Redelivery"
    assert CLEANED[CLEANED.tracking_number == tracking].iloc[0]["status"] == "Failed Delivery"

    # reset restores the original state and is audited
    assert client.post("/reset").json()["success"] is True
    assert shipment(tracking)["shipment"] == original
    assert audit_events()[-1]["action"] == "RESET_RUNTIME_DATASET"
    assert client.post("/reschedule", json={"tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
                                            "verification_token": token, "customer_confirmed": True}).status_code == 401
