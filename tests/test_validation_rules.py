"""Regression tests for the data-audit validation fixes:
placeholder addresses, safe date formats, UAE mobile validation/normalization,
decimal fields, and preserved safety behaviour.
"""

import json
from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.config import CLEANED_FILE, RUNTIME_FILE
from backend.data_agent import (
    normalize_cod,
    normalize_date_value,
    validate_address,
    validate_date,
    validate_date_sequence,
    validate_phone,
)
from backend.intent_agent import extract_date
from backend.shipment_service import is_valid_delivery_address
from backend.validators import (
    is_placeholder_address,
    normalize_registered_phone,
    normalize_uae_mobile,
    parse_excel_serial,
)

client = TestClient(app)
CLEANED = pd.read_excel(CLEANED_FILE)
IN_3_DAYS = (date.today() + timedelta(days=3)).isoformat()


def setup_function():
    assert client.post("/reset").json()["success"] is True


def last4(tracking):
    phone = str(CLEANED[CLEANED.tracking_number == tracking].iloc[0]["phone"])
    phone = phone[:-2] if phone.endswith(".0") else phone
    return "".join(c for c in phone if c.isdigit())[-4:]


# =================================================
# 1. Placeholder addresses
# =================================================

@pytest.mark.parametrize("value", ["same as before", "Same As Before", "  same as before  ", "SAME  AS  BEFORE"])
def test_same_as_before_is_rejected_everywhere(value):
    assert is_placeholder_address(value)
    assert not is_valid_delivery_address(value)
    _, note = validate_address(value)
    assert note and "Invalid delivery address" in note


@pytest.mark.parametrize("value", [
    "Villa 12, Al Wasl Road, Jumeirah, Dubai",              # English
    "فيلا 12، شارع الوصل، جميرا، دبي",                       # Arabic
    "Bldg 12, Apt 668، مدينة خليفة، Abu Dhabi",              # mixed
    "Office 214, Tower 13, Deira, Dubai (same as before)",   # contains the phrase but is a real address
])
def test_valid_addresses_still_accepted(value):
    assert is_valid_delivery_address(value)
    assert validate_address(value)[1] is None


def test_ex400463ae_requires_a_real_address_before_reschedule():
    tracking = "EX400463AE"  # In Transit, stored address "same as before"
    lookup = client.get(f"/shipment/{tracking}").json()
    assert lookup["success"] is True
    assert lookup["requires_address_first"] is True

    token = client.post("/verify", json={"tracking_number": tracking, "last4": last4(tracking)}).json()["verification_token"]
    blocked = client.post("/reschedule", json={
        "tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
        "verification_token": token, "customer_confirmed": True,
    }).json()
    assert blocked["success"] is False and blocked["decision"]["reason"] == "ADDRESS_REQUIRED"

    # The placeholder itself is not accepted as the "new" address.
    again = client.post("/repair-address", json={
        "tracking_number": tracking, "new_address": "  Same As Before ", "verification_token": token,
    }).json()
    assert again["success"] is False and again["reason"] == "INVALID_NEW_ADDRESS"
    assert client.get(f"/shipment/{tracking}").json()["shipment"]["delivery_address"] == "same as before"

    ok = client.post("/repair-address", json={
        "tracking_number": tracking, "new_address": "Villa 9, Al Safa 2, Dubai", "verification_token": token,
    }).json()
    assert ok["success"] is True
    done = client.post("/reschedule", json={
        "tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
        "verification_token": token, "customer_confirmed": True,
    }).json()
    assert done["success"] is True


def test_update_address_rejects_placeholder_without_changing_record():
    tracking = "EX400238AE"
    before = client.get(f"/shipment/{tracking}").json()["shipment"]
    token = client.post("/verify", json={"tracking_number": tracking, "last4": last4(tracking)}).json()["verification_token"]
    result = client.post("/update-address", json={
        "tracking_number": tracking, "new_address": "Same As Before",
        "verification_token": token, "customer_confirmed": True,
    }).json()
    assert result["success"] is False and result["decision"]["reason"] == "INVALID_NEW_ADDRESS"
    assert client.get(f"/shipment/{tracking}").json()["shipment"] == before


