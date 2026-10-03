"""Message understanding: deterministic bilingual parser + LLM path (mocked)."""

import json
from datetime import date

import httpx
import pytest

from backend import intent_agent
from backend.intent_agent import understand

TODAY = date(2026, 10, 3)  # Saturday


@pytest.mark.parametrize(
    "message, intent, language",
    [
        ("I need to reschedule my delivery", "reschedule", "en"),
        ("I missed the courier, can you come back another day?", "reschedule", "en"),
        ("I want to update my delivery address", "address", "en"),
        ("I moved, please send it to my new place", "address", "en"),
        ("عايز أغير ميعاد التوصيل", "reschedule", "ar"),
        ("ممكن تأجيل الشحنة ليوم تاني؟", "reschedule", "ar"),
        ("مكنتش في البيت، ممكن يجي بكرة؟", "reschedule", "ar"),
        ("ما كنت موجود، ابغى اعادة التوصيل باجر", "reschedule", "ar"),
        ("أريد تغيير عنوان التوصيل", "address", "ar"),
        ("ابغى اغير العنوان", "address", "ar"),
        ("نقلت لشقة جديدة", "address", "ar"),
        ("وين شحنتي؟", "other", "ar"),
        ("where is my package?", "other", "en"),
        ("مرحبا", "greeting", "ar"),
        ("hello", "greeting", "en"),
        ("deliver it next Monday to my new address", "multiple", "en"),
    ],
)
def test_rules_intent_and_language(message, intent, language):
    result = understand(message, None, TODAY)
    assert result["intent"] == intent
    assert result["language"] == language
    assert result["source"] == "rules"


@pytest.mark.parametrize(
    "message, expected",
    [
        ("tomorrow", "2026-10-04"),
        ("بكرة", "2026-10-04"),
        ("باجر", "2026-10-04"),
        ("بعد بكرة", "2026-10-05"),
        ("next Thursday", "2026-10-08"),
        ("يوم الخميس", "2026-10-08"),
        ("2026-10-12", "2026-10-12"),
        ("15/10/2026", "2026-10-15"),
        ("١٥/١٠/٢٠٢٦", "2026-10-15"),
        ("12 October", "2026-10-12"),
        ("in 3 days", "2026-10-06"),
        ("ما في احد في البيت", None),  # "احد" = someone, not Sunday
        ("31/02/2026", None),  # impossible date is never guessed
    ],
)
def test_date_resolution(message, expected):
    assert understand(message, "WAITING_FOR_RESCHEDULE_DATE", TODAY)["entities"]["delivery_date"] == expected


def test_entities_tracking_phone_address():
    r = understand("رقم الشحنة EX٤٠٠٢٣٨AE ورقمي 050 123 4567", None, TODAY)
    assert r["entities"]["tracking_number"] == "EX400238AE"
    assert r["entities"]["phone"] == "+971501234567"

    r = understand("Please change the address to Villa 12, Al Wasl Road, Dubai", None, TODAY)
    assert r["entities"]["address"] == "Villa 12, Al Wasl Road, Dubai"

    r = understand("غير العنوان لـ برج 7، شقة 1203، الخان، الشارقة", None, TODAY)
    assert r["entities"]["address"] == "برج 7، شقة 1203، الخان، الشارقة"

    r = understand("لو سمحت غير عنوان التوصيل إلى برج 7، شقة 1203، الخان، الشارقة", None, TODAY)
    assert r["entities"]["address"] == "برج 7، شقة 1203، الخان، الشارقة"

    # "للشحنة" is "for the shipment", not "to <address>" (regression).
    r = understand("عايز أغير عنوان التوصيل للشحنة EX401159AE", None, TODAY)
    assert r["intent"] == "address" and r["entities"]["tracking_number"] == "EX401159AE"
    assert r["entities"]["address"] is None
    assert understand("change the delivery address of EX401159AE to my place", None, TODAY)["entities"]["address"] is None

    # Vague text is not treated as an address.
    assert understand("change address to my office please", None, TODAY)["entities"]["address"] is None


