import re
import sys
import pandas as pd
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:  # allow `python backend/data_agent.py`
    sys.path.insert(0, str(BASE_DIR))

from backend.validators import (  # noqa: E402
    is_excel_serial_shape,
    is_placeholder_address,
    normalize_registered_phone,
    parse_excel_serial,
    parse_text_month_date,
)

INPUT_FILE = BASE_DIR / "data" / "FDE_Assignment_Shipment_Dataset.xlsx"
OUTPUT_FILE = BASE_DIR / "outputs" / "FDE_Assignment_Shipment_Dataset_AI_Cleaned.xlsx"


# =================================================
# BASIC CLEANING
# =================================================

def clean_text(value):
    if pd.isna(value):
        return value

    if isinstance(value, str):
        return value.strip()

    return value


# =================================================
# STATUS
# =================================================

def normalize_status(status):
    if pd.isna(status) or str(status).strip() == "":
        return status, None

    original = str(status).strip()
    value = original.lower().strip()

    status_map = {
        "delivered": "Delivered",
        "delivered_ok": "Delivered",

        "failed delivery": "Failed Delivery",
        "failed_delivery": "Failed Delivery",
        "failed": "Failed Delivery",
        "failed - customer not available": "Failed Delivery",

        "scheduled for redelivery": "Scheduled for Redelivery",
        "re-delivery scheduled": "Scheduled for Redelivery",
        "redelivery": "Scheduled for Redelivery",

        "in transit": "In Transit",
        "in-transit": "In Transit",
        "transit": "In Transit",

        "out for delivery": "Out for Delivery",

        "returned to sender": "Returned to Sender",
        "return to sender": "Returned to Sender",
        "rts": "Returned to Sender",
    }

    if value in status_map:
        cleaned = status_map[value]

        if cleaned != original:
            return (
                cleaned,
                f'Status normalized from "{original}" to "{cleaned}"'
            )

    return original, None


KNOWN_STATUSES = {
    "Delivered",
    "Failed Delivery",
    "Scheduled for Redelivery",
    "In Transit",
    "Out for Delivery",
    "Returned to Sender",
}


def resolve_undelivered_status(status, delivery_attempts):
    """
    "Undelivered" is not one of the operational statuses. It is only mapped
    to "Failed Delivery" when the row itself proves at least one delivery
    attempt was made (delivery_attempts >= 1). Otherwise it is left as-is and
    flagged for review — the agent never guesses a shipment state.
    """
    if pd.isna(status) or str(status).strip().lower() != "undelivered":
        return status, None

    try:
        attempts = int(delivery_attempts)
    except (TypeError, ValueError):
        return status, None

    if attempts < 1:
        return status, None

    return (
        "Failed Delivery",
        f'Status normalized from "{str(status).strip()}" to "Failed Delivery" '
        f"(delivery_attempts={attempts} confirms an unsuccessful delivery attempt)",
    )


def validate_status(status):
    if pd.isna(status) or str(status).strip() == "":
        return "Missing shipment status. Agent cannot safely determine shipment state."

    value = str(status).strip()

    # TEST rows are handled by the dedicated test-record check.
    if value.upper() == "TEST":
        return None

    if value not in KNOWN_STATUSES:
        return (
            f'Unrecognized shipment status "{value}". '
            "Agent cannot safely determine shipment state."
        )

    return None


# =================================================
# COD
# =================================================

def normalize_cod(value):
    if pd.isna(value):
        return value, None

    original = value

    if isinstance(value, str):
        cleaned = (
            value.upper()
            .replace("AED", "")
            .replace(",", "")
            .strip()
        )

        try:
            number = float(cleaned)

            return (
                number,
                f'COD normalized from "{original}" to {number} AED'
            )

        except ValueError:
            return original, None

    return value, None


def validate_cod(value):
    if pd.isna(value):
        return None

    try:
        amount = float(value)

        if amount < 0:
            return (
                f"Invalid COD amount detected ({value} AED). "
                "Negative COD values are not valid."
            )

        # Prototype threshold.
        # We flag very high amounts instead of changing them.
        if amount > 10000:
            return (
                f"Suspicious COD outlier detected ({value} AED). "
                "Value retained but requires review."
            )

    except (ValueError, TypeError):
        return (
            f'Invalid COD value "{value}". '
            "Amount cannot be safely interpreted."
        )

    return None


# =================================================
# WEIGHT
# =================================================