# =================================================
# 2. Dates
# =================================================

@pytest.mark.parametrize("raw, iso", [
    ("22 Aug 2026", "2026-08-22"),
    ("3 Sep 2026", "2026-09-03"),
    ("01 Jan 2026", "2026-01-01"),
    ("46175", "2026-06-02"),        # Excel serial (string, as stored in the file)
    (46226, "2026-07-23"),          # Excel serial (numeric cell)
    (46226.0, "2026-07-23"),
])
def test_unambiguous_formats_are_converted_to_iso(raw, iso):
    value, note = normalize_date_value(raw, "shipment date")
    assert value == iso and "normalized" in note
    assert validate_date(value, "shipment date") is None


@pytest.mark.parametrize("raw", ["0", "12", "99999", "46175.5", "-46175", "35000"])
def test_invalid_excel_serials_are_not_converted(raw):
    value, note = normalize_date_value(raw, "shipment date")
    assert value == raw and note is None
    assert validate_date(raw, "shipment date") is not None
    assert parse_excel_serial(raw) is None


@pytest.mark.parametrize("raw", ["07/06/2026", "07-04-26", "11.06.2026"])
def test_ambiguous_numeric_dates_still_escalate(raw):
    assert normalize_date_value(raw, "shipment date") == (raw, None)
    assert "Ambiguous" in validate_date(raw, "shipment date")


@pytest.mark.parametrize("raw", ["31 Feb 2026", "31/02/2026", "2026-02-30", "32 Aug 2026"])
def test_impossible_dates_are_rejected_not_replaced(raw):
    value, note = normalize_date_value(raw, "shipment date")
    assert value == raw and note is None  # never replaced with today or a fallback
    assert validate_date(raw, "shipment date") is not None


@pytest.mark.parametrize("raw", ["2026-08-02", "13/06/2026", "18/08/2026", "06-19-26"])
def test_existing_supported_formats_unchanged(raw):
    assert normalize_date_value(raw, "shipment date") == (raw, None)
    assert validate_date(raw, "shipment date") is None


def test_date_sequence_still_enforced_with_new_formats():
    assert validate_date_sequence("22 Aug 2026", "2026-08-20") is not None
    assert validate_date_sequence("46226", "2026-07-20") is not None   # 2026-07-23 shipment
    assert validate_date_sequence("18/08/2026", "22 Aug 2026") is None


def test_customer_date_with_explicit_year_is_respected():
    today = date(2026, 10, 3)
    assert extract_date("3 Sep 2026", today) == "2026-09-03"   # past -> rejected later, not moved to 2027
    assert extract_date("5 Jan 2027", today) == "2027-01-05"
    assert extract_date("12 October", today) == "2026-10-12"
    assert extract_date("31 Feb 2026", today) is None


@pytest.mark.parametrize("tracking", [
    "EX400003AE", "EX400183AE", "EX400209AE", "EX400443AE", "EX400950AE", "EX401367AE", "EX401606AE",
])
def test_previously_over_blocked_shipments_are_no_longer_blocked_by_format(tracking):
    lookup = client.get(f"/shipment/{tracking}").json()
    assert lookup["success"] is True, lookup.get("issue")
    assert client.post("/eligibility", json={"tracking_number": tracking, "intent": "reschedule"}).json()["allowed"]


def test_cleaned_file_has_no_text_month_or_serial_dates_left():
    for column in ("shipment_date", "last_attempt_date"):
        values = CLEANED[column].dropna().astype(str)
        assert not values.str.fullmatch(r"\d{1,2} [A-Za-z]{3,9} \d{4}").any()
        assert not values.str.fullmatch(r"\d{5}").any()


# =================================================
# 3/4. UAE mobile validation + normalization
# =================================================

