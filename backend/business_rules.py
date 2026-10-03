from backend.shipment_service import (
    can_reschedule_delivery,
    can_update_address,
    is_valid_delivery_address,
)

ACTION_ALLOW = "ALLOW"
ACTION_BLOCK = "BLOCK"
ACTION_ASK = "ASK"
ACTION_ESCALATE = "ESCALATE"


def evaluate_reschedule(
    tracking_number,
    customer_verified=False,
    customer_confirmed=False,
):
    eligibility = can_reschedule_delivery(tracking_number)

    if not eligibility.get("allowed"):
        return {
            "decision": ACTION_BLOCK,
            "reason": eligibility.get("reason", "NOT_ELIGIBLE"),
            "message": eligibility.get("message", "This shipment is not eligible for rescheduling."),
        }

    if eligibility.get("requires_address_first"):
        return {
            "decision": ACTION_ASK,
            "reason": "ADDRESS_REQUIRED",
            "message": "A valid delivery address is required before the delivery time can be changed.",
        }

    if not customer_verified:
        return {
            "decision": ACTION_BLOCK,
            "reason": "CUSTOMER_NOT_VERIFIED",
            "message": "Customer verification is required before changing the delivery time.",
        }

    if not customer_confirmed:
        return {
            "decision": ACTION_ASK,
            "reason": "CONFIRMATION_REQUIRED",
            "message": "Customer confirmation is required before changing the delivery time.",
        }

    return {
        "decision": ACTION_ALLOW,
        "reason": eligibility.get("reason", "ELIGIBLE"),
        "message": "Delivery-time change is allowed.",
    }


def evaluate_address_update(
    tracking_number,
    new_address,
    customer_verified=False,
    customer_confirmed=False,
):
    eligibility = can_update_address(tracking_number)

    if not eligibility.get("allowed"):
        return {
            "decision": ACTION_BLOCK,
            "reason": eligibility.get("reason", "NOT_ELIGIBLE"),
            "message": eligibility.get("message", "This shipment is not eligible for an address change."),
        }

    if not customer_verified:
        return {
            "decision": ACTION_BLOCK,
            "reason": "CUSTOMER_NOT_VERIFIED",
            "message": "Customer verification is required before changing the delivery address.",
        }

    if not is_valid_delivery_address(new_address):
        return {
            "decision": ACTION_ASK,
            "reason": "INVALID_NEW_ADDRESS",
            "message": "Please enter a complete delivery address.",
        }

    current_address = eligibility.get("current_address")
    if current_address and str(current_address).strip().casefold() == str(new_address).strip().casefold():
        return {
            "decision": ACTION_ASK,
            "reason": "ADDRESS_UNCHANGED",
            "message": "The new address is the same as the current delivery address.",
        }

    if not customer_confirmed:
        return {
            "decision": ACTION_ASK,
            "reason": "CONFIRMATION_REQUIRED",
            "message": "Customer confirmation is required before changing the delivery address.",
        }

    return {
        "decision": ACTION_ALLOW,
        "reason": "ELIGIBLE",
        "message": "Delivery-address change is allowed.",
    }
