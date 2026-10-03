import re

import pandas as pd
import time

from backend.validators import (
    is_placeholder_address,
    normalize_registered_phone,
    normalize_uae_mobile,
)
from pathlib import Path


# =================================================
# PATHS
# =================================================

from backend.config import BASE_DIR, CLEANED_FILE, RUNTIME_FILE  # noqa: E402


# =================================================
# LOAD DATA
# =================================================

def discard_stale_runtime():
    """
    The runtime copy is derived from the cleaned dataset. If the Data Agent
    regenerated the cleaned file after the runtime copy was made, the runtime
    copy is based on outdated source data and is discarded.
    """
    try:
        if (
            RUNTIME_FILE.exists()
            and CLEANED_FILE.exists()
            and RUNTIME_FILE.stat().st_mtime < CLEANED_FILE.stat().st_mtime
        ):
            RUNTIME_FILE.unlink()
    except OSError:
        pass


def load_shipments():
    """
    Load the CURRENT operational shipment state.

    Priority:
    1. Runtime dataset if it exists (and is not older than the cleaned source)
    2. Cleaned source dataset as fallback
    """

    discard_stale_runtime()

    if RUNTIME_FILE.exists():
        return pd.read_excel(
            RUNTIME_FILE
        )

    if CLEANED_FILE.exists():
        return pd.read_excel(
            CLEANED_FILE
        )

    raise FileNotFoundError(
        "No shipment dataset was found. "
        "Run backend/data_agent.py first."
    )



def save_shipments(df):
    """Save only the runtime copy. The cleaned source remains untouched."""
    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(RUNTIME_FILE, index=False)


def _find_runtime_index(df, tracking_number):
    tracking = normalize_tracking_number(tracking_number)
    if tracking is None or "tracking_number" not in df.columns:
        return []
    matches = df.index[
        df["tracking_number"].astype(str).str.strip().str.upper() == tracking
    ].tolist()
    return matches


def is_valid_uae_mobile(value):
    """Strict rule for a number the CUSTOMER provides: structurally valid UAE
    mobile on an MVP prefix (050/052/054/055/056/058). Format check only; it
    does not prove ownership."""
    return normalize_uae_mobile(value) is not None


def has_usable_registered_phone(value):
    """A number already on file that normalizes to a UAE mobile
    (+9715XXXXXXXX). Used for last-4 verification and lookups."""
    return normalize_registered_phone(value) is not None


def is_valid_tracking_format(value):
    """Validate the expected shipment identifier shape without guessing corrections."""
    tracking = normalize_tracking_number(value)
    if tracking is None:
        return False
    return bool(re.fullmatch(r"[A-Z]{2}\d{6}[A-Z]{2}", tracking))


def is_valid_delivery_address(value):
    if value is None or pd.isna(value):
        return False
    address = str(value).strip()
    if len(address) < 10:
        return False
    return not is_placeholder_address(address)


def collect_customer_phone(tracking_number, phone_number):
    """
    Save a customer-provided UAE mobile number to the runtime copy only.
    This is a prototype contact-data repair, NOT production-grade identity proof.
    """
    # Security: this fallback is ONLY for shipments that have no usable
    # registered phone. If a valid phone exists, the customer must verify
    # against it — otherwise anyone could overwrite it and obtain a token.
    lookup = get_shipment(tracking_number)
    if not lookup.get("success"):
        return {
            "success": False,
            "reason": "SHIPMENT_NOT_ELIGIBLE",
            "message": "This shipment cannot use the contact-number fallback.",
        }
    if not lookup.get("needs_phone_collection"):
        return {
            "success": False,
            "reason": "PHONE_ALREADY_REGISTERED",
            "message": "This shipment already has a registered mobile number. Please verify with its last 4 digits.",
        }

    normalized = normalize_uae_mobile(phone_number)
    if normalized is None:
        # Nothing is stored for an invalid number.
        return {
            "success": False,
            "reason": "INVALID_PHONE",
            "message": (
                "That is not a valid UAE mobile number. Please enter it again, "
                "for example 05XXXXXXXX or +9715XXXXXXXX (050, 052, 054, 055, 056 or 058)."
            ),
        }

    df = load_shipments()
    matches = _find_runtime_index(df, tracking_number)
    if len(matches) != 1:
        return {
            "success": False,
            "reason": "SHIPMENT_NOT_UNIQUE",
            "message": "The shipment could not be uniquely identified.",
        }

    # Excel often loads an all-numeric phone column as float64.
    # Cast only the runtime column to object before storing a validated
    # customer-provided phone string so we preserve digits safely.
    if "phone" in df.columns:
        df["phone"] = df["phone"].astype("object")

    df.at[matches[0], "phone"] = normalized
    if "agent_phone_source" not in df.columns:
        df["agent_phone_source"] = None
    df.at[matches[0], "agent_phone_source"] = "CUSTOMER_PROVIDED_MVP"
    save_shipments(df)

    return {
        "success": True,
        "phone": normalized,
        "message": "The contact number was accepted for this MVP session.",
    }