VALID = [
    ("0501234567", "+971501234567"), ("0521234567", "+971521234567"),
    ("0541234567", "+971541234567"), ("0551234567", "+971551234567"),
    ("0561234567", "+971561234567"), ("0581234567", "+971581234567"),
    ("+971501234567", "+971501234567"), ("+971521234567", "+971521234567"),
    ("+971541234567", "+971541234567"), ("+971551234567", "+971551234567"),
    ("+971561234567", "+971561234567"), ("+971581234567", "+971581234567"),
    ("971501234567", "+971501234567"), ("971521234567", "+971521234567"),
    ("971541234567", "+971541234567"), ("971551234567", "+971551234567"),
    ("971561234567", "+971561234567"), ("971581234567", "+971581234567"),
    ("+971 50 123 4567", "+971501234567"), ("050 123 4567", "+971501234567"),
    ("050-123-4567", "+971501234567"),
]

INVALID = [
    "1234567890", "041234567", "0421234567", "+97141234567", "+966501234567",
    "+201001234567", "050123456", "05012345678", "05012abc67", "050-ABC-4567",
    "971401234567", "0000000000", "123", "", None, "   ", "+971 50 123 456",
    "050.123.4567", "+9715012345678", "0591234567", "0531234567",  # non-MVP prefixes for NEW numbers
]


@pytest.mark.parametrize("raw, canonical", VALID)
def test_valid_uae_mobiles_normalize_to_canonical(raw, canonical):
    assert normalize_uae_mobile(raw) == canonical


@pytest.mark.parametrize("raw", INVALID)
def test_invalid_numbers_are_rejected(raw):
    assert normalize_uae_mobile(raw) is None


def test_equivalent_formats_compare_equal():
    forms = ["0501234567", "971501234567", "+971501234567", "+971 50 123 4567", "00971501234567"]
    assert {normalize_uae_mobile(f) for f in forms} == {"+971501234567"}
    assert {normalize_registered_phone(f) for f in forms} == {"+971501234567"}


def test_registered_numbers_on_other_5x_prefixes_remain_usable():
    # Numbers already on file (e.g. 053) keep last-4 verification; only new
    # customer-provided numbers must use an MVP prefix.
    assert normalize_registered_phone(971536385467.0) == "+971536385467"
    assert normalize_uae_mobile("+971536385467") is None
    for junk in ("+97141234567", "+966501234567", "05012abc67", "0000000000"):
        assert normalize_registered_phone(junk) is None
        assert validate_phone(junk) is not None
    assert validate_phone(971536385467.0) is None


@pytest.mark.parametrize("bad", ["0421234567", "+966501234567", "05012abc67", "050123456", "0531234567", "0000000000"])
def test_invalid_customer_phone_is_not_stored_and_does_not_proceed(bad):
    tracking = "EX400380AE"  # no phone on file
    response = client.post("/collect-phone", json={"tracking_number": tracking, "phone_number": bad}).json()
    assert response["success"] is False and response["reason"] == "INVALID_PHONE"
    assert "verification_token" not in response
    assert "not a valid UAE mobile" in response["message"]
    lookup = client.get(f"/shipment/{tracking}").json()
    assert lookup["needs_phone_collection"] is True and lookup["shipment"]["phone"] is None
    if RUNTIME_FILE.exists():
        runtime = pd.read_excel(RUNTIME_FILE)
        assert pd.isna(runtime[runtime.tracking_number == tracking].iloc[0]["phone"])


def test_valid_customer_phone_is_stored_canonical_and_proceeds():
    tracking = "EX400380AE"
    response = client.post("/collect-phone", json={"tracking_number": tracking, "phone_number": "050-765-4321"}).json()
    assert response["success"] is True and response["phone"] == "+971507654321"
    runtime = pd.read_excel(RUNTIME_FILE, dtype=object)
    assert runtime[runtime.tracking_number == tracking].iloc[0]["phone"] == "+971507654321"
    result = client.post("/reschedule", json={
        "tracking_number": tracking, "new_delivery_date": IN_3_DAYS,
        "verification_token": response["verification_token"], "customer_confirmed": True,
    }).json()
    assert result["success"] is True


