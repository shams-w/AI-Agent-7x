import os
import secrets
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.shipment_service import (
    get_shipment,
    find_shipments_by_phone,
    can_reschedule_delivery,
    can_update_address,
    collect_customer_phone,
    repair_delivery_address,
    create_weight_review_case,
    get_review_status,
    resolve_weight_review,
)

from backend.intent_agent import understand

from backend.actions import (
    verify_customer_phone_last4,
    reschedule_delivery,
    update_delivery_address,
    reset_runtime_dataset,
)


# =================================================
# APP
# =================================================

app = FastAPI(
    title="7X FDE AI Shipment Agent API",
    version="1.5.0",
    description=(
        "Mock backend API for the 7X FDE AI shipment assistant."
    ),
)


# =================================================
# CORS
# =================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get(
            "FDE_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =================================================
# VERIFICATION TOKEN STORE
# =================================================

# MVP-only in-memory verification store.
# Production would use a proper session / identity service.
VERIFICATION_TTL_SECONDS = 10 * 60
verification_tokens = {}

# Brute-force protection for last-4 verification (10,000 combinations).
# MVP: in-memory, per tracking number. Production: shared store + per-client limits.
MAX_VERIFICATION_ATTEMPTS = 5
VERIFICATION_LOCK_SECONDS = 15 * 60
failed_verifications = {}  # tracking -> {"count": int, "locked_until": float}


def verification_locked(tracking_number):
    entry = failed_verifications.get(normalize_tracking(tracking_number))
    if not entry:
        return False
    if entry.get("locked_until") and entry["locked_until"] > time.time():
        return True
    if entry.get("locked_until") and entry["locked_until"] <= time.time():
        failed_verifications.pop(normalize_tracking(tracking_number), None)
    return False


def register_failed_verification(tracking_number):
    key = normalize_tracking(tracking_number)
    entry = failed_verifications.setdefault(key, {"count": 0, "locked_until": None})
    entry["count"] += 1
    if entry["count"] >= MAX_VERIFICATION_ATTEMPTS:
        entry["locked_until"] = time.time() + VERIFICATION_LOCK_SECONDS
    return max(MAX_VERIFICATION_ATTEMPTS - entry["count"], 0)


def normalize_tracking(value):
    if value is None:
        return ""

    return str(value).strip().upper()


def issue_verification_token(tracking_number):
    token = secrets.token_urlsafe(32)

    verification_tokens[token] = {
        "tracking_number": normalize_tracking(
            tracking_number
        ),
        "expires_at": (
            time.time()
            + VERIFICATION_TTL_SECONDS
        ),
    }

    return token


def validate_verification_token(
    token,
    tracking_number,
):
    if not token:
        return False

    session = verification_tokens.get(
        token
    )

    if session is None:
        return False

    if session["expires_at"] < time.time():
        verification_tokens.pop(
            token,
            None,
        )
        return False

    if (
        session["tracking_number"]
        != normalize_tracking(
            tracking_number
        )
    ):
        return False

    return True


def revoke_verification_token(token):
    if token:
        verification_tokens.pop(
            token,
            None,
        )


def clear_expired_tokens():
    now = time.time()

    expired = [
        token
        for token, session
        in verification_tokens.items()
        if session["expires_at"] < now
    ]

    for token in expired:
        verification_tokens.pop(
            token,
            None,
        )


# =================================================
# REQUEST MODELS
# =================================================

class VerificationRequest(BaseModel):
    tracking_number: str
    last4: str


class FindShipmentRequest(BaseModel):
    phone_number: str


class EligibilityRequest(BaseModel):
    tracking_number: str
    intent: str


class RescheduleRequest(BaseModel):
    tracking_number: str
    new_delivery_date: str
    verification_token: str
    customer_confirmed: bool = False


class AddressUpdateRequest(BaseModel):
    tracking_number: str
    new_address: str
    verification_token: str
    customer_confirmed: bool = False


class UnderstandRequest(BaseModel):
    message: str
    state: str | None = None


