# backend/actions.py

import json
from datetime import datetime, UTC
from pathlib import Path

import pandas as pd

from backend.validators import normalize_registered_phone
from backend.business_rules import (
    ACTION_ALLOW,
    evaluate_address_update,
    evaluate_reschedule,
)


# =================================================
# PATHS
# =================================================

from backend.config import (  # noqa: E402
    BASE_DIR,
    AUDIT_LOG_FILE,
    RUNTIME_FILE,
)
from backend.config import CLEANED_FILE as SOURCE_FILE  # noqa: E402


# =================================================
# HELPERS
# =================================================

def normalize_tracking_number(tracking_number):
    if tracking_number is None:
        return None

    tracking = str(
        tracking_number
    ).strip().upper()

    return tracking or None


def normalize_phone_value(value):
    """
    Convert phone values read from Excel
    into clean text.

    Example:
    971536385467.0
    -> 971536385467
    """

    if value is None:
        return None

    if pd.isna(value):
        return None

    text = str(
        value
    ).strip()

    if text.endswith(".0"):
        text = text[:-2]

    return text


def get_last_four_digits(value):
    """
    Last 4 digits of the REGISTERED phone after normalization to
    +9715XXXXXXXX, so 0501234567 / 971501234567 / +971501234567 compare
    identically. A value that is not a usable UAE mobile yields None
    (verification unavailable) instead of verifying against junk digits.
    """

    canonical = normalize_registered_phone(value)

    if canonical is None:
        return None

    return canonical[-4:]


# =================================================
# RUNTIME DATASET
# =================================================

def load_runtime_dataset():
    """
    Load the runtime dataset used by
    the action tools.

    The original cleaned dataset is
    never directly modified.
    """

    from backend.shipment_service import discard_stale_runtime

    discard_stale_runtime()

    if RUNTIME_FILE.exists():

        return pd.read_excel(
            RUNTIME_FILE
        )

    if not SOURCE_FILE.exists():

        raise FileNotFoundError(
            "Cleaned shipment file was not found. "
            "Run backend/data_agent.py first."
        )

    df = pd.read_excel(
        SOURCE_FILE
    )

    save_runtime_dataset(
        df
    )

    return df


def save_runtime_dataset(df):
    """
    Save runtime shipment data.
    """

    RUNTIME_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_excel(
        RUNTIME_FILE,
        index=False
    )


def find_runtime_records(
    df,
    tracking_number
):
    """
    Find matching shipment records
    inside the runtime dataset.
    """

    tracking = normalize_tracking_number(
        tracking_number
    )

    if tracking is None:
        return df.iloc[0:0]

    return df[
        df["tracking_number"]
        .astype(str)
        .str.strip()
        .str.upper()
        == tracking
    ]


# =================================================
# AUDIT LOG
# =================================================

def write_audit_log(
    action,
    tracking_number,
    success,
    details=None,
):
    """
    Store every verification and operational
    action in a JSONL audit log.
    """

    AUDIT_LOG_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    event = {
        "timestamp_utc": (
            datetime.now(UTC)
            .isoformat()
        ),

        "action": action,

        "tracking_number": (
            normalize_tracking_number(
                tracking_number
            )
            if tracking_number
            else None
        ),

        "success": success,

        "details": details or {},
    }

    with open(
        AUDIT_LOG_FILE,
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            json.dumps(
                event,
                ensure_ascii=False,
                default=str
            )
            + "\n"
        )


# =================================================
# CUSTOMER VERIFICATION
# =================================================

