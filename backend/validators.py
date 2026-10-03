"""Deterministic field validators shared by shipment_service.py and data_agent.py.

Pure functions only: no I/O, no business decisions. They normalize a value
when the result is unambiguous and return None / an error otherwise; they
never guess, pad, or substitute a value.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta

# -------------------------------------------------
# Addresses
# -------------------------------------------------

# Values that are not a deliverable address. Compared after trim + casefold.
ADDRESS_PLACEHOLDERS = {
    "test", "n/a", "na", "asdf", "call me", "none", "null", "-", ".",
    "same as before",
}


def is_placeholder_address(value) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return " ".join(str(value).split()).casefold() in ADDRESS_PLACEHOLDERS


# -------------------------------------------------
# UAE mobile numbers
# -------------------------------------------------

# Prefixes accepted for numbers a customer provides in this MVP.
MVP_MOBILE_PREFIXES = {"50", "52", "54", "55", "56", "58"}

# Obvious dummy subscriber numbers (after the leading 5).
_FAKE_LOCAL = {"500000000", "512345678", "599999999"}

_ALLOWED_PHONE_CHARS = re.compile(r"^\+?[0-9][0-9 \-]*$")


def _phone_digits(value):
    """Digits of a phone value, or None if it contains anything but digits,
    spaces, hyphens and one leading '+'. Excel float artifacts (e.g.
    971536385467.0) are accepted only when they are exact integers."""
    if value is None:
        return None, False
    if isinstance(value, bool):
        return None, False
    if isinstance(value, (int,)):
        return str(value), False
    if isinstance(value, float):
        if math.isnan(value) or not value.is_integer():
            return None, False
        return str(int(value)), False
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    if not text or not _ALLOWED_PHONE_CHARS.match(text):
        return None, False
    return re.sub(r"[ \-]", "", text).lstrip("+"), text.startswith("+")


def _to_canonical(digits: str, has_plus: bool):
    """Map 05XXXXXXXX / 9715XXXXXXXX / +9715XXXXXXXX / 009715XXXXXXXX to
    +9715XXXXXXXX. Anything else -> None. Digits are never added or changed."""
    if digits is None:
        return None
    if has_plus:
        national = digits[3:] if digits.startswith("971") else None
    elif digits.startswith("00971"):
        national = digits[5:]
    elif digits.startswith("971"):
        national = digits[3:]
    elif digits.startswith("0"):
        national = digits[1:]
    else:
        national = None
    if national is None or not re.fullmatch(r"5\d{8}", national):
        return None
    if len(set(national)) == 1 or national in _FAKE_LOCAL:
        return None
    return "+971" + national


def normalize_uae_mobile(value):
    """Strict rule for numbers a CUSTOMER provides: a structurally valid UAE
    mobile on an MVP prefix (050/052/054/055/056/058). Returns the canonical
    +9715XXXXXXXX form, or None if invalid."""
    digits, has_plus = _phone_digits(value)
    canonical = _to_canonical(digits, has_plus)
    if canonical is None or canonical[4:6] not in MVP_MOBILE_PREFIXES:
        return None
    return canonical


def normalize_registered_phone(value):
    """Normalization for numbers ALREADY ON FILE. Same structural rules
    (UAE mobile, 9 national digits starting with 5, no letters), but any 5X
    prefix is kept usable so existing customers can still verify. Returns
    +9715XXXXXXXX or None."""
    digits, has_plus = _phone_digits(value)
    return _to_canonical(digits, has_plus)


# -------------------------------------------------
# Dates
# -------------------------------------------------

# Excel serial dates are accepted only inside a plausible operational window.
EXCEL_EPOCH = date(1899, 12, 30)
EXCEL_SERIAL_MIN = (date(2000, 1, 1) - EXCEL_EPOCH).days   # 36526
EXCEL_SERIAL_MAX = (date(2099, 12, 31) - EXCEL_EPOCH).days  # 73050

_TEXT_MONTH = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})$")


def parse_text_month_date(value):
    """'22 Aug 2026', '3 Sep 2026', '01 January 2026' -> date. None if not that
    shape or not a real calendar date (e.g. '31 Feb 2026')."""
    if value is None:
        return None
    match = _TEXT_MONTH.match(str(value).strip())
    if not match:
        return None
    day, month, year = match.groups()
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(f"{int(day)} {month.title()} {year}", fmt).date()
        except ValueError:
            continue
    return None


def is_excel_serial_shape(value) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return not (isinstance(value, float) and math.isnan(value))
    return bool(re.fullmatch(r"\d{1,7}(\.\d+)?", str(value).strip()))


def parse_excel_serial(value):
    """Integer Excel serial inside [2000-01-01, 2099-12-31] -> date. Fractions,
    out-of-range values and non-numbers -> None."""
    if not is_excel_serial_shape(value):
        return None
    number = float(value)
    if not number.is_integer():
        return None
    serial = int(number)
    if not EXCEL_SERIAL_MIN <= serial <= EXCEL_SERIAL_MAX:
        return None
    return EXCEL_EPOCH + timedelta(days=serial)
