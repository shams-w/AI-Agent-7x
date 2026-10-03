"""Browser end-to-end tests through the real React UI + FastAPI backend.

Starts its own backend (port 8765, throw-away runtime dir) and Vite dev
server (port 5199), so the demo files in outputs/ are never touched.

Run:  python -m pytest e2e -q
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8765"
WEB = "http://127.0.0.1:5199"
SHOTS = ROOT / "e2e" / "screenshots"
CLEANED = pd.read_excel(ROOT / "outputs" / "FDE_Assignment_Shipment_Dataset_AI_Cleaned.xlsx")

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def last4(tracking):
    phone = str(CLEANED[CLEANED.tracking_number == tracking].iloc[0]["phone"])
    phone = phone[:-2] if phone.endswith(".0") else phone
    return "".join(c for c in phone if c.isdigit())[-4:]


def api(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        API + path, data=data, method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def _wait(url, seconds=40):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.4)
    raise RuntimeError(f"{url} did not start")


def _fingerprint():
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "outputs").iterdir()) if p.is_file()
    }


@pytest.fixture(scope="session")
def servers():
    before = _fingerprint()
    runtime = tempfile.mkdtemp(prefix="fde-e2e-runtime-")
    env = {
        **os.environ,
        "FDE_RUNTIME_DIR": runtime,
        "FDE_CORS_ORIGINS": WEB,
        "FDE_INTENT_LLM": os.environ.get("FDE_INTENT_LLM", "off"),
        "VITE_API_BASE": API,
    }
    backend = subprocess.Popen(
        ["python3", "-m", "uvicorn", "backend.app:app", "--port", "8765"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, start_new_session=True,
    )
    frontend = subprocess.Popen(
        ["npx", "vite", "--port", "5199", "--strictPort", "--host", "127.0.0.1"],
        cwd=ROOT / "frontend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, start_new_session=True,
    )
    try:
        _wait(API + "/health")
        _wait(WEB)
        yield
    finally:
        for process in (frontend, backend):
            os.killpg(process.pid, signal.SIGTERM)
        shutil.rmtree(runtime, ignore_errors=True)
        assert _fingerprint() == before, "E2E run modified files in outputs/"


@pytest.fixture(scope="session")
def browser(servers):
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    api("/reset", {})
    context = browser.new_context(viewport={"width": 1400, "height": 1000})
    pg = context.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(WEB)
    expect(pg.get_by_test_id("conversation")).to_contain_text("shipment assistant")
    yield pg
    context.close()
    assert not errors, f"Browser errors: {errors}"


def send(page, text):
    box = page.get_by_test_id("chat-input")
    expect(box).to_be_enabled()
    box.fill(text)
    box.press("Enter")


def chat(page):
    return page.get_by_test_id("conversation")


def last_assistant(page):
    return page.get_by_test_id("assistant-msg").last


def shot(page, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


# -------------------------------------------------
# Successful flows
# -------------------------------------------------

def test_english_one_message_reschedule(page):
    send(page, "Hi, I missed my delivery EX400238AE. Can you bring it tomorrow?")
    expect(last_assistant(page)).to_contain_text("last 4 digits")
    expect(chat(page)).to_contain_text("I’ve noted")
    send(page, last4("EX400238AE"))

    card = page.get_by_test_id("confirmation-card")
    expect(card).to_contain_text("Confirm redelivery")
    expect(card).to_contain_text(TOMORROW)
    assert api("/shipment/EX400238AE")["shipment"]["status"] == "Failed Delivery"  # nothing yet

    page.get_by_test_id("confirm-btn").click()
    expect(chat(page)).to_contain_text("Delivery rescheduled")
    expect(chat(page)).to_contain_text(f"now scheduled for")
    expect(page.get_by_test_id("panel-redelivery")).to_have_text(TOMORROW)
    shot(page, "en_reschedule_success")

    after = api("/shipment/EX400238AE")["shipment"]
    assert after["status"] == "Scheduled for Redelivery"
    assert str(after["scheduled_redelivery_date"])[:10] == TOMORROW


def test_arabic_address_update_step_by_step(page):
    tracking = "EX401159AE"
    send(page, "السلام عليكم، عايز أغير عنوان التوصيل")
    expect(last_assistant(page)).to_have_text("هل رقم التتبع معاك؟")
    send(page, "أيوه معايا")
    expect(last_assistant(page)).to_contain_text("اكتب رقم التتبع")
    send(page, tracking)
    expect(last_assistant(page)).to_contain_text("آخر 4 أرقام")
    send(page, last4(tracking))
    expect(last_assistant(page)).to_contain_text("عنوان التوصيل الجديد")

    new_address = "فيلا 12، شارع الوصل، جميرا، دبي"
    send(page, new_address)
    card = page.get_by_test_id("confirmation-card")
    expect(card).to_contain_text("تأكيد تغيير العنوان")
    expect(card).to_contain_text(new_address)
    page.get_by_test_id("confirm-btn").click()

    expect(chat(page)).to_contain_text("تم تحديث عنوان التوصيل")
    expect(page.get_by_test_id("panel-address")).to_have_text(new_address)
    shot(page, "ar_address_success")
    assert api(f"/shipment/{tracking}")["shipment"]["delivery_address"] == new_address


def test_arabic_missing_phone_then_natural_date(page):
    tracking = "EX400380AE"  # raw status "Undelivered", phone missing
    send(page, f"مكنتش موجود لما المندوب جه، رقم الشحنة {tracking}")
    expect(chat(page)).to_contain_text("مطلوب رقم موبايل")
    send(page, "٠٥٠٧٦٥٤٣٢١")  # Arabic-Indic digits
    expect(chat(page)).to_contain_text("تم قبول رقم التواصل")
    expect(last_assistant(page)).to_contain_text("إمتى")
    send(page, "بكرة لو سمحت")
    card = page.get_by_test_id("confirmation-card")
    expect(card).to_contain_text("تأكيد إعادة التوصيل")
    expect(card).to_contain_text(TOMORROW)
    page.get_by_test_id("confirm-btn").click()
    expect(chat(page)).to_contain_text("تم تغيير موعد التوصيل")
    shot(page, "ar_missing_phone_reschedule")
    after = api(f"/shipment/{tracking}")["shipment"]
    assert after["status"] == "Scheduled for Redelivery"
    assert str(after["scheduled_redelivery_date"])[:10] == TOMORROW


def test_english_find_by_phone_then_switch_intent(page):
    tracking = "EX400476AE"
    send(page, "I need to change my delivery address")
    expect(last_assistant(page)).to_contain_text("tracking number")
    send(page, "no, I don't know it")
    expect(last_assistant(page)).to_contain_text("mobile number")
    phone = str(int(CLEANED[CLEANED.tracking_number == tracking].iloc[0]["phone"]))
    send(page, phone)
    expect(chat(page)).to_contain_text("Shipment located")
    send(page, last4(tracking))
    expect(last_assistant(page)).to_contain_text("new delivery address")
    # Customer changes their mind mid-flow.
    send(page, "actually, I'd rather reschedule the delivery instead")
    expect(last_assistant(page)).to_contain_text("What date")
    send(page, "next Thursday")
    expect(page.get_by_test_id("confirmation-card")).to_contain_text("Confirm redelivery")
    page.get_by_test_id("confirm-btn").click()
    expect(chat(page)).to_contain_text("Delivery rescheduled")
    assert api(f"/shipment/{tracking}")["shipment"]["status"] == "Scheduled for Redelivery"


# -------------------------------------------------
# Blocked / guarded flows
# -------------------------------------------------

def test_arabic_blocked_delivered_shipment(page):
    tracking = "EX400319AE"
    before = api(f"/shipment/{tracking}")["shipment"]
    send(page, f"ابغى اغير موعد التوصيل للشحنة {tracking}")
    expect(chat(page)).to_contain_text("الشحنة اتسلّمت بالفعل")
    expect(last_assistant(page)).to_contain_text("غير مسموح")
    expect(chat(page)).not_to_contain_text("آخر 4 أرقام")  # never asks to verify
    expect(chat(page)).not_to_contain_text("تم تغيير موعد التوصيل")
    expect(page.get_by_test_id("confirmation-card")).to_have_count(0)
    shot(page, "ar_blocked_delivered")
    assert api(f"/shipment/{tracking}")["shipment"] == before


def test_english_invalid_verification_locks_without_change(page):
    tracking = "EX400238AE"
    before = api(f"/shipment/{tracking}")["shipment"]
    wrong = "0000" if last4(tracking) != "0000" else "1111"
    send(page, f"please reschedule {tracking}")
    expect(last_assistant(page)).to_contain_text("last 4 digits")
    send(page, wrong)
    expect(last_assistant(page)).to_contain_text("4 attempt(s) left")
    for _ in range(4):
        send(page, wrong)
    expect(chat(page)).to_contain_text("Verification locked")
    expect(chat(page)).to_contain_text("Support handoff prepared")
    expect(page.get_by_test_id("confirmation-card")).to_have_count(0)
    expect(chat(page)).not_to_contain_text("Delivery rescheduled")
    assert api(f"/shipment/{tracking}")["shipment"] == before


def test_cancel_confirmation_changes_nothing(page):
    tracking = "EX400093AE"
    before = api(f"/shipment/{tracking}")["shipment"]
    send(page, f"Can you deliver {tracking} on a different day? Tomorrow works.")
    send(page, last4(tracking))
    expect(page.get_by_test_id("confirmation-card")).to_be_visible()
    page.get_by_test_id("cancel-btn").click()
    expect(chat(page)).to_contain_text("No shipment data was changed")
    assert api(f"/shipment/{tracking}")["shipment"] == before


def test_test_record_is_blocked(page):
    send(page, "I want to reschedule my delivery")
    send(page, "yes")
    send(page, "TEST1001")
    expect(chat(page)).to_contain_text("Test record blocked")
    expect(chat(page)).to_contain_text("Support handoff prepared")


def test_out_of_scope_and_greeting_in_arabic(page):
    send(page, "وين شحنتي؟")
    expect(last_assistant(page)).to_contain_text("حالياً أقدر أساعد فقط")
    send(page, "تمام، ابغى اغير العنوان")
    expect(last_assistant(page)).to_have_text("هل رقم التتبع معاك؟")


def test_new_request_after_success_in_same_chat(page):
    send(page, "Hi, I missed my delivery EX400238AE. Can you bring it tomorrow?")
    send(page, last4("EX400238AE"))
    page.get_by_test_id("confirm-btn").click()
    expect(chat(page)).to_contain_text("Delivery rescheduled")
    send(page, "also please change the address of EX401159AE")
    expect(last_assistant(page)).to_contain_text("last 4 digits")


def test_no_false_success_when_record_does_not_show_change(page):
    """If the backend's re-read record does not show the change, the UI must not claim success."""
    tracking = "EX400238AE"
    stale = api(f"/shipment/{tracking}")  # pre-change record
    send(page, f"Hi, I missed my delivery {tracking}. Can you bring it tomorrow?")
    send(page, last4(tracking))
    expect(page.get_by_test_id("confirmation-card")).to_be_visible()

    # From now on, serve the stale (pre-change) record to the UI.
    page.route(f"**/shipment/{tracking}", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(stale)))
    page.get_by_test_id("confirm-btn").click()

    expect(chat(page)).to_contain_text("Change not confirmed")
    expect(chat(page)).not_to_contain_text("Delivery rescheduled")