def repair_delivery_address(tracking_number, new_address):
    """Repair a missing/invalid runtime address before a reschedule workflow."""
    # Security: this is a prerequisite repair, not a general address-change
    # path. It must not bypass evaluate_address_update() (status rules +
    # explicit confirmation) for shipments that already have a valid address
    # or are not eligible for rescheduling.
    eligibility = can_reschedule_delivery(tracking_number)
    if not eligibility.get("allowed") or not eligibility.get("requires_address_first"):
        return {
            "success": False,
            "reason": "ADDRESS_REPAIR_NOT_ALLOWED",
            "message": "A prerequisite address can only be added when the shipment is eligible and has no usable address.",
        }

    if not is_valid_delivery_address(new_address):
        return {
            "success": False,
            "reason": "INVALID_NEW_ADDRESS",
            "message": "Please enter a complete delivery address.",
        }

    df = load_shipments()
    matches = _find_runtime_index(df, tracking_number)
    if len(matches) != 1:
        return {
            "success": False,
            "reason": "SHIPMENT_NOT_UNIQUE",
            "message": "The shipment could not be uniquely identified.",
        }

    previous = df.at[matches[0], "delivery_address"] if "delivery_address" in df.columns else None
    df.at[matches[0], "delivery_address"] = str(new_address).strip()
    if "agent_address_source" not in df.columns:
        df["agent_address_source"] = None
    df.at[matches[0], "agent_address_source"] = "CUSTOMER_PROVIDED_PREREQUISITE"
    save_shipments(df)

    return {
        "success": True,
        "previous_address": None if pd.isna(previous) else str(previous),
        "new_address": str(new_address).strip(),
        "message": "The delivery address was captured successfully.",
    }


REVIEW_SIMULATION_NOTE = (
    "For the MVP, internal operational review is simulated. "
    "The AI does not invent or correct the source operational value."
)


def create_weight_review_case(tracking_number, issue_code="INVALID_WEIGHT"):
    """Create/reuse a runtime-only internal review case.

    The historical function name is kept for compatibility with the existing
    API/tests, but the review can now represent more than one operational issue.
    """
    df = load_shipments()
    matches = _find_runtime_index(df, tracking_number)
    if len(matches) != 1:
        return {"success": False, "reason": "SHIPMENT_NOT_UNIQUE"}

    idx = matches[0]
    for column in [
        "agent_review_status",
        "agent_review_issue",
        "agent_review_started_at",
    ]:
        if column not in df.columns:
            df[column] = None

    normalized_issue = str(issue_code or "DATA_REVIEW_REQUIRED").strip().upper()
    current = df.at[idx, "agent_review_status"]
    current_issue = df.at[idx, "agent_review_issue"]
    current_issue = None if pd.isna(current_issue) else str(current_issue).strip().upper()

    # Start a fresh review when there is no active review, or when the issue
    # changed. A previously resolved *different* issue must not suppress a new one.
    if (
        pd.isna(current)
        or str(current).strip().upper() not in {"UNDER_REVIEW", "RESOLVED"}
        or current_issue != normalized_issue
    ):
        df.at[idx, "agent_review_status"] = "UNDER_REVIEW"
        df.at[idx, "agent_review_issue"] = normalized_issue
        df.at[idx, "agent_review_started_at"] = time.time()
        save_shipments(df)

    return {
        "success": True,
        "tracking_number": normalize_tracking_number(tracking_number),
        "status": str(df.at[idx, "agent_review_status"]).strip().upper(),
        "issue": normalized_issue,
    }


def get_review_status(tracking_number):
    """
    Return the runtime review status.

    Demo behavior: an internal operational review is simulated as completed
    after 8 seconds. Source operational values are never invented or silently
    corrected. The frontend polls this endpoint and notifies the customer when
    the review becomes RESOLVED.
    """
    df = load_shipments()
    matches = _find_runtime_index(df, tracking_number)
    if len(matches) != 1:
        return {"success": False, "reason": "SHIPMENT_NOT_UNIQUE"}

    idx = matches[0]
    status = None
    issue = None

    if "agent_review_status" in df.columns:
        value = df.at[idx, "agent_review_status"]
        status = None if pd.isna(value) else str(value).strip().upper()

    if "agent_review_issue" in df.columns:
        value = df.at[idx, "agent_review_issue"]
        issue = None if pd.isna(value) else str(value).strip().upper()

    # MVP demo only: simulate the internal operations team completing
    # the review after a short delay. This is NOT an automatic correction
    # of the source shipment data.
    if status == "UNDER_REVIEW" and "agent_review_started_at" in df.columns:
        started = df.at[idx, "agent_review_started_at"]
        try:
            started = float(started)
        except (TypeError, ValueError):
            started = None

        if started is not None and time.time() - started >= 8:
            df.at[idx, "agent_review_status"] = "RESOLVED"
            save_shipments(df)
            status = "RESOLVED"

    return {
        "success": True,
        "tracking_number": normalize_tracking_number(tracking_number),
        "status": status or "NONE",
        "issue": issue,
        "demo_auto_resolution": True,
        "simulation_note": REVIEW_SIMULATION_NOTE,
    }