def verify_customer_phone_last4(
    tracking_number,
    provided_last4
):
    """
    MVP verification assumption:

    Customer verifies identity using
    the last 4 digits of the registered
    phone number.

    Production systems should use
    stronger authentication.
    """

    df = load_runtime_dataset()

    records = find_runtime_records(
        df,
        tracking_number
    )

    # ---------------------------------------------
    # Shipment not found
    # ---------------------------------------------

    if records.empty:

        result = {
            "verified": False,
            "reason": "NOT_FOUND",
            "message": (
                "Shipment was not found."
            )
        }

        write_audit_log(
            action="VERIFY_CUSTOMER",
            tracking_number=tracking_number,
            success=False,
            details=result,
        )

        return result

    # ---------------------------------------------
    # Duplicate shipment
    # ---------------------------------------------

    if len(records) > 1:

        result = {
            "verified": False,
            "reason": "DUPLICATE_RECORD",
            "message": (
                "Multiple shipment records were found. "
                "Verification cannot continue automatically."
            )
        }

        write_audit_log(
            action="VERIFY_CUSTOMER",
            tracking_number=tracking_number,
            success=False,
            details=result,
        )

        return result

    # ---------------------------------------------
    # Get registered phone
    # ---------------------------------------------

    row = records.iloc[0]

    phone = row.get(
        "phone"
    )

    expected_last4 = get_last_four_digits(
        phone
    )

    # ---------------------------------------------
    # Clean customer input
    # ---------------------------------------------

    provided = str(
        provided_last4
    ).strip()

    provided = "".join(
        character
        for character in provided
        if character.isdigit()
    )

    # ---------------------------------------------
    # Phone unavailable
    # ---------------------------------------------

    if expected_last4 is None:

        result = {
            "verified": False,
            "reason": "PHONE_UNAVAILABLE",
            "message": (
                "Customer verification cannot be completed."
            )
        }

        write_audit_log(
            action="VERIFY_CUSTOMER",
            tracking_number=tracking_number,
            success=False,
            details=result,
        )

        return result

    # ---------------------------------------------
    # Invalid input
    # ---------------------------------------------

    if len(provided) != 4:

        result = {
            "verified": False,
            "reason": "INVALID_VERIFICATION_INPUT",
            "message": (
                "Please provide exactly the last 4 digits "
                "of the registered phone number."
            )
        }

        write_audit_log(
            action="VERIFY_CUSTOMER",
            tracking_number=tracking_number,
            success=False,
            details=result,
        )

        return result

    # ---------------------------------------------
    # Wrong digits
    # ---------------------------------------------

    if provided != expected_last4:

        result = {
            "verified": False,
            "reason": "VERIFICATION_FAILED",
            "message": (
                "The provided digits do not match "
                "the registered phone number."
            )
        }

        write_audit_log(
            action="VERIFY_CUSTOMER",
            tracking_number=tracking_number,
            success=False,
            details={
                "reason": "VERIFICATION_FAILED"
            },
        )

        return result

    # ---------------------------------------------
    # Verified
    # ---------------------------------------------

    result = {
        "verified": True,
        "reason": "VERIFIED",
        "message": (
            "Customer identity verified successfully."
        )
    }

    write_audit_log(
        action="VERIFY_CUSTOMER",
        tracking_number=tracking_number,
        success=True,
        details={
            "verification_method":
                "PHONE_LAST_4_DIGITS"
        },
    )

    return result


# =================================================
# RESCHEDULE DELIVERY ACTION
# =================================================

