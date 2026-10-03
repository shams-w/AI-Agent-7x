"""Read-only data audit of the shipment dataset.

* Reads data/ (raw) and outputs/..._AI_Cleaned.xlsx (reference). Writes nothing
  to either. Any runtime state goes to a throw-away FDE_RUNTIME_DIR.
* Each record is checked field-by-field, independently of the Data Agent's own
  notes, then run through the project's existing lookup/eligibility logic to
  see what the MVP would actually do with it.
* No values are inferred or corrected.

Run:  python audit/run_data_audit.py   -> audit/data_audit_records.csv + summary
"""

import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["FDE_RUNTIME_DIR"] = tempfile.mkdtemp(prefix="fde-audit-")
os.environ["FDE_INTENT_LLM"] = "off"

import pandas as pd  # noqa: E402

from backend.shipment_service import (  # noqa: E402
    can_reschedule_delivery,
    can_update_address,
    get_shipment,
    is_valid_delivery_address,
)
from backend.validators import MVP_MOBILE_PREFIXES, normalize_registered_phone  # noqa: E402

from backend import shipment_service  # noqa: E402

# The project re-reads the Excel file on every lookup. For the audit, read it
# once with the project's own default parsing and serve copies (read-only).
_PROJECT_VIEW = pd.read_excel(ROOT / "outputs" / "FDE_Assignment_Shipment_Dataset_AI_Cleaned.xlsx")
shipment_service.load_shipments = lambda: _PROJECT_VIEW.copy()

RAW = pd.read_excel(ROOT / "data" / "FDE_Assignment_Shipment_Dataset.xlsx", dtype=object)
CLEAN = pd.read_excel(ROOT / "outputs" / "FDE_Assignment_Shipment_Dataset_AI_Cleaned.xlsx", dtype=object)
assert len(RAW) == len(CLEAN)

CANONICAL = {"Delivered", "Failed Delivery", "Scheduled for Redelivery",
             "In Transit", "Out for Delivery", "Returned to Sender"}
EMIRATES = {"Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah", "Fujairah", "Umm Al Quwain"}
SENSITIVE = re.compile(r"\b(gate|door|access|pin)\s*code\b|\bpassword\b|\botp\b", re.I)