def resolve_weight_review(tracking_number):
    """Mark the current internal-demo review as resolved.

    The historical function name is kept for API compatibility. Resolution
    records approval/review only; it does not invent or rewrite source data.
    """
    df = load_shipments()
    matches = _find_runtime_index(df, tracking_number)
    if len(matches) != 1:
        return {"success": False, "reason": "SHIPMENT_NOT_UNIQUE"}
    idx = matches[0]
    if "agent_review_status" not in df.columns:
        df["agent_review_status"] = None
    if "agent_review_issue" not in df.columns:
        df["agent_review_issue"] = None

    issue = df.at[idx, "agent_review_issue"]
    issue = "DATA_REVIEW_REQUIRED" if pd.isna(issue) else str(issue).strip().upper()
    df.at[idx, "agent_review_status"] = "RESOLVED"
    df.at[idx, "agent_review_issue"] = issue
    save_shipments(df)
    return {
        "success": True,
        "tracking_number": normalize_tracking_number(tracking_number),
        "status": "RESOLVED",
        "issue": issue,
        "message": "The shipment review was marked as resolved.",
        "simulation_note": REVIEW_SIMULATION_NOTE,
    }


# =================================================
# NORMALIZATION HELPERS
# =================================================

def normalize_tracking_number(
    tracking_number
):
    if tracking_number is None:
        return None

    tracking = str(
        tracking_number
    ).strip().upper()

    return tracking or None


def normalize_phone_digits(value):
    """Legacy digit-only normalization (kept for compatibility).
    Validation and comparison use backend.validators instead."""
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]

    digits = "".join(character for character in text if character.isdigit())
    if not digits:
        return None

    if digits.startswith("00"):
        digits = digits[2:]

    if len(digits) == 10 and digits.startswith("05"):
        digits = "971" + digits[1:]

    return digits or None


def to_python_value(value):
    """
    Convert pandas/numpy values into normal Python values.
    """

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    return value


def mask_tracking_number(value):
    """
    EX400238AE -> EX****38AE
    """

    if value is None:
        return None

    tracking = str(
        value
    ).strip().upper()

    if len(tracking) <= 6:
        return tracking

    return (
        tracking[:2]
        + "*" * max(
            len(tracking) - 6,
            1
        )
        + tracking[-4:]
    )



# =================================================
# DATA QUALITY HANDLING
# =================================================

