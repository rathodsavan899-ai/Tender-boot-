# TenderBot AI — Agentic Tender Hunter, Bid Predictor & Tax Assistant

मराठी भाषेतील AI "डिजिटल मॅनेजर" for Maharashtra contractors: tender discovery, eligibility gap analysis,
L1 bid-rate prediction, EMD/BG kits, vendor marketplace, document vault, payment-delay notices, GST advice,
and WhatsApp + Marathi voice approval before any submission.

Stack: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, LangChain + OpenAI GPT-4o, Twilio (WhatsApp + Voice).

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in keys
uvicorn main:app --reload
```
Open http://localhost:8000/docs. Twilio webhooks need a public URL (e.g. ngrok) set as `PUBLIC_BASE_URL`:
- WhatsApp inbound webhook → `POST {PUBLIC_BASE_URL}/whatsapp-webhook`
- Voice calls are initiated by the API; Twilio fetches `/voice-prompt/{id}` and `/voice-response/{id}`.

Without `OPENAI_API_KEY` / Twilio credentials the app still runs: messages return as **dry runs** (not sent),
and features that need GPT-4o (extracting requirements from raw `tender_text`) return a clear error.

Regenerate the whole repo as a zip: `python build_zip.py` → `tenderbot-ai-production.zip`.

## Business rules (enforced in `database.check_access`)
| Status | Access |
|---|---|
| Trial (day 1–15) | everything |
| Basic ₹999 | analysis, alerts, document vault, draft + exportable GST billing |
| VIP ₹5,000 | all 6 features |
| Day 16+, no plan | locked: submission, competitor AI, voice calls, GST export, all VIP features, alerts. Returns HTTP 402 with the Marathi paywall message. Analysis and draft GST preview stay open. |

## Data-sourcing rules (no hallucination)
- **Competitor AI** uses only public awarded-tender results (Mahatenders / CPPP) stored in `awarded_tenders`.
  Fewer than `MIN_HISTORY_SAMPLES` matches → response is exactly "जुना डेटा उपलब्ध नाही".
  Percentages are relative to the estimated cost (SSR-based); negative = below.
- **Marketplace** returns contacts/rates only from the Internal Verified Vendor Database (`verified_vendors`).
- Submission is reported as `SUBMITTED` only if your `SUBMISSION_WEBHOOK_URL` service confirms with 2xx.
  Portal submission needs your DSC, so by default an approved bid is `APPROVED_AWAITING_PORTAL_SUBMISSION`.

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | health check |
| POST | `/analyze-tender` | document gap analysis + WhatsApp alert |
| POST | `/predict-bid-rate` | competitor AI → L1 %, bid amount, profit margin |
| POST | `/request-submit-approval` | WhatsApp prompt + Marathi voice call |
| POST | `/whatsapp-webhook` | YES/NO (also हो/नाही) → execute or cancel |
| POST | `/generate-payment-notice` | formal Marathi follow-up letter |
| POST | `/get-tax-advice` | GST liability, ITC, CA-ready breakdown |
| POST | `/generate-emd-kit` | EMD / BG document kit |
| GET | `/marketplace/search` | verified vendors |
| POST/GET | `/vault/documents` | document vault |
| POST | `/discover-tenders` | read a public listing page (allow-listed hosts) |
| POST | `/admin/*` (header `X-Admin-Key`) | ingest awarded data, add vendors, set plan, run vault alerts |

Feed the competitor AI first: `POST /admin/ingest-awarded-data` with `{"source":"Mahatenders","url":"..."}`
or `{"source":"CPPP","records":[{...}]}`. The scraper reads only public HTML tables; it does not bypass captchas/logins.

## Example
```bash
curl -X POST localhost:8000/get-tax-advice -H 'content-type: application/json' -d '{
  "phone":"+919876543210","taxable_value":1000000,
  "purchases":[{"description":"Cement","taxable_value":400000,"gst_rate_percent":18,"itc_eligible":true}]}'
```

GST figures are computed from your inputs; confirm with your CA before filing.