def validate_weight(value):
    if pd.isna(value) or str(value).strip() == "":
        return "Missing shipment weight."

    try:
        weight = float(value)

        if weight <= 0:
            return (
                f"Invalid shipment weight detected ({value} kg). "
                "Correct value cannot be safely inferred."
            )

    except (ValueError, TypeError):
        return (
            f'Invalid shipment weight format: "{value}".'
        )

    return None


# =================================================
# PHONE
# =================================================

def validate_phone(value):
    if pd.isna(value) or str(value).strip() == "":
        return "Missing phone number."

    # Stored numbers must normalize to a UAE mobile (+9715XXXXXXXX).
    # Letters, landlines, foreign and dummy numbers are flagged, never fixed.
    if normalize_registered_phone(value) is None:
        return "Invalid or placeholder phone number."

    return None


# =================================================
# ADDRESS
# =================================================

def validate_address(value):
    if pd.isna(value) or str(value).strip() == "":
        return value, "Missing delivery address."

    address = str(value).strip()

    if is_placeholder_address(address):
        return value, (
            f'Invalid delivery address detected: "{address}". '
            "Correct address cannot be safely inferred."
        )

    return address, None


# =================================================
# TRACKING NUMBER / TEST RECORD
# =================================================

def validate_tracking_record(tracking_number, status):
    notes = []

    if pd.isna(tracking_number) or str(tracking_number).strip() == "":
        notes.append(
            "Missing tracking number. Shipment cannot be safely identified."
        )
        return notes

    tracking = str(tracking_number).strip().upper()

    status_text = ""

    if not pd.isna(status):
        status_text = str(status).strip().upper()

    if (
        tracking.startswith("TEST")
        or status_text == "TEST"
    ):
        notes.append(
            "Test/dummy record detected. "
            "Operational actions must not be executed on this record."
        )

        return notes

    # Expected sample production format:
    # EX + 6 digits + AE
    if not re.fullmatch(
        r"EX\d{6}AE",
        tracking
    ):
        notes.append(
            f'Invalid or unexpected tracking number format: "{tracking_number}". '
            "Record requires review before operational use."
        )

    return notes


# =================================================
# DATES
# =================================================

def normalize_date_value(value, field_name):
    """
    Deterministic conversion of unambiguous non-ISO dates to YYYY-MM-DD:
      * text month:   "22 Aug 2026", "3 Sep 2026", "01 Jan 2026"
      * Excel serial: integer serial in the 2000-01-01..2099-12-31 window
    Anything else is returned unchanged for validate_date() to judge.
    Impossible or out-of-range values are never replaced.
    """
    if pd.isna(value) or str(value).strip() == "":
        return value, None

    original = str(value).strip()

    parsed = parse_text_month_date(original)
    if parsed is None and is_excel_serial_shape(value):
        parsed = parse_excel_serial(value)

    if parsed is None:
        return value, None

    iso = parsed.isoformat()
    return iso, f'{field_name.capitalize()} normalized from "{original}" to "{iso}"'


def validate_date(value, field_name):
    if pd.isna(value) or str(value).strip() == "":
        return f"Missing {field_name}."

    date_text = str(value).strip()

    # Supported unambiguous non-ISO shapes (normally already converted).
    if parse_text_month_date(date_text) is not None:
        return None
    if is_excel_serial_shape(value) and parse_excel_serial(value) is not None:
        return None

    # Shapes that could not be converted.
    if re.fullmatch(r"\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}", date_text):
        return (
            f'Impossible or unrecognised {field_name}: "{date_text}". '
            "Correct date cannot be safely inferred."
        )
    if is_excel_serial_shape(value) and not re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", date_text):
        return (
            f'Invalid Excel serial {field_name}: "{date_text}". '
            "Correct date cannot be safely inferred."
        )

    # Safe ISO format.
    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        date_text
    ):
        try:
            pd.to_datetime(
                date_text,
                format="%Y-%m-%d",
                errors="raise"
            )

            return None

        except Exception:
            return (
                f'Invalid {field_name}: "{date_text}".'
            )

    # Other date styles.
    if re.fullmatch(
        r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}",
        date_text
    ):
        parts = re.split(
            r"[./-]",
            date_text
        )

        first = int(parts[0])
        second = int(parts[1])

        # Both can be months -> ambiguous.
        if first <= 12 and second <= 12:
            return (
                f'Ambiguous {field_name}: "{date_text}". '
                "Correct date cannot be safely inferred."
            )

        # Unambiguous order, but the date itself must exist (e.g. 31/02/2026).
        year = int(parts[2])
        year = year + 2000 if year < 100 else year
        day, month = (first, second) if first > 12 else (second, first)
        try:
            pd.Timestamp(year=year, month=month, day=day)
        except ValueError:
            return (
                f'Impossible {field_name}: "{date_text}". '
                "Correct date cannot be safely inferred."
            )

        return None

    return (
        f'Invalid or unsupported {field_name} format: "{date_text}".'
    )