def classify_data_quality_issue(ai_notes):
    """
    Convert internal Data Agent notes into one SAFE handling decision.

    Important:
    - Raw AI_Notes are never returned to the customer.
    - A row can contain more than one issue.
    - Blocking issues always take priority over non-blocking warnings.
    - Formatting-only fixes do not become customer-facing errors.
    """

    text = (
        ""
        if ai_notes is None or pd.isna(ai_notes)
        else str(ai_notes).strip().lower()
    )

    if not text:
        return {
            "code": "DATA_REVIEW_REQUIRED",
            "title": "Shipment data needs review",
            "message": (
                "This shipment contains data that cannot be "
                "safely resolved automatically."
            ),
            "handling": "ESCALATE",
            "blocking": True,
        }

    candidates = []

    def add_issue(
        priority,
        code,
        title,
        message,
        handling,
        blocking,
        terms,
    ):
        if any(
            term in text
            for term in terms
        ):
            candidates.append(
                {
                    "priority": priority,
                    "code": code,
                    "title": title,
                    "message": message,
                    "handling": handling,
                    "blocking": blocking,
                }
            )

    # -------------------------------------------------
    # Highest-priority hard blocks
    # -------------------------------------------------

    add_issue(
        10,
        "TEST_RECORD",
        "Test record blocked",
        (
            "This record is marked as test data and cannot "
            "be used for customer actions."
        ),
        "BLOCK",
        True,
        [
            "test/dummy record detected",
            "test record",
            "dummy record",
            "test tracking",
            "status test",
        ],
    )

    add_issue(
        20,
        "INVALID_TRACKING_DATA",
        "Tracking data needs review",
        (
            "The shipment tracking data is not reliable enough "
            "for an automatic operational change."
        ),
        "ESCALATE",
        True,
        [
            "missing tracking number",
            "invalid or unexpected tracking number format",
            "invalid tracking",
            "tracking format",
        ],
    )

    add_issue(
        30,
        "MISSING_STATUS",
        "Shipment status unavailable",
        (
            "The shipment status is missing, so I cannot safely "
            "determine whether an operational change is allowed."
        ),
        "ESCALATE",
        True,
        [
            "missing shipment status",
        ],
    )

    add_issue(
        31,
        "UNKNOWN_STATUS",
        "Shipment status needs review",
        (
            "The recorded shipment status is not recognised, so I cannot "
            "safely determine whether an operational change is allowed."
        ),
        "ESCALATE",
        True,
        [
            "unrecognized shipment status",
        ],
    )

    # -------------------------------------------------
    # Identity / verification
    # -------------------------------------------------

    add_issue(
        40,
        "MISSING_PHONE",
        "Customer verification unavailable",
        (
            "The shipment does not have a registered mobile "
            "number that can be used for safe verification."
        ),
        "ESCALATE",
        True,
        [
            "missing phone number",
            "missing phone",
            "phone missing",
            "blank phone",
            "no phone",
        ],
    )

    add_issue(
        41,
        "INVALID_PHONE",
        "Customer verification unavailable",
        (
            "The registered mobile number appears invalid, "
            "so I cannot use it for identity verification."
        ),
        "ESCALATE",
        True,
        [
            "invalid or placeholder phone number",
            "invalid phone",
            "fake phone",
            "placeholder phone",
            "0000000000",
        ],
    )

    # -------------------------------------------------
    # Date / timeline integrity
    # -------------------------------------------------

    add_issue(
        50,
        "INVALID_TIMELINE",
        "Shipment timeline needs review",
        (
            "I found conflicting shipment dates, so I will not "
            "use the affected timeline to make an automatic change."
        ),
        "ESCALATE",
        True,
        [
            "illogical date sequence detected",
            "invalid date sequence",
            "before shipment date",
            "date sequence",
            "conflicting date",
        ],
    )

    add_issue(
        51,
        "INVALID_SHIPMENT_DATE",
        "Shipment date needs review",
        (
            "The shipment date is missing, invalid, or ambiguous, "
            "so the record requires review before an automated change."
        ),
        "ESCALATE",
        True,
        [
            "missing shipment date",
            "ambiguous shipment date",
            "invalid shipment date",
            "invalid or unsupported shipment date format",
            "impossible shipment date",
            "impossible or unrecognised shipment date",
            "invalid excel serial shipment date",
        ],
    )

    add_issue(
        52,
        "INVALID_LAST_ATTEMPT_DATE",
        "Delivery-attempt date needs review",
        (
            "The recorded delivery-attempt date is invalid or ambiguous, "
            "so the affected shipment timeline requires review."
        ),
        "ESCALATE",
        True,
        [
            "ambiguous last attempt date",
            "invalid last attempt date",
            "invalid or unsupported last attempt date format",
            "impossible last attempt date",
            "impossible or unrecognised last attempt date",
            "invalid excel serial last attempt date",
        ],
    )

    # -------------------------------------------------
    # Address quality
    # -------------------------------------------------

    add_issue(
        60,
        "INVALID_ADDRESS",
        "Delivery address needs review",
        (
            "The stored delivery address appears missing, incomplete, "
            "or non-operational and should not be trusted automatically."
        ),
        "ESCALATE",
        True,
        [
            "missing delivery address",
            "invalid delivery address detected",
            "invalid address",
            "placeholder address",
            "address incomplete",
            "n/a address",
        ],
    )

    # -------------------------------------------------
    # Operational shipment data
    # -------------------------------------------------

    add_issue(
        70,
        "INVALID_WEIGHT",
        "Shipment weight needs review",
        (
            "The shipment weight is missing or invalid, so the record "
            "requires review before an automated change."
        ),
        "ESCALATE",
        True,
        [
            "missing shipment weight",
            "invalid shipment weight detected",
            "invalid shipment weight format",
            "invalid weight",
            "zero weight",
            "negative weight",
        ],
    )

    add_issue(
        71,
        "INVALID_DELIVERY_ATTEMPTS",
        "Delivery-attempt data needs review",
        (
            "The delivery-attempt count is missing or invalid, so "
            "the record requires manual review."
        ),
        "ESCALATE",
        True,
        [
            "missing delivery_attempts value",
            "invalid delivery_attempts value",
            "invalid delivery_attempts format",
        ],
    )

    add_issue(
        72,
        "CROSS_FIELD_INCONSISTENCY",
        "Conflicting shipment data",
        (
            "Some shipment fields conflict with each other, so "
            "the record requires manual review."
        ),
        "ESCALATE",
        True,
        [
            "cross-field inconsistency detected",
            "cross-field",
            "cross field",
            "delivered with 0",
            "delivered + 0",
            "status and delivery attempts",
            "inconsistent delivery attempts",
        ],
    )

    # -------------------------------------------------
    # Payment / COD data
    # -------------------------------------------------

    add_issue(
        80,
        "INVALID_COD",
        "COD data needs review",
        (
            "The cash-on-delivery amount cannot be interpreted safely, "
            "so the record requires review."
        ),
        "ESCALATE",
        True,
        [
            "invalid cod amount detected",
            "invalid cod value",
            "negative cod",
        ],
    )

    add_issue(
        81,
        "SUSPICIOUS_COD",
        "Payment-related data needs review",
        (
            "The shipment contains an unusual COD amount that "
            "requires review before an automated change."
        ),
        "ESCALATE",
        True,
        [
            "suspicious cod outlier detected",
            "cod outlier",
            "suspicious cod",
            "high cod",
            "cod amount outlier",
        ],
    )

    # -------------------------------------------------
    # Non-blocking warnings
    # -------------------------------------------------

    add_issue(
        200,
        "MISSING_LAST_ATTEMPT",
        "Limited shipment history",
        (
            "The last delivery-attempt date is unavailable. "
            "I can continue where the requested action does not "
            "depend on that missing date."
        ),
        "ALLOW_WITH_LIMITATION",
        False,
        [
            "missing last attempt date",
            "missing last attempt",
            "missing last_attempt",
            "last attempt missing",
            "blank last attempt",
        ],
    )

    add_issue(
        210,
        "SENSITIVE_NOTES_HIDDEN",
        "Protected shipment note",
        (
            "Sensitive internal note content has been hidden "
            "from the customer-facing assistant."
        ),
        "HIDE_AND_ALLOW",
        False,
        [
            "potential sensitive information detected",
            "sensitive note",
            "gate code",
            "door code",
            "access code",
            "pin code",
            "password",
            "otp",
        ],
    )

    # Formatting-only notes are expected after a safe auto-fix.
    # If a NEEDS_REVIEW row contains only formatting notes because
    # of future data changes, keep the conservative fallback below.

    if not candidates:
        return {
            "code": "DATA_REVIEW_REQUIRED",
            "title": "Shipment data needs review",
            "message": (
                "This shipment contains data that cannot be safely "
                "resolved automatically."
            ),
            "handling": "ESCALATE",
            "blocking": True,
        }

    # Critical fix:
    # choose the highest-priority issue across ALL notes rather than
    # returning the first textual match. This prevents a harmless
    # warning such as "missing last attempt date" from hiding a
    # blocking issue such as invalid weight or an ambiguous date.
    candidates.sort(
        key=lambda issue: (
            0 if issue["blocking"] else 1,
            issue["priority"],
        )
    )

    selected = dict(
        candidates[0]
    )

    selected.pop(
        "priority",
        None,
    )

    selected["detected_codes"] = [
        issue["code"]
        for issue in candidates
    ]

    # Full ordered list so callers can report the issue that is actually
    # blocking after repairable ones (phone/address) are set aside.
    selected["issues"] = [
        {key: value for key, value in issue.items() if key != "priority"}
        for issue in candidates
    ]

    return selected


