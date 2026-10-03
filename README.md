# 7X FDE AI Shipment Agent

A customer-facing shipment assistant (MVP) that handles two operational requests in **English and Arabic**:

1. **Reschedule a delivery**
2. **Update a delivery address**

An LLM understands what the customer means. **Everything that decides or changes data is deterministic**: business rules, identity verification, explicit confirmation, execution, and the audit log.

```
customer message (EN / AR)
   │
   ▼
/agent/understand ── LLM (Claude, forced tool schema) ──┐   intent, language, yes/no,
   │                 deterministic bilingual parser ◄───┘   tracking #, phone, date, address
   │                 (fallback + validator; entities must appear in the customer's text)
   ▼
/shipment  ──► data-quality guardrails (test records, duplicates, bad dates/weight...)
   ▼
/eligibility ──► business_rules.py (status allow-list; never an LLM decision)
   ▼
/verify (last 4 digits, 5 attempts then lock)  or  /collect-phone (only if no phone on file)
   ▼
confirmation card (customer must click "Confirm")
   ▼
/reschedule | /update-address  ──► runtime dataset + audit log
   ▼
re-read /shipment ──► final answer states only what the record now shows
```

## Project layout

```
backend/
  app.py              FastAPI endpoints, verification tokens, attempt lockout
  intent_agent.py     message understanding: LLM + deterministic EN/AR parser
  business_rules.py   ALLOW / BLOCK / ASK decisions
  shipment_service.py lookup, eligibility, data-quality classification, repairs
  actions.py          verification + the two write actions + audit log
  data_agent.py       cleans the raw Excel file -> outputs/..._AI_Cleaned.xlsx
  config.py           file locations (FDE_RUNTIME_DIR isolates tests)
frontend/             React + Vite chat UI (src/i18n.js holds all EN/AR text)
data/                 raw source dataset (never modified)
outputs/              cleaned dataset, runtime copy, audit log
tests/                backend unit + API end-to-end tests
e2e/                  browser end-to-end tests (Playwright, real UI + API)
```

## Run it

Backend (Python 3.11+):

```bash
pip install -r requirements.txt
python -m backend.data_agent          # only if you change data/…xlsx
uvicorn backend.app:app --reload --port 8000
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev                            # http://localhost:5173
```

### Turning on the LLM

Without an API key the assistant uses the deterministic bilingual parser (it already handles common English, MSA, Gulf and Egyptian phrasing). To use Claude for understanding:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export FDE_INTENT_MODEL=claude-haiku-4-5   # optional (default)
```

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | – | enables the LLM path |
| `FDE_INTENT_LLM` | `auto` | `off` forces the deterministic parser |
| `FDE_INTENT_MODEL` | `claude-haiku-4-5` | model used for understanding |
| `FDE_INTENT_TIMEOUT` | `8` | seconds before falling back to the parser |
| `FDE_RUNTIME_DIR` | `outputs/` | where the runtime copy + audit log are written |
| `FDE_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | allowed UI origins |
| `VITE_API_BASE` (frontend) | `http://127.0.0.1:8000` | backend URL |

Verify the live LLM path (16 English/Arabic scenarios; a fallback to rules counts as a failure):

```bash
ANTHROPIC_API_KEY=sk-ant-... python scripts/verify_live_llm.py
```

How the LLM is kept safe:
- It is called with a forced tool (`record_understanding`) and a strict schema. Free text is never used.
- Tracking numbers, phones and addresses it returns are **discarded unless they literally appear in the customer's message**. Dates must be real calendar dates; the deterministic resolver wins whenever it can resolve the date itself.
- Any error, timeout or invalid output falls back to the deterministic parser (`source: "rules"` in the response).
- It never sees verification digits, and it never writes customer-facing text. All replies are templated in `frontend/src/i18n.js`, so the assistant cannot claim something that did not happen.

## Demo script

Click **Reset Demo** first. You can type in English or Arabic, and the assistant replies in the customer's language. The **English / العربية** button switches the interface language.

| Scenario | Try typing | Verify with |
|---|---|---|
| One-message reschedule | `Hi, I missed my delivery EX400238AE. Can you bring it tomorrow?` | `5467` |
| Arabic address change | `عايز أغير عنوان التوصيل` → `أيوه` → `EX401159AE` → address | `5205` |
| Arabic natural date | `مكنتش في البيت، رقم الشحنة EX400476AE` → `بعد بكرة` | `1224` |
| Missing phone (raw status was "Undelivered") | `مكنتش موجود، رقم الشحنة EX400380AE` → a UAE mobile | – |
| Missing address before reschedule | `reschedule EX400489AE` | `3065` |
| Blocked: delivered | `ابغى اغير موعد التوصيل للشحنة EX400319AE` | – |
| Blocked: out for delivery / returned | `EX401166AE` / `EX401452AE` | – |
| Internal review (invalid weight) | `reschedule EX400402AE` | – |
| Test record | `reschedule` → `yes` → `TEST1001` | – |
| Find by phone | `I need to change my address` → `no` → registered mobile | – |
| Change of mind | in the address step: `actually I'd rather reschedule` | – |