def reschedule_delivery(
    tracking_number,
    new_delivery_date,
    customer_verified=False,
    customer_confirmed=False,
):
    """
    Execute a mocked redelivery action.

    Business rules must return ALLOW
    before any data is changed.
    """

    # ---------------------------------------------
    # Business rule check
    # ---------------------------------------------

    decision = evaluate_reschedule(
        tracking_number=tracking_number,
        customer_verified=customer_verified,
        customer_confirmed=customer_confirmed,
    )

    if (
        decision.get("decision")
        != ACTION_ALLOW
    ):

        result = {
            "success": False,
            "action": "RESCHEDULE_DELIVERY",
            "decision": decision,
            "message": (
                "Reschedule action was not executed."
            )
        }

        write_audit_log(
            action="RESCHEDULE_DELIVERY",
            tracking_number=tracking_number,
            success=False,
            details=result,
        )

        return result

    # ---------------------------------------------
    # Date required
    # ---------------------------------------------

    if (
        new_delivery_date is None
        or str(new_delivery_date).strip()
        == ""
    ):

        result = {
            "success": False,
            "action": "RESCHEDULE_DELIVERY",
            "reason": "DELIVERY_DATE_REQUIRED",
            "message": (
                "A new delivery date is required."
            )
        }

        write_audit_log(
            action="RESCHEDULE_DELIVERY",
            tracking_number=tracking_number,
            success=False,
            details=result,
        )

        return result

    # ---------------------------------------------
    # Validate date format
    # ---------------------------------------------

    try:

        new_date = pd.to_datetime(
            str(new_delivery_date),
            format="%Y-%m-%d",
            errors="raise"
        )

    except Exception:

        result = {
            "success": False,
            "action": "RESCHEDULE_DELIVERY",
            "reason": "INVALID_DATE",
            "message": (
                "Delivery date must use YYYY-MM-DD format."
            )
        }

        write_audit_log(
            action="RESCHEDULE_DELIVERY",
            tracking_number=tracking_number,
            success=False,
            details=result,
        )

        return result

    # ---------------------------------------------
    # Past date check
    # ---------------------------------------------

    today = pd.Timestamp.today().normalize()

    if new_date < today:

        result = {
            "success": False,
            "action": "RESCHEDULE_DELIVERY",
            "reason": "PAST_DATE",
            "message": (
                "The new delivery date cannot be in the past."
            )
        }

        write_audit_log(
            action="RESCHEDULE_DELIVERY",
            tracking_number=tracking_number,
            success=False,
            details=result,
        )

        return result

    # ---------------------------------------------
    # Load runtime data
    # ---------------------------------------------

    df = load_runtime_dataset()

    matches = find_runtime_records(
        df,
        tracking_number
    )

    # ---------------------------------------------
    # Runtime uniqueness check
    # ---------------------------------------------

    if len(matches) != 1:

        result = {
            "success": False,
            "action": "RESCHEDULE_DELIVERY",
            "reason": "RUNTIME_RECORD_NOT_UNIQUE",
            "message": (
                "The shipment could not be uniquely identified "
                "in the runtime dataset."
            )
        }

        write_audit_log(
            action="RESCHEDULE_DELIVERY",
            tracking_number=tracking_number,
            success=False,
            details=result,
        )

        return result

    index = matches.index[0]

    previous_status = df.at[
        index,
        "status"
    ]

    # ---------------------------------------------
    # Add runtime column if necessary
    # ---------------------------------------------

    if (
        "scheduled_redelivery_date"
        not in df.columns
    ):

        df[
            "scheduled_redelivery_date"
        ] = None

    # ---------------------------------------------
    # Execute action
    # ---------------------------------------------

    df.at[
        index,
        "scheduled_redelivery_date"
    ] = new_date.strftime(
        "%Y-%m-%d"
    )

    df.at[
        index,
        "status"
    ] = "Scheduled for Redelivery"

    # ---------------------------------------------
    # Save mock backend
    # ---------------------------------------------

    save_runtime_dataset(
        df
    )

    # ---------------------------------------------
    # Result
    # ---------------------------------------------

    result = {
        "success": True,

        "action":
            "RESCHEDULE_DELIVERY",

        "tracking_number":
            normalize_tracking_number(
                tracking_number
            ),

        "previous_status": (
            None
            if pd.isna(previous_status)
            else str(previous_status)
        ),

        "new_status":
            "Scheduled for Redelivery",

        "scheduled_redelivery_date":
            new_date.strftime(
                "%Y-%m-%d"
            ),

        "message": (
            "Delivery has been rescheduled successfully."
        )
    }

    write_audit_log(
        action="RESCHEDULE_DELIVERY",
        tracking_number=tracking_number,
        success=True,
        details=result,
    )

    return result


# =================================================
# UPDATE DELIVERY ADDRESS ACTION
# =================================================