# =================================================
# SHIPMENT VIEW
# =================================================

def build_safe_shipment_view(row):
    """
    Build the internal shipment object.

    Phone is available internally for verification.
    app.py masks it before returning customer-facing responses.
    """

    safe_fields = {
        "tracking_number": row.get(
            "tracking_number"
        ),

        "customer_name": row.get(
            "customer_name"
        ),

        "phone": row.get(
            "phone"
        ),

        "delivery_address": row.get(
            "delivery_address"
        ),

        "emirate": row.get(
            "emirate"
        ),

        "service_type": row.get(
            "service_type"
        ),

        "shipment_date": row.get(
            "shipment_date"
        ),

        "last_attempt_date": row.get(
            "last_attempt_date"
        ),

        "status": row.get(
            "status"
        ),

        "delivery_attempts": row.get(
            "delivery_attempts"
        ),

        "cod_amount_aed": row.get(
            "cod_amount_aed"
        ),

        "weight_kg": row.get(
            "weight_kg"
        ),
    }

    if (
        "scheduled_redelivery_date"
        in row.index
    ):
        safe_fields[
            "scheduled_redelivery_date"
        ] = row.get(
            "scheduled_redelivery_date"
        )

    for key, value in safe_fields.items():
        safe_fields[key] = (
            to_python_value(
                value
            )
        )

    return safe_fields


# =================================================
# FIND SHIPMENT RECORDS
# =================================================

def find_shipment_records(
    tracking_number
):
    tracking = normalize_tracking_number(
        tracking_number
    )

    if tracking is None:
        return pd.DataFrame()

    df = load_shipments()

    if "tracking_number" not in df.columns:
        raise ValueError(
            "tracking_number column is missing "
            "from dataset."
        )

    return df[
        df["tracking_number"]
        .astype(str)
        .str.strip()
        .str.upper()
        == tracking
    ]


# =================================================
# GET SHIPMENT
# =================================================