# Issue catalogue: code -> (category, affects_mvp, safe_to_ignore,
#                           customer_input, human_review, handling)
CATALOGUE = {
    "STATUS_FORMAT_VARIANT": ("Normal / valid", "No", "Yes", "No", "No",
        "Casing/synonym only (e.g. DELIVERED, delivered_ok, Transit). Already normalized by the Data Agent; no action."),
    "STATUS_UNDELIVERED_MAPPED": ("Unknown / needs review", "Yes", "No", "No", "Yes (light)",
        "Mapped to Failed Delivery by the verified project fix because delivery_attempts >= 1. Ops should confirm the source system's meaning of 'Undelivered'."),
    "TEST_RECORD": ("Invalid data", "Yes (blocked)", "No", "No", "Yes",
        "Already hard-blocked and hidden from phone lookup. Remove from the production extract."),
    "MISSING_PHONE": ("Missing data", "Yes", "No", "Yes", "No",
        "Eligible shipments: customer provides a UAE mobile via the MVP fallback (format-checked only; production needs OTP). Do not infer."),
    "PLACEHOLDER_PHONE": ("Invalid data", "Yes", "No", "Yes", "No",
        "Not a usable UAE mobile; treated like a missing phone. Do not guess the real number."),
    "REGISTERED_PHONE_NON_MVP_PREFIX": ("Unknown / needs review", "No (still verifiable)", "Yes for MVP", "No", "Optional",
        "Registered number on 051/053/057/059. Still used for last-4 verification (decision 2026-10-03); a NEW number from a customer must use 050/052/054/055/056/058. Data owner may confirm the prefix list."),
    "DATE_NORMALIZED": ("Normal / valid", "No (now accepted)", "Yes", "No", "No",
        "Unambiguous '22 Aug 2026' / Excel-serial date converted to ISO by the Data Agent."),
    "MISSING_ADDRESS": ("Missing data", "Yes", "No", "Yes", "Only if Out for Delivery",
        "Reschedule: customer provides the address first (existing prerequisite). Out for Delivery: existing internal-review rule."),
    "PLACEHOLDER_ADDRESS": ("Invalid data", "Yes", "No", "Yes", "Only if Out for Delivery",
        "Same as missing address (values like asdf, call me, -, .)."),
    "PLACEHOLDER_ADDRESS_UNDETECTED": ("Invalid data", "Yes (incorrect allow)", "No", "Yes", "Yes",
        "'same as before' passes the MVP address check (>= 10 chars, not in the placeholder list), so the customer is never asked for an address. Recommend adding it to the existing placeholder list, which is a rule change, so it is not applied here."),
    "INVALID_WEIGHT": ("Invalid data", "Yes (blocked)", "No", "No", "Yes",
        "Existing internal-review flow. Weight is never guessed."),
    "COD_FORMAT": ("Normal / valid", "No", "Yes", "No", "No",
        "'AED 123.45' strings were normalized to numbers by the Data Agent; no action."),
    "COD_OUTLIER": ("Unknown / needs review", "Yes (blocked)", "No", "No", "Yes",
        "99999 AED retained and escalated by the existing rule."),
    "DATE_UNSUPPORTED_BUT_UNAMBIGUOUS": ("Invalid data", "Yes (possibly over-blocking)", "No", "No", "Yes",
        "'23 Jun 2026' or an Excel serial like '46175' is rejected as an unsupported format and blocks the shipment, although the value is not ambiguous. Recommend extending the parser after review. Not applied."),
    "DATE_AMBIGUOUS": ("Invalid data", "Yes (blocked)", "No", "No", "Yes",
        "Day/month cannot be determined (e.g. 07/06/2026, 07-04-26). Correctly escalated; the source system must confirm."),
    "DATE_SEQUENCE": ("Contradictory data", "Yes (blocked)", "No", "No", "Yes",
        "Last attempt before shipment date. Correctly escalated."),
    "DELIVERED_ZERO_ATTEMPTS": ("Contradictory data", "Low (Delivered is ineligible anyway)", "No", "No", "Yes",
        "Existing cross-field rule escalates it. Historical data; do not 'fix' it."),
    "ZERO_ATTEMPTS_WITH_ATTEMPT_DATE": ("Contradictory data", "Yes when status is eligible", "No", "No", "Yes",
        "delivery_attempts = 0 but a last_attempt_date exists. Not covered by any project rule, so eligible records are NOT blocked today."),
    "REDELIVERY_WITHOUT_ATTEMPT": ("Unknown / needs review", "Yes (eligible today)", "No", "No", "Yes",
        "'Scheduled for Redelivery' with 0 attempts. No project rule covers it; flag for ops, do not create a rule here."),
    "IN_TRANSIT_WITH_ATTEMPTS": ("Unknown / needs review", "Low (eligible today)", "Yes for MVP", "No", "Optional",
        "In Transit after 1+ attempts (possibly back at hub). No project rule; informational."),
    "NO_ATTEMPT_YET_NO_DATE": ("Normal / valid", "Cosmetic", "Yes", "No", "No",
        "0 attempts and no last-attempt date is expected. The project still shows a 'limited history' warning to the customer, which is harmless but unnecessary."),
    "DELIVERED_MISSING_FIELD": ("Missing data", "No (Delivered is ineligible)", "Yes", "No", "No",
        "Historical Delivered record missing phone, address or date. Do not backfill; no MVP action is possible on it."),
    "SENSITIVE_NOTE": ("Normal / valid", "No (hidden)", "Yes (already hidden)", "No", "No",
        "Gate code in notes. Valid operational data; never exposed by the API. Keep it hidden."),
    "DUPLICATE_CONFLICTING": ("Contradictory data", "Yes (blocked)", "No", "No", "Yes",
        "Same tracking number with different statuses. Existing rule refuses to pick one; ops must merge."),
    "DUPLICATE_SAME_STATUS": ("Unknown / needs review", "Yes (blocked)", "No", "No", "Yes",
        "Same tracking number repeated with the same status. Still blocked (cannot tell which row is current)."),
    "NAME_WHITESPACE": ("Normal / valid", "No", "Yes", "No", "No",
        "Whitespace trimmed by the Data Agent."),
}