def parse_safe_date(value):
    if pd.isna(value) or str(value).strip() == "":
        return None

    date_text = str(value).strip()

    text_month = parse_text_month_date(date_text)
    if text_month is not None:
        return pd.Timestamp(text_month)

    if is_excel_serial_shape(value):
        serial = parse_excel_serial(value)
        if serial is not None:
            return pd.Timestamp(serial)

    # YYYY-MM-DD
    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        date_text
    ):
        try:
            return pd.to_datetime(
                date_text,
                format="%Y-%m-%d"
            )
        except Exception:
            return None

    # DD.MM.YYYY only when clearly unambiguous.
    if re.fullmatch(
        r"\d{1,2}\.\d{1,2}\.\d{4}",
        date_text
    ):
        parts = date_text.split(".")

        first = int(parts[0])
        second = int(parts[1])

        if first > 12 and second <= 12:
            try:
                return pd.to_datetime(
                    date_text,
                    format="%d.%m.%Y"
                )
            except Exception:
                return None

    # DD/MM/YYYY only when clearly unambiguous.
    if re.fullmatch(
        r"\d{1,2}/\d{1,2}/\d{4}",
        date_text
    ):
        parts = date_text.split("/")

        first = int(parts[0])
        second = int(parts[1])

        if first > 12 and second <= 12:
            try:
                return pd.to_datetime(
                    date_text,
                    format="%d/%m/%Y"
                )
            except Exception:
                return None

    # DD-MM-YYYY only when clearly unambiguous.
    if re.fullmatch(
        r"\d{1,2}-\d{1,2}-\d{4}",
        date_text
    ):
        parts = date_text.split("-")

        first = int(parts[0])
        second = int(parts[1])

        if first > 12 and second <= 12:
            try:
                return pd.to_datetime(
                    date_text,
                    format="%d-%m-%Y"
                )
            except Exception:
                return None

    return None


def validate_date_sequence(
    shipment_date,
    last_attempt_date
):
    shipment = parse_safe_date(
        shipment_date
    )

    last_attempt = parse_safe_date(
        last_attempt_date
    )

    if shipment is None or last_attempt is None:
        return None

    if last_attempt < shipment:
        return (
            "Illogical date sequence detected: "
            f"last attempt date ({last_attempt_date}) "
            f"is earlier than shipment date ({shipment_date}). "
            "Correct dates cannot be safely inferred."
        )

    return None


# =================================================
# DELIVERY ATTEMPTS
# =================================================

def validate_delivery_attempts(value):
    if pd.isna(value) or str(value).strip() == "":
        return "Missing delivery_attempts value."

    try:
        attempts = int(value)

        if attempts < 0:
            return (
                f"Invalid delivery_attempts value ({value}). "
                "Number of delivery attempts cannot be negative."
            )

    except (ValueError, TypeError):
        return (
            f'Invalid delivery_attempts format: "{value}".'
        )

    return None


# =================================================
# CROSS-FIELD LOGIC
# =================================================

def validate_status_attempts(
    status,
    delivery_attempts
):
    if pd.isna(status):
        return None

    normalized_status, _ = normalize_status(
        status
    )

    try:
        attempts = int(
            delivery_attempts
        )

    except (ValueError, TypeError):
        return None

    if (
        normalized_status == "Delivered"
        and attempts == 0
    ):
        return (
            "Cross-field inconsistency detected: "
            "shipment status is Delivered but delivery_attempts is 0."
        )

    return None


# =================================================
# SENSITIVE NOTES
# =================================================

def validate_sensitive_notes(value):
    if pd.isna(value) or str(value).strip() == "":
        return None

    note = str(value).strip()

    sensitive_patterns = [
        r"\bgate\s*code\b",
        r"\bdoor\s*code\b",
        r"\baccess\s*code\b",
        r"\bpin\s*code\b",
        r"\bpassword\b",
        r"\botp\b",
    ]

    for pattern in sensitive_patterns:
        if re.search(
            pattern,
            note,
            flags=re.IGNORECASE
        ):
            return (
                "Potential sensitive information detected in free-text notes. "
                "Customer-facing AI should not expose internal notes automatically."
            )

    return None