def get_shipment(
    tracking_number
):
    """
    Main shipment lookup tool.

    Deterministic normalization is allowed; tracking identifiers are never guessed.
    Missing/invalid phone and missing/invalid address are repairable in the MVP.
    Impossible weight values require internal review before an operational action.
    """
    tracking = normalize_tracking_number(tracking_number)

    if tracking is None:
        return {
            "success": False,
            "result": "INVALID_INPUT",
            "message": "A valid tracking number is required.",
        }

    records = find_shipment_records(tracking)

    if records.empty:
        if not is_valid_tracking_format(tracking):
            return {
                "success": False,
                "result": "INVALID_TRACKING_FORMAT",
                "tracking_number": tracking,
                "message": (
                    "The tracking number format does not look valid. "
                    "Please re-enter it exactly as shown on the shipment, or find the shipment by mobile number."
                ),
            }
        return {
            "success": False,
            "result": "NOT_FOUND",
            "tracking_number": tracking,
            "message": "Shipment was not found. Please check the tracking number.",
        }

    if len(records) > 1:
        statuses = []
        if "status" in records.columns:
            for value in records["status"]:
                if not pd.isna(value):
                    status = str(value).strip()
                    if status not in statuses:
                        statuses.append(status)
        return {
            "success": False,
            "result": "DUPLICATE",
            "tracking_number": tracking,
            "record_count": len(records),
            "statuses": statuses,
            "issue": {
                "code": "DUPLICATE_RECORDS",
                "title": "Conflicting shipment records",
                "message": "I found multiple records for this tracking number, so I will not guess which record is correct.",
                "handling": "ESCALATE",
            },
            "message": "Multiple records were found. Human review is required before an operational action can be performed.",
        }

    row = records.iloc[0]
    ai_action = row.get("AI_Action")
    ai_notes = row.get("AI_Notes")
    data_quality_issue = None

    if not pd.isna(ai_action) and str(ai_action).strip().upper() == "NEEDS_REVIEW":
        data_quality_issue = classify_data_quality_issue(ai_notes)

        detected_codes = set(data_quality_issue.get("detected_codes", [data_quality_issue["code"]]))

        # Preserve the original hard-block priority: test/dummy records must
        # never enter operational or review workflows, even when they also
        # contain an invalid weight.
        if "TEST_RECORD" in detected_codes:
            return {
                "success": False,
                "result": "NEEDS_REVIEW",
                "tracking_number": tracking,
                "issue": {
                    "code": "TEST_RECORD",
                    "title": "Test record blocked",
                    "message": "This record is marked as test data and cannot be used for customer actions.",
                    "handling": "BLOCK",
                },
                "message": "Test records cannot be used for operational customer actions.",
            }

        # Impossible weight must never be hidden by a repairable phone/address issue.
        if "INVALID_WEIGHT" in detected_codes:
            review_status = row.get("agent_review_status") if "agent_review_status" in row.index else None
            if pd.isna(review_status) or str(review_status).strip().upper() != "RESOLVED":
                return {
                    "success": False,
                    "result": "NEEDS_REVIEW",
                    "tracking_number": tracking,
                    "issue": {
                        "code": "INVALID_WEIGHT",
                        "title": "Shipment weight requires review",
                        "message": (
                            "The recorded shipment weight is zero, negative, or otherwise invalid. "
                            "I have paused this change so the operational team can review the shipment."
                        ),
                        "handling": "INTERNAL_REVIEW",
                    },
                    "review_required": True,
                    "message": "Shipment weight requires internal review before an automated change.",
                }
            detected_codes.discard("INVALID_WEIGHT")

            # The source row still contains the original INVALID_WEIGHT note.
            # A resolved review is an operational override for this anomaly only;
            # it does not rewrite or invent the source weight. If weight was the
            # primary classified issue, clear that primary block and continue
            # evaluating any remaining issues below.
            if data_quality_issue.get("code") == "INVALID_WEIGHT":
                if "MISSING_LAST_ATTEMPT" in detected_codes:
                    data_quality_issue = {
                        "code": "MISSING_LAST_ATTEMPT",
                        "title": "Limited shipment history",
                        "message": (
                            "The last delivery-attempt date is unavailable. "
                            "I can continue where the requested action does not "
                            "depend on that missing date."
                        ),
                        "handling": "ALLOW_WITH_LIMITATION",
                        "blocking": False,
                        "detected_codes": list(detected_codes),
                    }
                elif "SENSITIVE_NOTES_HIDDEN" in detected_codes:
                    data_quality_issue = {
                        "code": "SENSITIVE_NOTES_HIDDEN",
                        "title": "Protected shipment note",
                        "message": (
                            "Sensitive internal note content has been hidden "
                            "from the customer-facing assistant."
                        ),
                        "handling": "HIDE_AND_ALLOW",
                        "blocking": False,
                        "detected_codes": list(detected_codes),
                    }
                else:
                    data_quality_issue = None

        repairable_codes = {"MISSING_PHONE", "INVALID_PHONE", "INVALID_ADDRESS"}
        nonblocking_codes = {"MISSING_LAST_ATTEMPT", "SENSITIVE_NOTES_HIDDEN"}
        unresolved_other = detected_codes - repairable_codes - nonblocking_codes

        if unresolved_other:
            # Report the issue that is really blocking, not a repairable one
            # (e.g. a missing phone) that happens to sort first.
            blocking_issue = next(
                (
                    issue
                    for issue in (data_quality_issue or {}).get("issues", [])
                    if issue["code"] in unresolved_other
                ),
                data_quality_issue,
            )
            return {
                "success": False,
                "result": "NEEDS_REVIEW",
                "tracking_number": tracking,
                "issue": {
                    "code": blocking_issue["code"],
                    "title": blocking_issue["title"],
                    "message": blocking_issue["message"],
                    "handling": blocking_issue["handling"],
                },
                "message": blocking_issue["message"],
            }

        # Phone and address are repairable in this MVP. Current runtime values win over stale source notes.
        phone_problem = bool(detected_codes & {"MISSING_PHONE", "INVALID_PHONE"}) and not has_usable_registered_phone(row.get("phone"))
        address_problem = "INVALID_ADDRESS" in detected_codes and not is_valid_delivery_address(row.get("delivery_address"))

        # Preserve a non-blocking warning if one exists; otherwise repairable issues are represented by flags below.
        if data_quality_issue is not None and not (phone_problem or address_problem) and data_quality_issue["code"] in repairable_codes:
            data_quality_issue = None
        elif data_quality_issue is not None and data_quality_issue["code"] in repairable_codes:
            data_quality_issue = None

        elif data_quality_issue is not None and data_quality_issue["blocking"]:
            return {
                "success": False,
                "result": "NEEDS_REVIEW",
                "tracking_number": tracking,
                "issue": {
                    "code": data_quality_issue["code"],
                    "title": data_quality_issue["title"],
                    "message": data_quality_issue["message"],
                    "handling": data_quality_issue["handling"],
                },
                "message": data_quality_issue["message"],
            }

    # Cross-field operational inconsistency: a shipment marked Out for Delivery
    # must not silently rely on a missing/invalid destination address. This is
    # different from a simple missing address on an earlier shipment stage,
    # where the customer can safely provide the address as a prerequisite.
    status_text = str(row.get("status") or "").strip().lower()
    address_is_valid = is_valid_delivery_address(row.get("delivery_address"))
    if status_text == "out for delivery" and not address_is_valid:
        review_status = row.get("agent_review_status") if "agent_review_status" in row.index else None
        review_issue = row.get("agent_review_issue") if "agent_review_issue" in row.index else None
        review_status = None if pd.isna(review_status) else str(review_status).strip().upper()
        review_issue = None if pd.isna(review_issue) else str(review_issue).strip().upper()

        if not (
            review_status == "RESOLVED"
            and review_issue == "OUT_FOR_DELIVERY_MISSING_ADDRESS"
        ):
            return {
                "success": False,
                "result": "NEEDS_REVIEW",
                "tracking_number": tracking,
                "issue": {
                    "code": "OUT_FOR_DELIVERY_MISSING_ADDRESS",
                    "title": "Shipment information requires review",
                    "message": (
                        "This shipment is marked as Out for Delivery, but no valid "
                        "delivery address is available. I have paused the request "
                        "and routed the shipment for internal operational review."
                    ),
                    "handling": "INTERNAL_REVIEW",
                },
                "review_required": True,
                "message": (
                    "The shipment status and delivery-address data are inconsistent "
                    "and require internal review before an automated change."
                ),
            }

    shipment = build_safe_shipment_view(row)
    result = {
        "success": True,
        "result": "FOUND",
        "shipment": shipment,
        "message": "Shipment found successfully.",
        "needs_phone_collection": not has_usable_registered_phone(row.get("phone")),
        "requires_address_first": not is_valid_delivery_address(row.get("delivery_address")),
    }

    if data_quality_issue is not None and not data_quality_issue.get("blocking", False):
        result["data_quality_warning"] = {
            "code": data_quality_issue["code"],
            "title": data_quality_issue["title"],
            "message": data_quality_issue["message"],
            "handling": data_quality_issue["handling"],
        }

    return result