@pytest.mark.parametrize(
    "message, answer",
    [("yes", "yes"), ("ايوه معايا", "yes"), ("نعم", "yes"), ("no", "no"),
     ("لا", "no"), ("لا معرفش", "no"), ("I don't know it", "no"), ("مش فاكر", "no")],
)
def test_yes_no(message, answer):
    assert understand(message, "WAITING_FOR_TRACKING_CHOICE", TODAY)["answer"] == answer


# -------------------------------------------------
# LLM path with a mocked Anthropic API
# -------------------------------------------------

def _mock_llm(monkeypatch, tool_input=None, status=200, capture=None):
    def handler(request):
        if capture is not None:
            capture.append(json.loads(request.content))
        if status != 200:
            return httpx.Response(status, json={"error": {"type": "overloaded_error"}})
        return httpx.Response(200, json={"content": [
            {"type": "tool_use", "name": "record_understanding", "input": tool_input}
        ]})

    monkeypatch.setenv("FDE_INTENT_LLM", "auto")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(intent_agent, "_transport", httpx.MockTransport(handler))


def test_llm_understands_free_form_and_is_used(monkeypatch):
    sent = []
    _mock_llm(monkeypatch, {
        "language": "ar", "intent": "reschedule", "answer": None,
        "tracking_number": "EX400238AE", "phone": None,
        "delivery_date": "2026-10-09", "address": None,
    }, capture=sent)
    r = understand("الشحنة EX400238AE ما وصلتني، خلوها توصل الجمعة الجاية لو سمحتوا", None, TODAY)
    assert r["source"] == "llm"
    assert r["intent"] == "reschedule"
    assert r["entities"]["tracking_number"] == "EX400238AE"
    # Rules can resolve "الجمعه" themselves -> deterministic date wins.
    assert r["entities"]["delivery_date"] == "2026-10-09"
    assert sent[0]["tool_choice"] == {"type": "tool", "name": "record_understanding"}
    assert "2026-10-03" in sent[0]["system"]


def test_llm_hallucinated_entities_are_discarded(monkeypatch):
    _mock_llm(monkeypatch, {
        "language": "en", "intent": "address", "answer": None,
        "tracking_number": "EX999999AE",  # not in message
        "phone": "+971509999999",          # not in message
        "delivery_date": None,
        "address": "Villa 1, Invented Street, Dubai",  # not in message
    })
    r = understand("I need my parcel to go somewhere else", None, TODAY)
    assert r["source"] == "llm"
    assert r["intent"] == "address"
    assert r["entities"] == {"tracking_number": None, "phone": None, "delivery_date": None, "address": None}


def test_llm_address_containing_tracking_number_is_rejected(monkeypatch):
    _mock_llm(monkeypatch, {
        "language": "ar", "intent": "address", "answer": None,
        "tracking_number": "EX401159AE", "phone": None, "delivery_date": None,
        "address": "لشحنة EX401159AE",
    })
    r = understand("عايز أغير عنوان التوصيل للشحنة EX401159AE", None, TODAY)
    assert r["source"] == "llm" and r["entities"]["address"] is None


def test_llm_invalid_output_falls_back_to_rules(monkeypatch):
    _mock_llm(monkeypatch, {"language": "en", "intent": "cancel_everything"})
    r = understand("I want to reschedule", None, TODAY)
    assert r["source"] == "rules"
    assert r["intent"] == "reschedule"
    assert r["llm_fallback_reason"] == "ValueError"


def test_llm_http_error_falls_back_to_rules(monkeypatch):
    _mock_llm(monkeypatch, status=529)
    r = understand("ابغى اغير العنوان", None, TODAY)
    assert r["source"] == "rules"
    assert r["intent"] == "address"
    assert r["llm_fallback_reason"] == "HTTPStatusError"


def test_llm_disabled_without_key(monkeypatch):
    monkeypatch.setenv("FDE_INTENT_LLM", "auto")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert understand("reschedule please", None, TODAY)["source"] == "rules"