class ContactPhoneRequest(BaseModel):
    tracking_number: str
    phone_number: str


class RepairAddressRequest(BaseModel):
    tracking_number: str
    new_address: str
    verification_token: str


# =================================================
# ROOT
# =================================================

@app.get("/")
def root():
    return {
        "service": "7X FDE AI Shipment Agent API",
        "status": "running",
        "version": "1.5.0",
    }


# =================================================
# HEALTH
# =================================================

@app.get("/health")
def health():
    clear_expired_tokens()

    return {
        "status": "ok"
    }


# =================================================
# SHIPMENT LOOKUP
# =================================================

@app.get("/shipment/{tracking_number}")
def shipment_lookup(
    tracking_number: str
):
    result = get_shipment(
        tracking_number
    )

    if (
        result.get("result") == "NEEDS_REVIEW"
        and result.get("review_required")
        and result.get("issue", {}).get("handling") == "INTERNAL_REVIEW"
    ):
        review = create_weight_review_case(
            tracking_number,
            result.get("issue", {}).get("code", "DATA_REVIEW_REQUIRED"),
        )
        result["review"] = review

    # Mask phone before returning publicly.
    if (
        result.get("success")
        and "shipment" in result
    ):
        shipment = result["shipment"]

        phone = shipment.get("phone")

        if phone is not None:
            phone_text = str(phone)

            if phone_text.endswith(".0"):
                phone_text = phone_text[:-2]

            digits = "".join(
                character
                for character in phone_text
                if character.isdigit()
            )

            if len(digits) >= 4:
                shipment["phone"] = (
                    "*" * (len(digits) - 4)
                    + digits[-4:]
                )
            else:
                shipment["phone"] = "****"

    return result


# =================================================
# MESSAGE UNDERSTANDING (LLM + deterministic fallback)
# =================================================

@app.post("/agent/understand")
def agent_understand(request: UnderstandRequest):
    """
    Understand a free-text customer message (English or Arabic).

    Returns intent, language, yes/no answer and grounded entities only.
    It never executes anything and never decides eligibility; the existing
    deterministic endpoints remain the only way to change shipment data.
    """
    return understand(request.message, request.state)


# =================================================
# FIND MY SHIPMENT
# =================================================

@app.post("/find-shipments")
def find_my_shipments(
    request: FindShipmentRequest
):
    """
    Find active shipments linked to a registered mobile number.

    MVP identification capability.
    Production should protect this with stronger authentication.
    """

    return find_shipments_by_phone(
        request.phone_number
    )


# =================================================
# EARLY ACTION ELIGIBILITY
# =================================================

@app.post("/eligibility")
def check_eligibility(
    request: EligibilityRequest
):
    """
    Check action eligibility before asking the customer
    for verification or new operational information.
    """

    intent = str(
        request.intent
    ).strip().lower()

    if intent == "reschedule":
        result = can_reschedule_delivery(
            request.tracking_number
        )

    elif intent == "address":
        result = can_update_address(
            request.tracking_number
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported intent. "
                "Use 'reschedule' or 'address'."
            ),
        )

    return {
        "intent": intent,
        **result,
    }


# =================================================
# VERIFY CUSTOMER
# =================================================

@app.post("/verify")
def verify_customer(
    request: VerificationRequest
):
    clear_expired_tokens()

    if verification_locked(request.tracking_number):
        return {
            "verified": False,
            "reason": "TOO_MANY_ATTEMPTS",
            "attempts_remaining": 0,
            "message": (
                "Too many failed verification attempts. "
                "Verification is temporarily locked for this shipment."
            ),
        }

    result = verify_customer_phone_last4(
        tracking_number=request.tracking_number,
        provided_last4=request.last4,
    )

    if result.get("reason") == "VERIFICATION_FAILED":
        remaining = register_failed_verification(request.tracking_number)
        result["attempts_remaining"] = remaining
        if remaining == 0:
            result["reason"] = "TOO_MANY_ATTEMPTS"
            result["message"] = (
                "Too many failed verification attempts. "
                "Verification is temporarily locked for this shipment."
            )

    if result.get("verified"):
        failed_verifications.pop(normalize_tracking(request.tracking_number), None)
        token = issue_verification_token(
            request.tracking_number
        )

        result["verification_token"] = token
        result[
            "verification_expires_in_seconds"
        ] = VERIFICATION_TTL_SECONDS

    return result