# =================================================
# FIND MY SHIPMENT
# =================================================

def is_test_record(row):
    tracking = str(row.get("tracking_number") or "").strip().upper()
    status = str(row.get("status") or "").strip().upper()
    notes = row.get("AI_Notes")
    notes = "" if notes is None or pd.isna(notes) else str(notes).lower()
    return (
        tracking.startswith("TEST")
        or status == "TEST"
        or "test/dummy record detected" in notes
    )


def find_shipments_by_phone(
    phone_number
):
    """
    Locate active shipments using a registered mobile number.

    This is an enabling capability, not a third operational action.

    MVP assumption:
    Production shipment discovery should be protected by stronger
    authentication such as OTP, authenticated account, CRM identity,
    or another trusted identity provider.
    """

    # Lookup only compares against numbers already on file and stores
    # nothing, so the registered-number rule applies (any UAE 5X mobile).
    # Letters, landlines, foreign and malformed numbers are rejected.
    normalized_phone = normalize_registered_phone(
        phone_number
    )

    if normalized_phone is None:
        return {
            "success": False,
            "result": "INVALID_PHONE",
            "shipments": [],
            "message": (
                "A valid registered mobile number is required."
            )
        }

    df = load_shipments()

    if "phone" not in df.columns:
        return {
            "success": False,
            "result": "PHONE_DATA_UNAVAILABLE",
            "shipments": [],
            "message": (
                "Registered phone information is not "
                "available for shipment discovery."
            )
        }

    phone_matches = df[
        df["phone"].apply(
            normalize_registered_phone
        )
        == normalized_phone
    ].copy()

    if phone_matches.empty:
        return {
            "success": False,
            "result": "NO_SHIPMENTS_FOUND",
            "shipments": [],
            "message": (
                "No shipments were found for this "
                "registered mobile number."
            )
        }

    inactive_statuses = {
        "delivered",
        "returned to sender",
    }

    shipments = []

    for _, row in phone_matches.iterrows():

        tracking = row.get(
            "tracking_number"
        )

        if pd.isna(tracking):
            continue

        status = str(
            row.get("status")
            or ""
        ).strip()

        if status.lower() in inactive_statuses:
            continue

        # Test/dummy records must never be offered to a customer.
        if is_test_record(row):
            continue

        ai_action = row.get(
            "AI_Action"
        )

        ai_notes = row.get(
            "AI_Notes"
        )

        review_issue = None

        if (
            not pd.isna(ai_action)
            and str(ai_action)
            .strip()
            .upper()
            == "NEEDS_REVIEW"
        ):
            review_issue = classify_data_quality_issue(
                ai_notes
            )

        requires_review = (
            review_issue is not None
            and review_issue["blocking"]
        )

        shipments.append(
            {
                # Internal selection value.
                # Frontend should display masked_tracking_number instead.
                "tracking_number":
                    normalize_tracking_number(
                        tracking
                    ),

                "masked_tracking_number":
                    mask_tracking_number(
                        tracking
                    ),

                "status":
                    to_python_value(
                        row.get(
                            "status"
                        )
                    ),

                "emirate":
                    to_python_value(
                        row.get(
                            "emirate"
                        )
                    ),

                "service_type":
                    to_python_value(
                        row.get(
                            "service_type"
                        )
                    ),

                "shipment_date":
                    to_python_value(
                        row.get(
                            "shipment_date"
                        )
                    ),

                "requires_review":
                    requires_review,

                "review_issue": (
                    None
                    if review_issue is None
                    else {
                        "code": review_issue["code"],
                        "title": review_issue["title"],
                        "message": review_issue["message"],
                        "handling": review_issue["handling"],
                    }
                ),
            }
        )

    if not shipments:
        return {
            "success": False,
            "result": "NO_ACTIVE_SHIPMENTS",
            "shipments": [],
            "message": (
                "No active shipments were found for "
                "this registered mobile number."
            )
        }

    shipments.sort(
        key=lambda shipment:
            str(
                shipment.get(
                    "shipment_date"
                )
                or ""
            ),
        reverse=True
    )

    return {
        "success": True,
        "result": "FOUND",
        "count": len(
            shipments
        ),
        "shipments": shipments,
        "message": (
            f"{len(shipments)} active shipment(s) found."
        )
    }