def test_unconfirmed_change_is_never_executed_from_ui(page):
    tracking = "EX400093AE"
    before = api(f"/shipment/{tracking}")["shipment"]
    send(page, f"please reschedule {tracking} to tomorrow")
    send(page, last4(tracking))
    expect(page.get_by_test_id("confirmation-card")).to_be_visible()
    # Customer walks away without confirming: nothing may change.
    page.wait_for_timeout(1500)
    assert api(f"/shipment/{tracking}")["shipment"] == before


def test_arabic_address_with_tracking_in_first_message(page):
    """Regression: 'للشحنة' must not be read as 'to <address>'."""
    tracking = "EX401159AE"
    send(page, f"عايز أغير عنوان التوصيل للشحنة {tracking}")
    send(page, last4(tracking))
    expect(last_assistant(page)).to_contain_text("عنوان التوصيل الجديد")
    expect(page.get_by_test_id("confirmation-card")).to_have_count(0)


def test_invalid_uae_mobile_cannot_continue_then_valid_one_can(page):
    tracking = "EX401556AE"  # no phone on file
    send(page, f"reschedule my delivery {tracking}")
    expect(chat(page)).to_contain_text("Mobile number required")
    for bad in ["+966501234567", "0421234567", "05012abc67"]:
        send(page, bad)
        expect(chat(page)).to_contain_text("not a valid UAE mobile")
        expect(page.get_by_test_id("chat-input")).to_have_attribute("placeholder", "Enter a UAE mobile number...")
    assert api(f"/shipment/{tracking}")["shipment"]["phone"] is None  # nothing stored
    expect(chat(page)).not_to_contain_text("Contact number accepted")
    send(page, "050-765-4321")
    expect(chat(page)).to_contain_text("Contact number accepted")
    expect(last_assistant(page)).to_contain_text("What date")
    assert api(f"/shipment/{tracking}")["shipment"]["phone"].endswith("4321")