# =================================================
# DUPLICATE TRACKING ANALYSIS
# =================================================

def build_duplicate_map(df):
    duplicate_map = {}

    grouped = df.groupby(
        "tracking_number",
        dropna=False
    )

    for tracking_number, group in grouped:

        if pd.isna(tracking_number):
            continue

        if len(group) <= 1:
            continue

        normalized_statuses = set()

        for status in group["status"]:
            normalized_status, _ = normalize_status(
                status
            )

            if not pd.isna(
                normalized_status
            ):
                normalized_statuses.add(
                    str(normalized_status)
                )

        duplicate_map[
            str(tracking_number).strip()
        ] = {
            "count": len(group),

            "conflicting_status":
                len(normalized_statuses) > 1,

            "statuses":
                sorted(normalized_statuses)
        }

    return duplicate_map


# =================================================
# PROCESS ONE ROW
# =================================================

def process_row(
    row,
    duplicate_map
):
    actions = []
    notes = []

    # -------------------------------------------------
    # 1. Clean whitespace
    # -------------------------------------------------

    for column in row.index:

        if isinstance(
            row[column],
            str
        ):
            original = row[column]

            cleaned = clean_text(
                original
            )

            if cleaned != original:

                row[column] = cleaned

                actions.append(
                    "AUTO_FIXED"
                )

                notes.append(
                    f"Removed extra whitespace from {column}"
                )

    # -------------------------------------------------
    # 2. Normalize status
    # -------------------------------------------------

    if "status" in row:

        new_value, note = normalize_status(
            row["status"]
        )

        if not note:
            new_value, note = resolve_undelivered_status(
                row["status"],
                row.get("delivery_attempts"),
            )

        if note:

            row["status"] = new_value

            actions.append(
                "AUTO_FIXED"
            )

            notes.append(
                note
            )

        status_issue = validate_status(
            row["status"]
        )

        if status_issue:

            actions.append(
                "NEEDS_REVIEW"
            )

            notes.append(
                status_issue
            )

    # -------------------------------------------------
    # 3. Normalize + validate COD
    # -------------------------------------------------

    if "cod_amount_aed" in row:

        new_value, note = normalize_cod(
            row["cod_amount_aed"]
        )

        if note:

            row["cod_amount_aed"] = new_value

            actions.append(
                "AUTO_FIXED"
            )

            notes.append(
                note
            )

        cod_issue = validate_cod(
            row["cod_amount_aed"]
        )

        if cod_issue:

            actions.append(
                "NEEDS_REVIEW"
            )

            notes.append(
                cod_issue
            )

    # -------------------------------------------------
    # 4. Weight
    # -------------------------------------------------

    if "weight_kg" in row:

        note = validate_weight(
            row["weight_kg"]
        )

        if note:

            actions.append(
                "NEEDS_REVIEW"
            )

            notes.append(
                note
            )

    # -------------------------------------------------
    # 5. Phone
    # -------------------------------------------------

    if "phone" in row:

        note = validate_phone(
            row["phone"]
        )

        if note:

            actions.append(
                "NEEDS_REVIEW"
            )

            notes.append(
                note
            )

    # -------------------------------------------------
    # 6. Shipment date
    # -------------------------------------------------

    if "shipment_date" in row:

        new_value, note = normalize_date_value(
            row["shipment_date"],
            "shipment date"
        )

        if note:

            row["shipment_date"] = new_value

            actions.append(
                "AUTO_FIXED"
            )

            notes.append(
                note
            )

        note = validate_date(
            row["shipment_date"],
            "shipment date"
        )

        if note:

            actions.append(
                "NEEDS_REVIEW"
            )

            notes.append(
                note
            )

    # -------------------------------------------------
    # 7. Last attempt date
    # -------------------------------------------------

    if "last_attempt_date" in row:

        new_value, note = normalize_date_value(
            row["last_attempt_date"],
            "last attempt date"
        )

        if note:

            row["last_attempt_date"] = new_value

            actions.append(
                "AUTO_FIXED"
            )

            notes.append(
                note
            )

        note = validate_date(
            row["last_attempt_date"],
            "last attempt date"
        )

        if note:

            actions.append(
                "NEEDS_REVIEW"
            )

            notes.append(
                note
            )

    # -------------------------------------------------
    # 8. Date sequence
    # -------------------------------------------------

    if (
        "shipment_date" in row
        and "last_attempt_date" in row
    ):

        note = validate_date_sequence(
            row["shipment_date"],
            row["last_attempt_date"]
        )

        if note:

            actions.append(
                "NEEDS_REVIEW"
            )

            notes.append(
                note
            )

    # -------------------------------------------------
    # 9. Address
    # -------------------------------------------------

    if "delivery_address" in row:

        new_value, note = validate_address(
            row["delivery_address"]
        )

        if (
            new_value
            != row["delivery_address"]
        ):

            row["delivery_address"] = new_value

            actions.append(
                "AUTO_FIXED"
            )

        if note:

            actions.append(
                "NEEDS_REVIEW"
            )

            notes.append(
                note
            )

    # -------------------------------------------------
    # 10. Tracking number / test record
    # -------------------------------------------------

    tracking_number = row.get(
        "tracking_number"
    )

    status = row.get(
        "status"
    )

    tracking_notes = validate_tracking_record(
        tracking_number,
        status
    )

    for note in tracking_notes:

        actions.append(
            "NEEDS_REVIEW"
        )

        notes.append(
            note
        )

    # -------------------------------------------------
    # 11. Duplicate tracking
    # -------------------------------------------------

    if not pd.isna(
        tracking_number
    ):

        tracking_key = str(
            tracking_number
        ).strip()

        if tracking_key in duplicate_map:

            duplicate_info = duplicate_map[
                tracking_key
            ]

            actions.append(
                "NEEDS_REVIEW"
            )

            if duplicate_info[
                "conflicting_status"
            ]:

                status_list = ", ".join(
                    duplicate_info[
                        "statuses"
                    ]
                )

                notes.append(
                    "Duplicate tracking number detected "
                    f"({duplicate_info['count']} records) "
                    "with conflicting shipment statuses: "
                    f"{status_list}. "
                    "Correct record cannot be safely selected."
                )

            else:

                notes.append(
                    "Duplicate tracking number detected "
                    f"({duplicate_info['count']} records). "
                    "Duplicate records require review."
                )

    # -------------------------------------------------
    # 12. Delivery attempts validation
    # -------------------------------------------------

    if "delivery_attempts" in row:

        note = validate_delivery_attempts(
            row["delivery_attempts"]
        )

        if note:

            actions.append(
                "NEEDS_REVIEW"
            )

            notes.append(
                note
            )

    # -------------------------------------------------
    # 13. Status / attempts consistency
    # -------------------------------------------------

    if (
        "status" in row
        and "delivery_attempts" in row
    ):

        note = validate_status_attempts(
            row["status"],
            row["delivery_attempts"]
        )

        if note:

            actions.append(
                "NEEDS_REVIEW"
            )

            notes.append(
                note
            )

    # -------------------------------------------------
    # 14. Sensitive free-text notes
    # -------------------------------------------------

    if "notes" in row:

        note = validate_sensitive_notes(
            row["notes"]
        )

        if note:

            actions.append(
                "NEEDS_REVIEW"
            )

            notes.append(
                note
            )

    # =================================================
    # FINAL DECISION
    # =================================================

    if "NEEDS_REVIEW" in actions:

        ai_action = "NEEDS_REVIEW"

    elif "AUTO_FIXED" in actions:

        ai_action = "AUTO_FIXED"

    else:

        ai_action = "NO_CHANGE"

    row["AI_Action"] = ai_action

    row["AI_Notes"] = (
        " | ".join(notes)
        if notes
        else ""
    )

    return row


# =================================================
# RUN DATA AGENT
# =================================================

def run_data_agent():

    print(
        "Reading original shipment dataset..."
    )

    df = pd.read_excel(
        INPUT_FILE
    )

    print(
        f"Loaded {len(df)} shipment records."
    )

    duplicate_map = build_duplicate_map(
        df
    )

    print(
        f"Detected {len(duplicate_map)} "
        "duplicate tracking numbers."
    )

    cleaned_df = df.apply(
        lambda row: process_row(
            row,
            duplicate_map
        ),
        axis=1
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    cleaned_df.to_excel(
        OUTPUT_FILE,
        index=False
    )

    print(
        "Finished."
    )

    print(
        f"Output saved to: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    run_data_agent()