## Data quality (Data Agent)

`python -m backend.data_agent` turns `data/FDE_Assignment_Shipment_Dataset.xlsx` into `outputs/FDE_Assignment_Shipment_Dataset_AI_Cleaned.xlsx`. Only status values are normalized. Customer fields (name, phone, address, weight, COD, dates) are never invented or rewritten.

| Raw status | Rows | Handling |
|---|---|---|
| `Undelivered` | 3 | → `Failed Delivery` **only because each row has `delivery_attempts ≥ 1`** (reason recorded in `AI_Notes`). With 0 attempts it would stay as-is and be flagged as an unrecognized status. |
| `RTS`, `Return to sender` | 2 + 1 | → `Returned to Sender` |
| `in-transit` | 3 | → `In Transit` |
| `TEST` | 6 | kept as-is. Flagged as a test record and blocked from every customer action. |
| `TEST1002`, `TEST1004` (status `Delivered`) | 2 | also flagged as test records (by tracking prefix) |
| anything else unknown | – | flagged `Unrecognized shipment status` → `UNKNOWN_STATUS` → escalated |

Test records are also excluded from find-by-phone results.

## Security controls

- Server-issued verification token: 10-minute TTL, bound to one shipment, single-use after a successful change.
- Last-4 verification: **5 failed attempts lock the shipment for 15 minutes**.
- `/collect-phone` works **only when the shipment has no usable phone**. It can no longer overwrite a registered phone to obtain a token.
- `/repair-address` works **only as a reschedule prerequisite** (eligible shipment with no usable address). It cannot be used to change an address while bypassing the status rules or confirmation.
- Address eligibility uses a status **allow-list**, so an unknown status is never eligible.
- Phones are masked in API responses. Internal notes are never returned.
- Every verification and action is written to the audit log (JSONL).

## Tests

```bash
python -m pytest tests -q        # backend: unit + API end-to-end (no network, no LLM)
python -m pytest e2e -q          # browser E2E: starts its own backend (:8765) + Vite (:5199)
python -m pytest -q              # both
```

- All test writes go to a temporary `FDE_RUNTIME_DIR`. Both suites **fail if any file in `outputs/` changes**.
- The LLM path is tested with a mocked Anthropic API: tool-call parsing, hallucinated entities rejected, fallback on invalid output and HTTP errors.
- Browser E2E covers English and Arabic, success, blocked, missing phone, invalid verification and lockout, cancel, test record, change of intent, and a second request in the same chat. After each success it checks the backend record actually changed.

## Validation rules (deterministic, `backend/validators.py`)

- **Customer-entered mobile:** must be a UAE mobile on 050/052/054/055/056/058, written as `05XXXXXXXX`, `9715XXXXXXXX` or `+9715XXXXXXXX`. Spaces and hyphens are allowed; letters, landlines, foreign numbers, wrong lengths and dummy numbers are rejected. The number is stored as `+9715XXXXXXXX`; an invalid number is never stored.
- **Registered mobile on file:** normalized the same way before comparing (`0501234567` = `971501234567` = `+971501234567`). Numbers on other UAE 5X prefixes (e.g. 053) stay usable for last-4 verification.
- **Address:** must be ≥ 10 characters and not a placeholder (`same as before`, `asdf`, `call me`, `-`, `.` …). The check ignores case and surrounding spaces.
- **Dates (Data Agent):**
  - ISO, unambiguous `DD/MM/YYYY`, `D Mon YYYY` (`22 Aug 2026`) and integer Excel serials (2000–2099) are accepted. The last two are converted to ISO, and each conversion is recorded in `AI_Notes`.
  - Ambiguous (`07/06/2026`) and impossible (`31/02/2026`) dates are escalated, never replaced.
- **Internal review:** simulated for the MVP. The AI does not invent or correct the source operational value.

## Data audit

See [`DATA_AUDIT.md`](DATA_AUDIT.md). Re-run with `python audit/run_data_audit.py` (read-only; writes only to `audit/`).

## Known limitations (MVP)

- Verification tokens and attempt counters are in memory, so they reset when the backend restarts. Production would use a shared store plus OTP or account authentication.
- `/collect-phone` is format validation only, not proof of ownership. Production needs OTP.
- The runtime "database" is an Excel file. Concurrent writers are not safe.
- The internal review auto-resolves after 8 seconds (demo behaviour).
- Reschedule dates have no upper bound (no maximum booking horizon is defined in the rules).