def update_delivery_address(
    tracking_number,
    new_address,
    customer_verified=False,
    customer_confirmed=False,
):
    """
    Execute a mocked delivery address update.
    """

    # ---------------------------------------------
    # Business rule check
    # ---------------------------------------------

    decision = evaluate_address_update(
        tracking_number=tracking_number,
        new_address=new_address,
        customer_verified=customer_verified,
        customer_confirmed=customer_confirmed,
    )

    if (
        decision.get("decision")
        != ACTION_ALLOW
    ):

        result = {
            "success": False,
            "action": "UPDATE_DELIVERY_ADDRESS",
            "decision": decision,
            "message": (
                "Address update was not executed."
            )
        }

        write_audit_log(
            action="UPDATE_DELIVERY_ADDRESS",
            tracking_number=tracking_number,
            success=False,
            details=result,
        )

        return result

    # ---------------------------------------------
    # Normalize address
    # ---------------------------------------------

    normalized_address = str(
        new_address
    ).strip()

    # ---------------------------------------------
    # Load runtime data
    # ---------------------------------------------

    df = load_runtime_dataset()

    matches = find_runtime_records(
        df,
        tracking_number
    )

    # ---------------------------------------------
    # Runtime uniqueness check
    # ---------------------------------------------

    if len(matches) != 1:

        result = {
            "success": False,
            "action": "UPDATE_DELIVERY_ADDRESS",
            "reason": "RUNTIME_RECORD_NOT_UNIQUE",
            "message": (
                "The shipment could not be uniquely identified "
                "in the runtime dataset."
            )
        }

        write_audit_log(
            action="UPDATE_DELIVERY_ADDRESS",
            tracking_number=tracking_number,
            success=False,
            details=result,
        )

        return result

    index = matches.index[0]

    previous_address = df.at[
        index,
        "delivery_address"
    ]

    # ---------------------------------------------
    # Execute address update
    # ---------------------------------------------

    df.at[
        index,
        "delivery_address"
    ] = normalized_address

    # ---------------------------------------------
    # Save runtime backend
    # ---------------------------------------------

    save_runtime_dataset(
        df
    )

    # ---------------------------------------------
    # Result
    # ---------------------------------------------

    result = {
        "success": True,

        "action":
            "UPDATE_DELIVERY_ADDRESS",

        "tracking_number":
            normalize_tracking_number(
                tracking_number
            ),

        "previous_address": (
            None
            if pd.isna(previous_address)
            else str(previous_address)
        ),

        "new_address":
            normalized_address,

        "message": (
            "Delivery address updated successfully."
        )
    }

    write_audit_log(
        action="UPDATE_DELIVERY_ADDRESS",
        tracking_number=tracking_number,
        success=True,
        details=result,
    )

    return result


# =================================================
# RESET MOCK BACKEND
# =================================================

def reset_runtime_dataset():
    """
    Reset runtime data back to
    the cleaned source dataset.

    Useful before demos and testing.
    """

    if not SOURCE_FILE.exists():

        return {
            "success": False,
            "message": (
                "Cleaned source dataset was not found."
            )
        }

    df = pd.read_excel(
        SOURCE_FILE
    )

    save_runtime_dataset(
        df
    )

    write_audit_log(
        action="RESET_RUNTIME_DATASET",
        tracking_number=None,
        success=True,
        details={
            "records": len(df)
        },
    )

    return {
        "success": True,
        "records": len(df),
        "message": (
            "Runtime dataset reset successfully."
        )
    }


# =================================================
# SIMPLE TERMINAL TEST
# =================================================

if __name__ == "__main__":

    print(
        "Action Tools Test"
    )

    print(
        "-" * 50
    )

    tracking = input(
        "Enter tracking number: "
    )

    print()

    print(
        "Verification Test"
    )

    last4 = input(
        "Enter last 4 digits of registered phone: "
    )

    verification = verify_customer_phone_last4(
        tracking,
        last4
    )

    print()

    print(
        verification
    )

    # ---------------------------------------------
    # Stop if verification fails
    # ---------------------------------------------

    if not verification["verified"]:

        print()

        print(
            "Verification failed. "
            "No operational action will be executed."
        )

    else:

        print()

        print(
            "1 = Reschedule Delivery"
        )

        print(
            "2 = Update Delivery Address"
        )

        choice = input(
            "Choose action: "
        ).strip()

        # =========================================
        # RESCHEDULE
        # =========================================

        if choice == "1":

            new_date = input(
                "Enter new delivery date YYYY-MM-DD: "
            )

            confirm = input(
                "Confirm reschedule? y/n: "
            ).strip().lower()

            result = reschedule_delivery(
                tracking_number=tracking,
                new_delivery_date=new_date,
                customer_verified=True,
                customer_confirmed=(
                    confirm == "y"
                ),
            )

            print()

            print(
                result
            )

        # =========================================
        # ADDRESS UPDATE
        # =========================================

        elif choice == "2":

            new_address = input(
                "Enter new delivery address: "
            )

            confirm = input(
                "Confirm address update? y/n: "
            ).strip().lower()

            result = update_delivery_address(
                tracking_number=tracking,
                new_address=new_address,
                customer_verified=True,
                customer_confirmed=(
                    confirm == "y"
                ),
            )

            print()

            print(
                result
            )

        else:

            print()

            print(
                "Invalid action."
            )