def test_placeholder_new_address_is_rejected_in_ui(page):
    tracking = "EX401159AE"
    before = api(f"/shipment/{tracking}")["shipment"]
    send(page, f"I want to change the delivery address for {tracking}")
    send(page, last4(tracking))
    expect(last_assistant(page)).to_contain_text("new delivery address")
    send(page, "  Same As Before  ")
    expect(chat(page)).to_contain_text("Address needs more detail")
    expect(page.get_by_test_id("confirmation-card")).to_have_count(0)
    assert api(f"/shipment/{tracking}")["shipment"] == before


def test_invalid_weight_review_is_simulated_and_resumes_only_after_resolution(page):
    tracking = "EX400402AE"  # In Transit, weight 0
    send(page, f"please reschedule {tracking}")
    expect(chat(page)).to_contain_text("Shipment review in progress")
    expect(chat(page)).to_contain_text("internal operational review is simulated")
    expect(chat(page)).to_contain_text("does not invent or correct the source operational value")
    expect(chat(page)).not_to_contain_text("last 4 digits")
    # Demo review auto-resolves after ~8s; the UI polls, re-reads, then continues.
    expect(chat(page)).to_contain_text("Shipment review completed", timeout=20000)
    expect(last_assistant(page)).to_contain_text("last 4 digits", timeout=10000)
    assert float(api(f"/shipment/{tracking}")["shipment"]["weight_kg"]) == 0.0  # not guessed or changed