# =================================================
# RESCHEDULE ELIGIBILITY
# =================================================

def can_reschedule_delivery(
    tracking_number
):
    lookup = get_shipment(tracking_number)

    if not lookup["success"]:
        return {
            "allowed": False,
            "reason": lookup["result"],
            "message": lookup["message"],
        }

    shipment = lookup["shipment"]
    status = str(shipment.get("status") or "").strip().lower()

    if status == "delivered":
        return {"allowed": False, "reason": "ALREADY_DELIVERED", "message": "This shipment has already been delivered."}

    if status == "returned to sender":
        return {"allowed": False, "reason": "RETURNED_TO_SENDER", "message": "This shipment has been returned to sender and requires human support."}

    # Out for Delivery is evaluated before the normal missing-address
    # prerequisite. If the address was missing at this stage, get_shipment()
    # already routed the cross-field inconsistency through internal review.
    # After review, the operational status still controls eligibility.
    if status == "out for delivery":
        return {"allowed": False, "reason": "OUT_FOR_DELIVERY", "message": "The shipment is currently out for delivery. Automated rescheduling is not available."}

    # For earlier eligible shipment stages, a usable destination address is a
    # repairable prerequisite and may be collected from the customer.
    if lookup.get("requires_address_first"):
        return {
            "allowed": True,
            "reason": "ADDRESS_REQUIRED_FIRST",
            "requires_confirmation": True,
            "requires_address_first": True,
            "message": "A valid delivery address must be provided before the delivery time can be changed.",
        }

    allowed_statuses = {"failed delivery", "scheduled for redelivery", "transit", "in transit"}
    if status not in allowed_statuses:
        return {"allowed": False, "reason": "STATUS_NOT_SUPPORTED", "message": "This shipment status is not supported for automated rescheduling in the MVP."}

    reason = "ELIGIBLE"
    if status == "failed delivery":
        reason = "FAILED_DELIVERY"
    elif status == "scheduled for redelivery":
        reason = "ALREADY_SCHEDULED"
    elif status in {"transit", "in transit"}:
        reason = "TRANSIT_ELIGIBLE"

    result = {
        "allowed": True,
        "reason": reason,
        "requires_confirmation": True,
        "requires_address_first": bool(lookup.get("requires_address_first")),
        "message": "The shipment is eligible for a delivery-time change.",
    }

    if status == "scheduled for redelivery":
        result["current_redelivery_date"] = shipment.get("scheduled_redelivery_date")

    if lookup.get("requires_address_first"):
        result["message"] = "The shipment can be rescheduled, but a valid delivery address must be provided first."

    return result


# =================================================
# ADDRESS UPDATE ELIGIBILITY
# =================================================

def can_update_address(
    tracking_number
):
    lookup = get_shipment(tracking_number)

    if not lookup["success"]:
        return {
            "allowed": False,
            "reason": lookup["result"],
            "message": lookup["message"],
        }

    shipment = lookup["shipment"]
    status = str(shipment.get("status") or "").strip().lower()

    if status == "delivered":
        return {"allowed": False, "reason": "ALREADY_DELIVERED", "message": "The delivery address cannot be changed because the shipment has already been delivered."}

    if status == "returned to sender":
        return {"allowed": False, "reason": "RETURNED_TO_SENDER", "message": "The shipment has been returned to sender and requires human support."}

    if status == "out for delivery":
        return {"allowed": False, "reason": "OUT_FOR_DELIVERY", "message": "The shipment is currently out for delivery. Address changes require human support."}

    # Allow-list, not deny-list: an unrecognised status must never be
    # treated as eligible for an operational change.
    if status not in {"failed delivery", "scheduled for redelivery", "transit", "in transit"}:
        return {"allowed": False, "reason": "STATUS_NOT_SUPPORTED", "message": "This shipment status is not supported for automated address changes in the MVP."}

    return {
        "allowed": True,
        "reason": "ELIGIBLE",
        "requires_confirmation": True,
        "current_address": shipment.get("delivery_address"),
        "message": "The shipment is eligible for an address update.",
    }


# =================================================
# TERMINAL TEST
# =================================================

if __name__ == "__main__":

    print(
        "Shipment Service Test"
    )

    print(
        "-" * 50
    )

    if RUNTIME_FILE.exists():
        print(
            "Data source: RUNTIME"
        )
    else:
        print(
            "Data source: CLEANED SOURCE"
        )

    print()

    tracking = input(
        "Enter tracking number: "
    )

    print()

    print(
        "Lookup Result:"
    )

    print(
        get_shipment(
            tracking
        )
    )

    print()

    print(
        "Reschedule Eligibility:"
    )

    print(
        can_reschedule_delivery(
            tracking
        )
    )

    print()

    print(
        "Address Change Eligibility:"
    )

    print(
        can_update_address(
            tracking
        )
    )
