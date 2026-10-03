"""Live verification of the Claude understanding path (requires ANTHROPIC_API_KEY).

A scenario passes only if the REAL LLM answered (source == "llm"); a silent
fallback to the deterministic parser counts as a failure.

    export ANTHROPIC_API_KEY=sk-ant-...
    python scripts/verify_live_llm.py
"""

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("FDE_RUNTIME_DIR", tempfile.mkdtemp(prefix="fde-live-llm-"))
os.environ["FDE_INTENT_LLM"] = "auto"

from backend.intent_agent import understand  # noqa: E402

TODAY = date.today()
TOMORROW = (TODAY + timedelta(days=1)).isoformat()
DAY_AFTER = (TODAY + timedelta(days=2)).isoformat()

# (name, message, state, expected subset)
SCENARIOS = [
    ("EN reschedule + tracking + date",
     "Hi, I missed my delivery EX400238AE. Can you bring it tomorrow?", None,
     {"language": "en", "intent": "reschedule", "tracking_number": "EX400238AE", "delivery_date": TOMORROW}),
    ("EN reschedule, indirect phrasing",
     "Nobody was home when the courier came, could he try again another day?", None,
     {"language": "en", "intent": "reschedule"}),
    ("EN address + inline address",
     "Please change the address to Villa 12, Al Wasl Road, Jumeirah, Dubai", None,
     {"language": "en", "intent": "address", "address": "Villa 12, Al Wasl Road, Jumeirah, Dubai"}),
    ("AR (Egyptian) reschedule + date",
     "مكنتش في البيت لما المندوب جه، ممكن يجي بعد بكرة؟ رقم الشحنة EX400476AE", None,
     {"language": "ar", "intent": "reschedule", "tracking_number": "EX400476AE", "delivery_date": DAY_AFTER}),
    ("AR (Gulf) reschedule",
     "ابغى اغير موعد التوصيل باجر لو سمحت", None,
     {"language": "ar", "intent": "reschedule", "delivery_date": TOMORROW}),
    ("AR address + inline address",
     "لو سمحت غير عنوان التوصيل إلى برج 7، شقة 1203، الخان، الشارقة", None,
     {"language": "ar", "intent": "address", "address": "برج 7، شقة 1203، الخان، الشارقة"}),
    ("AR address, indirect (moved)",
     "نقلت لشقة جديدة وعايز الشحنة توصل هناك", None,
     {"language": "ar", "intent": "address"}),
    ("Mixed: both requests",
     "Can you deliver it next Monday and also send it to my new office?", None,
     {"intent": "multiple"}),
    ("Out of scope (tracking status)",
     "وين شحنتي؟ متى توصل؟", None,
     {"language": "ar", "intent": "other"}),
    ("Ambiguous, no request",
     "hmm I'm not sure", None,
     {"intent": "none"}),
    ("Yes answer (AR)", "ايوه معايا", "WAITING_FOR_TRACKING_CHOICE", {"answer": "yes"}),
    ("No answer (EN)", "no, I don't know it", "WAITING_FOR_TRACKING_CHOICE", {"answer": "no"}),
    ("Intent change in address step (EN)",
     "actually, I'd rather reschedule the delivery instead", "WAITING_FOR_NEW_ADDRESS",
     {"intent": "reschedule", "address": None}),
    ("Intent change in date step (AR)",
     "لا خلاص، عايز أغير العنوان بدل كده", "WAITING_FOR_RESCHEDULE_DATE",
     {"intent": "address", "delivery_date": None}),
    ("Address in address step (AR, Arabic digits)",
     "فيلا ١٢، شارع الوصل، جميرا، دبي", "WAITING_FOR_NEW_ADDRESS",
     {"address": "فيلا ١٢، شارع الوصل، جميرا، دبي"}),
    ("Hallucination guard: no tracking in text",
     "I want to reschedule my parcel", None,
     {"intent": "reschedule", "tracking_number": None, "address": None}),
]


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set: live LLM verification NOT run.")
        return 2

    failures = 0
    for name, message, state, expected in SCENARIOS:
        result = understand(message, state)
        flat = {"language": result["language"], "intent": result["intent"],
                "answer": result["answer"], **result["entities"]}
        problems = [f"{k}={flat.get(k)!r} (expected {v!r})" for k, v in expected.items() if flat.get(k) != v]
        if result["source"] != "llm":
            problems.insert(0, f"source={result['source']} ({result.get('llm_fallback_reason')})")
        status = "PASS" if not problems else "FAIL"
        failures += bool(problems)
        print(f"[{status}] {name}: {'; '.join(problems) if problems else flat}")

    print(f"\n{len(SCENARIOS) - failures}/{len(SCENARIOS)} live LLM scenarios passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