@pytest.mark.parametrize("form", ["{local}", "{intl}", "+{intl}", "+971 {a} {b} {c}"])
def test_find_by_phone_matches_any_equivalent_format(form):
    tracking = "EX400476AE"
    canonical = normalize_registered_phone(CLEANED[CLEANED.tracking_number == tracking].iloc[0]["phone"])
    national = canonical[4:]
    value = form.format(local="0" + national, intl="971" + national, a=national[:2], b=national[2:5], c=national[5:])
    found = client.post("/find-shipments", json={"phone_number": value}).json()
    assert found["success"] is True
    assert tracking in [s["tracking_number"] for s in found["shipments"]]


@pytest.mark.parametrize("bad", ["+97141234567", "+966501234567", "05012abc67", "123"])
def test_find_by_phone_rejects_malformed_numbers(bad):
    assert client.post("/find-shipments", json={"phone_number": bad}).json()["result"] == "INVALID_PHONE"


def test_verification_uses_normalized_registered_number():
    # EX400238AE is registered as +971536385467 (053 prefix): still verifiable.
    result = client.post("/verify", json={"tracking_number": "EX400238AE", "last4": "5467"}).json()
    assert result["verified"] is True


# =================================================
# 8. Decimal fields preserved
# =================================================

@pytest.mark.parametrize("raw, expected", [
    ("AED 125.50", 125.5), ("99.95", 99.95), ("0.00", 0.0), ("AED 0.00", 0.0), (125.5, 125.5), ("AED 1,250.75", 1250.75),
])
def test_cod_decimals_are_not_rounded(raw, expected):
    value, _ = normalize_cod(raw)
    assert value == expected and isinstance(value, float)


def test_api_returns_decimal_cod_and_weight_unchanged():
    row = CLEANED[(CLEANED.cod_amount_aed % 1 != 0) & (CLEANED.weight_kg % 1 != 0)
                  & CLEANED.tracking_number.isin(["EX401159AE"])].iloc[0]
    shipment = client.get(f"/shipment/{row.tracking_number}").json()["shipment"]
    assert shipment["cod_amount_aed"] == pytest.approx(float(row.cod_amount_aed), abs=0)
    assert shipment["weight_kg"] == pytest.approx(float(row.weight_kg), abs=0)
    assert shipment["cod_amount_aed"] % 1 != 0 and shipment["weight_kg"] % 1 != 0


def test_cleaned_file_keeps_decimals():
    assert (CLEANED.cod_amount_aed % 1 != 0).sum() > 100
    assert (CLEANED.weight_kg % 1 != 0).sum() > 500


# =================================================
# 7/9/10/11/12. Preserved safety behaviour
# =================================================

def test_invalid_weight_review_is_simulated_and_weight_never_changes():
    tracking = "EX400402AE"
    original_weight = float(CLEANED[CLEANED.tracking_number == tracking].iloc[0]["weight_kg"])
    lookup = client.get(f"/shipment/{tracking}").json()
    assert lookup["success"] is False and lookup["issue"]["handling"] == "INTERNAL_REVIEW"
    resolved = client.post(f"/review/{tracking}/resolve").json()
    assert "simulated" in resolved["simulation_note"]
    assert "simulated" in client.get(f"/review/{tracking}").json()["simulation_note"]
    after = client.get(f"/shipment/{tracking}").json()
    assert after["success"] is True  # continues only after review, re-read from data
    assert after["shipment"]["weight_kg"] == original_weight  # not guessed or changed


def test_sensitive_notes_never_returned():
    sensitive = CLEANED[CLEANED.notes.astype(str).str.contains("Gate code", na=False)].tracking_number
    for tracking in sensitive.head(15):
        body = json.dumps(client.get(f"/shipment/{tracking}").json())
        assert "Gate code" not in body and "4412" not in body and '"notes"' not in body
        assert "AI_Notes" not in body


def test_duplicates_test_records_and_ambiguous_dates_still_escalate():
    assert client.get("/shipment/EX400215AE").json()["result"] == "DUPLICATE"
    for tracking in ["TEST1001", "TEST1002"]:
        assert client.get(f"/shipment/{tracking}").json()["issue"]["code"] == "TEST_RECORD"
    assert client.get("/shipment/EX400009AE").json()["success"] is False