def date_format(value):
    if pd.isna(value):
        return "NULL"
    s = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return "ISO"
    if re.fullmatch(r"\d{5}", s):
        return "EXCEL_SERIAL"
    if re.fullmatch(r"\d{1,2} [A-Za-z]{3,9} \d{4}", s):
        return "D_MON_YYYY"
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a <= 12 and b <= 12:
            return "AMBIGUOUS"
        return "UNAMBIGUOUS_NUMERIC"
    return "OTHER"


def to_date(value):
    fmt = date_format(value)
    s = str(value).strip()
    try:
        if fmt == "ISO":
            return pd.to_datetime(s, format="%Y-%m-%d")
        if fmt == "D_MON_YYYY":
            return pd.to_datetime(s, format="%d %b %Y")
        if fmt == "EXCEL_SERIAL":
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(s))
        if fmt == "UNAMBIGUOUS_NUMERIC":
            a, b, y = [int(x) for x in re.split(r"[/.-]", s)]
            y = y + 2000 if y < 100 else y
            return pd.Timestamp(y, b, a) if a > 12 else pd.Timestamp(y, a, b)
    except Exception:
        return None
    return None


def mvp_outcome(tracking):
    lookup = get_shipment(tracking)
    if not lookup["success"]:
        code = (lookup.get("issue") or {}).get("code") or lookup["result"]
        if code == "TEST_RECORD":
            return "BLOCKED_TEST_RECORD", code
        if lookup.get("review_required"):
            return "INTERNAL_REVIEW", code
        if lookup["result"] == "DUPLICATE":
            return "ESCALATED_DUPLICATE", code
        return "ESCALATED_DATA_REVIEW", code
    resched = can_reschedule_delivery(tracking)
    address = can_update_address(tracking)
    if not resched["allowed"] and not address["allowed"]:
        return "BLOCKED_BY_STATUS", resched["reason"]
    needs = []
    if lookup.get("needs_phone_collection"):
        needs.append("phone")
    if lookup.get("requires_address_first"):
        needs.append("address")
    return ("ELIGIBLE_NEEDS_CUSTOMER_INPUT" if needs else "ELIGIBLE"), "+".join(needs) or "OK"


