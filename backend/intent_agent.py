"""Customer-message understanding (English + Arabic).

Responsibility split
--------------------
* The LLM (Claude, via the Anthropic Messages API) is used ONLY to understand
  what the customer said: intent, language, yes/no answers and entities.
  It is forced to answer through a strict tool schema.
* Everything the LLM returns is re-validated deterministically. Entities must
  be grounded in the customer's own text (a tracking number, phone or address
  that does not appear in the message is discarded), dates must be real
  calendar dates that are not in the past.
* Business rules, verification, confirmation and execution are NOT done here.
  They stay in business_rules.py / actions.py / app.py, unchanged.
* If no API key is configured, the call fails or times out, or the output is
  invalid, a deterministic bilingual parser is used instead. The system works
  fully without the LLM, it just understands less free-form phrasing.

Environment
-----------
ANTHROPIC_API_KEY        enables the LLM path
FDE_INTENT_LLM           "auto" (default: use LLM when a key exists) | "off"
FDE_INTENT_MODEL         default "claude-haiku-4-5"
FDE_ANTHROPIC_BASE_URL   default "https://api.anthropic.com"
FDE_INTENT_TIMEOUT       seconds, default 8
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta

import httpx

INTENTS = {"reschedule", "address", "multiple", "other", "greeting", "none"}

# -------------------------------------------------
# Text normalisation helpers
# -------------------------------------------------

_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ARABIC_LETTER = re.compile(r"[؀-ۿ]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_DIACRITICS = re.compile(r"[ً-ْـ]")  # tashkeel + tatweel


def normalize_digits(text: str) -> str:
    return str(text or "").translate(_DIGIT_MAP)


def _norm_ar(text: str) -> str:
    """Lower-case + simplify Arabic spelling variants for keyword matching."""
    t = normalize_digits(text).lower()
    t = _DIACRITICS.sub("", t)
    t = re.sub("[إأآ]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه").replace("گ", "ك").replace("چ", "ج")
    return re.sub(r"\s+", " ", t).strip()


def detect_language(text: str) -> str:
    ar = len(_ARABIC_LETTER.findall(text or ""))
    en = len(_LATIN_LETTER.findall(text or ""))
    # Tracking numbers ("EX400238AE") add Latin letters to Arabic sentences.
    en -= 4 * len(re.findall(r"[A-Za-z]{2}\d{6}[A-Za-z]{2}", text or ""))
    return "ar" if ar > 0 and ar >= max(en, 0) else "en"


# -------------------------------------------------
# Entity extraction (deterministic)
# -------------------------------------------------

TRACKING_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2}\d{6}[A-Za-z]{2})(?![A-Za-z0-9])")
PHONE_RE = re.compile(r"(?<!\d)((?:\+|00)?971[\s-]?5\d(?:[\s-]?\d){7}|05\d(?:[\s-]?\d){7})(?!\d)")


def extract_tracking(text: str):
    match = TRACKING_RE.search(normalize_digits(text))
    return match.group(1).upper() if match else None


def extract_phone(text: str):
    match = PHONE_RE.search(normalize_digits(text))
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("05"):
        digits = "971" + digits[1:]
    return "+" + digits


def extract_last4(text: str):
    t = normalize_digits(text).strip()
    match = re.fullmatch(r"\D*(\d{4})\D*", t)
    return match.group(1) if match else None


def extract_selection(text: str):
    t = normalize_digits(text).strip()
    match = re.fullmatch(r"\D{0,12}?(\d{1,2})\D{0,12}", t)
    return int(match.group(1)) if match else None


_WEEKDAYS = {
    0: ["monday", "الاثنين", "الاتنين", "يوم الاثنين"],
    1: ["tuesday", "الثلاثاء", "التلات", "الثلاثا"],
    2: ["wednesday", "الاربعاء", "الاربع"],
    3: ["thursday", "الخميس"],
    4: ["friday", "الجمعه"],
    5: ["saturday", "السبت"],
    6: ["sunday", "الاحد"],
}

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "مايو": 5, "يونيو": 6,
    "يوليو": 7, "اغسطس": 8, "سبتمبر": 9, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}

_DAY_AFTER_TOMORROW = ["day after tomorrow", "بعد بكره", "بعد بكرا", "بعد غد", "بعد بكرة", "بعد باكر", "بعد باجر"]
_TOMORROW = ["tomorrow", "tmrw", "بكره", "بكرا", "بكرة", "غدا", "باكر", "باجر"]
_TODAY = ["today", "النهارده", "النهاردة", "اليوم", "الحين"]


def _safe_date(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None


def extract_date(text: str, today: date | None = None):
    """Return an ISO date string or None. Never guesses ambiguous input."""
    today = today or date.today()
    raw = normalize_digits(text)
    t = _norm_ar(raw)

    m = re.search(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", raw)
    if m:
        d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d.isoformat() if d else None

    # UAE convention is day-first. The customer always sees the resolved date
    # on the confirmation card before anything changes.
    m = re.search(r"(?<!\d)(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})(?!\d)", raw)
    if m:
        year = int(m.group(3))
        year = year + 2000 if year < 100 else year
        d = _safe_date(year, int(m.group(2)), int(m.group(1)))
        return d.isoformat() if d else None

    for name, month in _MONTHS.items():
        m = re.search(rf"(?<!\w)(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{name}(?!\w)", t) or \
            re.search(rf"(?<!\w){name}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?!\w)", t)
        if m:
            day = int(m.group(1))
            # An explicit year is always respected ("3 Sep 2026" stays 2026,
            # even if that is in the past — the past-date rule rejects it).
            year_match = re.match(r"\s*,?\s*(\d{4})(?!\d)", t[m.end():])
            if year_match:
                d = _safe_date(int(year_match.group(1)), month, day)
            else:
                d = _safe_date(today.year, month, day)
                if d and d < today:
                    d = _safe_date(today.year + 1, month, day)
            return d.isoformat() if d else None

    if any(k in t for k in _DAY_AFTER_TOMORROW):
        return (today + timedelta(days=2)).isoformat()

    m = re.search(r"(?:in|after|بعد)\s+(\d{1,2})\s*(?:days?|ايام|يوم)", t)
    if m:
        return (today + timedelta(days=int(m.group(1)))).isoformat()

    words = set(re.findall(r"[\w]+", t))
    if any(k in words for k in _TOMORROW):
        return (today + timedelta(days=1)).isoformat()
    if any(k in words for k in _TODAY):
        return today.isoformat()

    for weekday, names in _WEEKDAYS.items():
        if any(_norm_ar(n) in words for n in names):
            delta = (weekday - today.weekday()) % 7 or 7
            return (today + timedelta(days=delta)).isoformat()

    return None


# -------------------------------------------------
# Intent keywords (deterministic fallback)
# -------------------------------------------------

_RESCHEDULE_TERMS = [
    # English
    "reschedul", "redeliver", "re-deliver", "re deliver", "deliver again", "delivery again",
    "another day", "another date", "different day", "different date", "other day",
    "new date", "new delivery date", "delivery date", "delivery time", "delivery day",
    "change the date", "change date", "change the day", "change the time",
    "missed", "wasn't home", "wasnt home", "was not home", "not home", "not at home",
    "won't be home", "wont be home", "will not be home", "not available", "postpone",
    "delay", "later date", "come back", "try again", "deliver it tomorrow",
    "deliver tomorrow", "bring it", "deliver on", "deliver it on", "deliver next",
    # Arabic (MSA + Gulf + Egyptian)
    "موعد", "ميعاد", "معاد", "تاجيل", "ااجل", "اجيل", "نأجل", "يتأجل", "جدوله", "جدولة",
    "اعاده التوصيل", "اعاده توصيل", "اعادة التوصيل", "توصيل مره ثانيه", "توصيل مره تانيه",
    "مره تانيه", "مره ثانيه", "يوم تاني", "يوم ثاني", "يوم اخر", "تاريخ التوصيل",
    "وقت التوصيل", "تاريخ ثاني", "تاريخ تاني", "تاريخ جديد", "فاتني", "فاتتني",
    "مكنتش موجود", "ما كنت موجود", "ماكنت موجود", "مش موجود", "مو موجود", "ماني موجود",
    "مكنتش في البيت", "ما كنت في البيت", "مش في البيت", "مو في البيت", "مب موجود",
    "ارجعوا", "يرجع يوصل", "يجيبها", "تجيبوها", "جيبوها", "وصلوها بكره", "وصلوها باجر",
    "التوصيل بكره", "التوصيل باجر", "يوصلها", "ما في احد", "مافي احد", "محد في البيت",
    "مفيش حد", "no one was home", "nobody was home", "nobody home", "no one home",
]

_ADDRESS_TERMS = [
    # English
    "address", "location", "deliver to a different", "deliver to another",
    "deliver it to", "send it to", "ship it to", "ship to", "moved", "new place",
    "different place", "different location", "wrong place", "change where",
    # Arabic
    "عنوان", "العنوان", "عنواني", "لوكيشن", "لوكيشان", "الموقع", "موقع التوصيل",
    "مكان التوصيل", "المكان", "مكان ثاني", "مكان تاني", "مكان اخر", "مكان جديد",
    "نقلت", "انتقلت", "عزلت", "سكن جديد", "بيت جديد", "شقه جديده", "شقتي الجديده",
    "وصلوها علي", "ابعتوها علي", "ابعثوها الي", "ارسلوها الي", "حولوها",
]

_STATUS_TERMS = [
    "where is", "where's", "track my", "status of", "when will", "refund", "complaint",
    "وين", "فين", "حالة الشحنه", "حاله الشحنه", "متى توصل", "امتي توصل", "امتى توصل",
    "تتبع", "استرجاع", "شكوى",
]

_GREETING_TERMS = [
    "hi", "hello", "hey", "good morning", "good evening", "salam",
    "السلام", "سلام", "مرحبا", "اهلا", "هلا", "صباح", "مساء",
]

_YES = {
    "yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "correct", "i have it",
    "i do", "have it", "i have", "نعم", "ايوه", "ايوا", "ايو", "اه", "ايه", "اكيد",
    "تمام", "معايا", "معي", "عندي", "موجود", "اي", "ايوة", "صح", "اوكي", "اوك",
}
_NO = {
    "no", "n", "nope", "nah", "i don't", "i dont", "don't have", "dont have",
    "not sure", "don't know", "dont know", "i don't know", "no idea", "forgot",
    "لا", "لاء", "لأ", "لء", "مش معايا", "ماعندي", "ما عندي", "معنديش",
    "مش عارف", "معرفش", "ما اعرف", "مااعرف", "مش فاكر", "نسيت", "نسيته", "مو معي", "ماعرف",
}


def _contains_any(t: str, terms) -> bool:
    padded = f" {t} "
    for term in terms:
        term_n = _norm_ar(term)
        if term_n.isascii() and len(term_n) <= 4:
            if re.search(rf"(?<![a-z]){re.escape(term_n)}(?![a-z])", t):
                return True
        elif term_n in padded:
            return True
    return False


def extract_yes_no(text: str):
    t = _norm_ar(text).strip(" .!؟?،,")
    if not t:
        return None
    norm_yes = {_norm_ar(x) for x in _YES}
    norm_no = {_norm_ar(x) for x in _NO}
    if t in norm_no or any(t.startswith(n + " ") for n in norm_no if len(n) > 1):
        return "no"
    if t in norm_yes or any(t.startswith(y + " ") for y in norm_yes if len(y) > 1):
        return "yes"
    if any(phrase in t for phrase in ("don't know", "dont know", "مش عارف", "معرفش", "ما اعرف", "مش فاكر", "نسيت")):
        return "no"
    return None


_ADDRESS_AFTER = [
    re.compile(r"^(?:please\s+)?(?:change|update|make|set|move)\s+it\s+to\s*[:\-]?\s*(.+)$", re.I | re.S),
    re.compile(r"^(?:the\s+)?new\s+address\s*(?:is|:)\s*(.+)$", re.I | re.S),
    re.compile(r"(?:address|location|deliver(?:y)?(?: it)?|send it|ship it)\b.*?\b(?:to|is)\b\s*[:\-]?\s*(.+)$", re.I | re.S),
    re.compile(r"(?:العنوان|عنواني|عنوان|المكان|الموقع)(?:\s+(?:التوصيل|الشحنة|الشحنه|الجديد|الصحيح))*\s*(?:لـ|ل|الى|إلى|علي|على|هو|:)\s*[:\-]?\s*(.+)$", re.S),
    re.compile(r"(?:وصلوها|ابعتوها|ابعثوها|ارسلوها|حولوها|غيره|غيروه|خليه)\s*(?:على|علي|الى|إلى|لـ|ل)\s*(.+)$", re.S),
]


def extract_address(text: str, whole_message_is_address: bool = False):
    from backend.shipment_service import is_valid_delivery_address

    raw = str(text or "").strip()
    candidate = None
    for pattern in _ADDRESS_AFTER:
        m = pattern.search(raw)
        if m:
            candidate = m.group(1)
            break
    if candidate is None and whole_message_is_address:
        candidate = raw
    if not candidate:
        return None
    candidate = candidate.strip(" \t\n.:-،?؟!ـ")
    if not whole_message_is_address:
        # Inline extraction must look like a real address, not "my new address".
        lowered = _norm_ar(candidate)
        looks_structured = bool(re.search(r"\d", normalize_digits(candidate))) or (
            ("," in candidate or "،" in candidate) and len(candidate.split()) >= 3
        )
        if not looks_structured or "address" in lowered or "عنوان" in lowered:
            return None
        # "عنوان التوصيل للشحنة EX…" — the "ل" belongs to "للشحنة", not "to".
        if re.match(r"^(?:ال)?(?:شحن|طلب|رقم|طرد)", lowered):
            return None
    return candidate if is_plausible_address(candidate) else None


def is_plausible_address(candidate) -> bool:
    """Shared check for rule- and LLM-extracted addresses."""
    from backend.shipment_service import is_valid_delivery_address

    if not candidate or TRACKING_RE.search(normalize_digits(candidate)):
        return False  # a tracking number is never part of a delivery address
    return is_valid_delivery_address(candidate)


def rules_understand(message: str, state: str | None = None, today: date | None = None) -> dict:
    t = _norm_ar(message)
    wants_reschedule = _contains_any(t, _RESCHEDULE_TERMS)
    wants_address = _contains_any(t, _ADDRESS_TERMS)

    # A date phrase alone ("can you bring it tomorrow?") is a reschedule signal.
    has_date = extract_date(message, today) is not None
    if not wants_reschedule and not wants_address and has_date and _contains_any(
        t, ["deliver", "bring", "توصيل", "وصل", "يجيب", "جيب", "شحنه", "طلب"]
    ):
        wants_reschedule = True

    # An explicit new date together with an address change = both requests.
    if wants_address and has_date:
        wants_reschedule = True

    if wants_reschedule and wants_address:
        # "change delivery date" mentions "delivery" but not an address;
        # an explicit address phrase with an explicit new date is "multiple".
        intent = "multiple"
    elif wants_reschedule:
        intent = "reschedule"
    elif wants_address:
        intent = "address"
    elif _contains_any(t, _STATUS_TERMS):
        intent = "other"
    elif _contains_any(t, _GREETING_TERMS) and len(t.split()) <= 4:
        intent = "greeting"
    else:
        intent = "none"

    in_address_step = state in ("WAITING_FOR_NEW_ADDRESS", "WAITING_FOR_PREREQ_ADDRESS")
    address = extract_address(message, whole_message_is_address=in_address_step)
    if (
        address
        and in_address_step
        and address == message.strip(" \t\n.:-،?؟!ـ")
        and intent != "none"
        and not re.search(r"\d", normalize_digits(message))
    ):
        # "actually I'd rather reschedule" is a request, not an address.
        address = None

    return {
        "intent": intent,
        "answer": extract_yes_no(message),
        "entities": {
            "tracking_number": extract_tracking(message),
            "phone": extract_phone(message),
            "delivery_date": extract_date(message, today),
            "address": address,
        },
    }


# -------------------------------------------------
# LLM path
# -------------------------------------------------

_TOOL = {
    "name": "record_understanding",
    "description": "Record what the customer is asking for. Only extract values that literally appear in the message (dates may be resolved to ISO).",
    "input_schema": {
        "type": "object",
        "properties": {
            "language": {"type": "string", "enum": ["en", "ar"]},
            "intent": {
                "type": "string",
                "enum": sorted(INTENTS),
                "description": (
                    "reschedule = change delivery date/time or ask for redelivery; "
                    "address = change the delivery address/location; "
                    "multiple = clearly asks for both; other = a shipment request we do not support "
                    "(tracking status, refunds, complaints...); greeting = only a greeting; "
                    "none = no request (e.g. an answer to a question like a yes/no, a number or an address)."
                ),
            },
            "answer": {"type": ["string", "null"], "enum": ["yes", "no", None],
                       "description": "If the message answers a yes/no question (e.g. 'do you have your tracking number?')."},
            "tracking_number": {"type": ["string", "null"], "description": "Exactly as written, format like EX400238AE."},
            "phone": {"type": ["string", "null"], "description": "UAE mobile exactly as written."},
            "delivery_date": {"type": ["string", "null"], "description": "Requested NEW delivery date as YYYY-MM-DD, resolved relative to today. null if none or ambiguous."},
            "address": {"type": ["string", "null"], "description": "The NEW delivery address, copied verbatim from the message. null if none."},
        },
        "required": ["language", "intent", "answer", "tracking_number", "phone", "delivery_date", "address"],
    },
}

_SYSTEM = (
    "You are the language-understanding component of a UAE postal shipment assistant. "
    "Customers write in English or Arabic (MSA, Gulf or Egyptian dialect, sometimes mixed). "
    "You never answer the customer and never decide whether an action is allowed; you only "
    "classify the message and extract values by calling record_understanding. "
    "Never invent a tracking number, phone or address that is not in the message. "
    "Today is {today} ({weekday}). The conversation is currently in state: {state}."
)


def _llm_enabled() -> bool:
    mode = os.environ.get("FDE_INTENT_LLM", "auto").strip().lower()
    return mode != "off" and bool(os.environ.get("ANTHROPIC_API_KEY"))


# Tests inject an httpx.MockTransport here.
_transport: httpx.BaseTransport | None = None


def llm_understand(message: str, state: str | None, today: date) -> dict:
    base = os.environ.get("FDE_ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    timeout = float(os.environ.get("FDE_INTENT_TIMEOUT", "8"))
    payload = {
        "model": os.environ.get("FDE_INTENT_MODEL", "claude-haiku-4-5"),
        "max_tokens": 400,
        "temperature": 0,
        "system": _SYSTEM.format(today=today.isoformat(), weekday=today.strftime("%A"), state=state or "WELCOME"),
        "tools": [_TOOL],
        "tool_choice": {"type": "tool", "name": "record_understanding"},
        "messages": [{"role": "user", "content": str(message)[:2000]}],
    }
    headers = {
        "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    with httpx.Client(timeout=timeout, transport=_transport) as client:
        response = client.post(f"{base}/v1/messages", headers=headers, content=json.dumps(payload))
    response.raise_for_status()
    for block in response.json().get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "record_understanding":
            return block.get("input") or {}
    raise ValueError("LLM did not return a tool call")


def _grounded(value, message: str, normalizer=lambda s: s):
    if not value or not isinstance(value, str):
        return False
    return normalizer(value.strip()) in normalizer(message)


def _validate_llm(raw: dict, message: str, state: str | None, today: date, rules: dict) -> dict:
    from backend.shipment_service import is_valid_delivery_address

    intent = raw.get("intent")
    if intent not in INTENTS:
        raise ValueError(f"invalid intent {intent!r}")

    answer = raw.get("answer") if raw.get("answer") in ("yes", "no") else None

    squash = lambda s: re.sub(r"[\s\-]", "", normalize_digits(s)).upper()  # noqa: E731

    tracking = raw.get("tracking_number")
    tracking = tracking.strip().upper() if _grounded(tracking, message, squash) and TRACKING_RE.fullmatch(tracking.strip()) else None

    phone = raw.get("phone")
    phone = extract_phone(phone) if _grounded(phone, message, squash) else None

    address = raw.get("address")
    address = address.strip() if _grounded(address, message, _norm_ar) and is_plausible_address(address) else None

    delivery_date = raw.get("delivery_date")
    try:
        parsed = date.fromisoformat(delivery_date) if delivery_date else None
    except (TypeError, ValueError):
        parsed = None
    # The deterministic resolver wins whenever it can resolve the date itself.
    delivery_date = rules["entities"]["delivery_date"] or (parsed.isoformat() if parsed else None)

    return {
        "intent": intent,
        "answer": answer if answer is not None else rules["answer"],
        "entities": {
            "tracking_number": tracking or rules["entities"]["tracking_number"],
            "phone": phone or rules["entities"]["phone"],
            "delivery_date": delivery_date,
            "address": address or rules["entities"]["address"],
        },
    }


# -------------------------------------------------
# Public entry point
# -------------------------------------------------

def understand(message: str, state: str | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    message = str(message or "")[:2000]
    rules = rules_understand(message, state, today)

    result = None
    source = "rules"
    llm_error = None

    if _llm_enabled():
        try:
            result = _validate_llm(llm_understand(message, state, today), message, state, today, rules)
            source = "llm"
        except Exception as error:  # noqa: BLE001 — any LLM failure falls back safely
            llm_error = type(error).__name__

    if result is None:
        result = rules

    response = {
        "language": detect_language(message),
        "intent": result["intent"],
        "answer": result["answer"],
        "entities": result["entities"],
        "source": source,
    }
    if llm_error:
        response["llm_fallback_reason"] = llm_error
    return response