# =================================================
# COLLECT MISSING / INVALID CONTACT PHONE (MVP)
# =================================================

@app.post("/collect-phone")
def collect_phone(request: ContactPhoneRequest):
    """
    Prototype fallback when the shipment has no usable registered phone.

    The number is format-validated and stored only in the runtime copy.
    This is NOT equivalent to production OTP/account verification.
    A short-lived token is still issued so action endpoints remain server-enforced.
    """
    clear_expired_tokens()

    result = collect_customer_phone(
        request.tracking_number,
        request.phone_number,
    )

    if not result.get("success"):
        return result

    token = issue_verification_token(request.tracking_number)
    return {
        **result,
        "verification_token": token,
        "verification_expires_in_seconds": VERIFICATION_TTL_SECONDS,
        "verification_method": "CUSTOMER_PROVIDED_PHONE_MVP",
        "identity_assurance": "LIMITED_MVP",
    }


# =================================================
# ADDRESS PREREQUISITE FOR RESCHEDULE
# =================================================

@app.post("/repair-address")
def repair_address(request: RepairAddressRequest):
    require_verification(
        request.verification_token,
        request.tracking_number,
    )

    # Do not revoke the token here because the customer still needs
    # to finish the reschedule action in the same verified session.
    return repair_delivery_address(
        request.tracking_number,
        request.new_address,
    )


# =================================================
# INTERNAL SHIPMENT REVIEW (MOCK WORKFLOW)
# =================================================

@app.post("/review/{tracking_number}")
def open_review(tracking_number: str):
    return create_weight_review_case(tracking_number)


@app.get("/review/{tracking_number}")
def review_status(tracking_number: str):
    return get_review_status(tracking_number)


@app.post("/review/{tracking_number}/resolve")
def resolve_review(tracking_number: str):
    """
    Internal-demo endpoint simulating an operations team resolving the anomaly.
    It does not invent or silently rewrite source operational data.
    """
    return resolve_weight_review(tracking_number)


# =================================================
# SECURE ACTION HELPER
# =================================================


def require_verification(
    token,
    tracking_number,
):
    clear_expired_tokens()

    if not validate_verification_token(
        token,
        tracking_number,
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Verification is missing, invalid, expired, "
                "or does not belong to this shipment."
            ),
        )


# =================================================
# RESCHEDULE DELIVERY
# =================================================

@app.post("/reschedule")
def reschedule(
    request: RescheduleRequest
):
    require_verification(
        request.verification_token,
        request.tracking_number,
    )

    result = reschedule_delivery(
        tracking_number=request.tracking_number,
        new_delivery_date=request.new_delivery_date,
        customer_verified=True,
        customer_confirmed=request.customer_confirmed,
    )

    if result.get("success"):
        revoke_verification_token(
            request.verification_token
        )

    return result


# =================================================
# UPDATE ADDRESS
# =================================================

@app.post("/update-address")
def update_address(
    request: AddressUpdateRequest
):
    require_verification(
        request.verification_token,
        request.tracking_number,
    )

    result = update_delivery_address(
        tracking_number=request.tracking_number,
        new_address=request.new_address,
        customer_verified=True,
        customer_confirmed=request.customer_confirmed,
    )

    if result.get("success"):
        revoke_verification_token(
            request.verification_token
        )

    return result


# =================================================
# RESET DEMO DATA
# =================================================

@app.post("/reset")
def reset_demo_data():
    verification_tokens.clear()
    failed_verifications.clear()

    return reset_runtime_dataset()