def main():
    dup_groups = CLEAN.groupby(CLEAN["tracking_number"].astype(str).str.strip().str.upper())
    dup_info = {}
    for key, group in dup_groups:
        if len(group) > 1:
            dup_info[key] = len(set(group["status"].astype(str))) > 1

    rows = []
    for i in range(len(CLEAN)):
        raw, row = RAW.iloc[i], CLEAN.iloc[i]
        tracking = str(row["tracking_number"]).strip().upper()
        status = str(row["status"]).strip()
        attempts = int(row["delivery_attempts"])
        issues = []

        is_test = tracking.startswith("TEST") or status.upper() == "TEST"
        if is_test:
            issues.append("TEST_RECORD")

        raw_status = str(raw["status"])
        if raw_status.strip().lower() == "undelivered":
            issues.append("STATUS_UNDELIVERED_MAPPED")
        elif raw_status != status and not is_test:
            issues.append("STATUS_FORMAT_VARIANT")

        if tracking in dup_info:
            issues.append("DUPLICATE_CONFLICTING" if dup_info[tracking] else "DUPLICATE_SAME_STATUS")

        # phone
        phone = row["phone"]
        if pd.isna(phone) or str(phone).strip() == "":
            phone_issue = "MISSING_PHONE"
        elif normalize_registered_phone(phone) is None:
            phone_issue = "PLACEHOLDER_PHONE"
        else:
            phone_issue = None
            if normalize_registered_phone(phone)[4:6] not in MVP_MOBILE_PREFIXES and not is_test:
                issues.append("REGISTERED_PHONE_NON_MVP_PREFIX")

        # address
        address = row["delivery_address"]
        if pd.isna(address) or str(address).strip() == "":
            addr_issue = "MISSING_ADDRESS"
        elif not is_valid_delivery_address(address):
            addr_issue = "PLACEHOLDER_ADDRESS"
        elif str(address).strip().lower() in {"same as before", "same", "as before", "old address"}:
            addr_issue = "PLACEHOLDER_ADDRESS_UNDETECTED"
        else:
            addr_issue = None

        # last attempt / attempts
        last_attempt_missing = pd.isna(row["last_attempt_date"])

        if status == "Delivered" and not is_test and (phone_issue or addr_issue or last_attempt_missing):
            issues.append("DELIVERED_MISSING_FIELD")
            phone_issue = addr_issue = None  # counted once, as historical

        if phone_issue and not is_test:
            issues.append(phone_issue)
        if addr_issue and not is_test:
            issues.append(addr_issue)

        if not is_test:
            if last_attempt_missing and attempts == 0 and status != "Delivered":
                issues.append("NO_ATTEMPT_YET_NO_DATE")
            if not last_attempt_missing and attempts == 0:
                issues.append("ZERO_ATTEMPTS_WITH_ATTEMPT_DATE")
            if status == "Delivered" and attempts == 0:
                issues.append("DELIVERED_ZERO_ATTEMPTS")
            if status == "Scheduled for Redelivery" and attempts == 0:
                issues.append("REDELIVERY_WITHOUT_ATTEMPT")
            if status == "In Transit" and attempts > 0:
                issues.append("IN_TRANSIT_WITH_ATTEMPTS")

        # weight / COD
        weight = pd.to_numeric(row["weight_kg"], errors="coerce")
        if (pd.isna(weight) or weight <= 0) and not is_test:
            issues.append("INVALID_WEIGHT")
        if isinstance(raw["cod_amount_aed"], str) and "AED" in raw["cod_amount_aed"].upper():
            issues.append("COD_FORMAT")
        cod = pd.to_numeric(row["cod_amount_aed"], errors="coerce")
        if pd.notna(cod) and cod > 10000 and not is_test:
            issues.append("COD_OUTLIER")

        # dates
        for column in ("shipment_date", "last_attempt_date"):
            if date_format(raw[column]) in ("D_MON_YYYY", "EXCEL_SERIAL") and date_format(row[column]) == "ISO" and not is_test:
                issues.append("DATE_NORMALIZED")
                break
        date_issue = set()
        for column in ("shipment_date", "last_attempt_date"):
            fmt = date_format(row[column])
            if fmt in ("D_MON_YYYY", "EXCEL_SERIAL"):
                date_issue.add("DATE_UNSUPPORTED_BUT_UNAMBIGUOUS")
            elif fmt in ("AMBIGUOUS", "OTHER"):
                date_issue.add("DATE_AMBIGUOUS")
        ship, last = to_date(row["shipment_date"]), to_date(row["last_attempt_date"])
        if ship is not None and last is not None and last < ship:
            date_issue.add("DATE_SEQUENCE")
        if not is_test:
            issues.extend(sorted(date_issue))

        # notes / name
        if pd.notna(row["notes"]) and SENSITIVE.search(str(row["notes"])):
            issues.append("SENSITIVE_NOTE")
        if isinstance(raw["customer_name"], str) and raw["customer_name"] != raw["customer_name"].strip():
            issues.append("NAME_WHITESPACE")

        outcome, outcome_detail = mvp_outcome(tracking)

        # Only "ignorable" issues => normal record.
        ignorable = {code for code, meta in CATALOGUE.items() if meta[0] == "Normal / valid"}
        # Informational only (decision 2026-10-03): reported, not a material issue.
        ignorable.add("REGISTERED_PHONE_NON_MVP_PREFIX")
        material = [code for code in issues if code not in ignorable]

        incorrect_allow = outcome.startswith("ELIGIBLE") and any(
            code in material for code in (
                "PLACEHOLDER_ADDRESS_UNDETECTED", "ZERO_ATTEMPTS_WITH_ATTEMPT_DATE",
                "REDELIVERY_WITHOUT_ATTEMPT",
            )
        )
        hard_reasons = set(material) - {
            "DATE_UNSUPPORTED_BUT_UNAMBIGUOUS", "MISSING_PHONE", "PLACEHOLDER_PHONE",
            "MISSING_ADDRESS", "PLACEHOLDER_ADDRESS", "IN_TRANSIT_WITH_ATTEMPTS",
            "STATUS_UNDELIVERED_MAPPED", "DELIVERED_MISSING_FIELD",
        }
        possibly_over_blocked = (
            outcome == "ESCALATED_DATA_REVIEW"
            and "DATE_UNSUPPORTED_BUT_UNAMBIGUOUS" in material
            and not hard_reasons
            and status in {"Failed Delivery", "Scheduled for Redelivery", "In Transit"}
        )

        rows.append({
            "row": i + 2,  # Excel row number
            "tracking_number": tracking,
            "status": status,
            "raw_status": raw_status,
            "delivery_attempts": attempts,
            "issues": "|".join(issues),
            "categories": "|".join(sorted({CATALOGUE[c][0] for c in issues})) or "Normal / valid",
            "record_class": "Normal / valid" if not material else "Has issues",
            "mvp_outcome": outcome,
            "mvp_outcome_detail": outcome_detail,
            "risk_incorrect_allow": incorrect_allow,
            "risk_over_block": possibly_over_blocked,
            "needs_human_review": any(CATALOGUE[c][4].startswith("Yes") for c in material)
                or (status == "Out for Delivery" and any(c in material for c in ("MISSING_ADDRESS", "PLACEHOLDER_ADDRESS"))),
            "needs_customer_input": outcome == "ELIGIBLE_NEEDS_CUSTOMER_INPUT",
        })

    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "audit" / "data_audit_records.csv", index=False)

    issue_counter = Counter(code for value in out["issues"] for code in value.split("|") if code)
    summary = {
        "records": len(out),
        "unique_tracking_numbers": int(CLEAN["tracking_number"].nunique()),
        "record_class": out["record_class"].value_counts().to_dict(),
        "issue_occurrences_by_category": dict(Counter(
            CATALOGUE[code][0] for value in out["issues"] for code in value.split("|") if code
        )),
        "records_by_category": {
            cat: int(out["categories"].str.contains(re.escape(cat)).sum())
            for cat in ["Normal / valid", "Missing data", "Invalid data", "Contradictory data", "Unknown / needs review"]
        },
        "issues": {code: issue_counter.get(code, 0) for code in CATALOGUE},
        "mvp_outcome": out["mvp_outcome"].value_counts().to_dict(),
        "needs_human_review": int(out["needs_human_review"].sum()),
        "needs_customer_input": int(out["needs_customer_input"].sum()),
        "risk_incorrect_allow": out[out["risk_incorrect_allow"]]["tracking_number"].tolist(),
        "risk_over_block": out[out["risk_over_block"]]["tracking_number"].tolist(),
        "by_issue": {
            code: sorted(set(out[out["issues"].str.split("|").apply(lambda xs, c=code: c in xs)]["tracking_number"]))
            for code in CATALOGUE
        },
        "outcome_by_issue": {
            code: out[out["issues"].str.split("|").apply(lambda xs, c=code: c in xs)]["mvp_outcome"].value_counts().to_dict()
            for code in CATALOGUE
        },
    }
    (ROOT / "audit" / "data_audit_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k not in ("by_issue",)}, indent=1, default=str))


if __name__ == "__main__":
    main()
