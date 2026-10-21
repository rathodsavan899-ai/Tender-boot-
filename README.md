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

## मोबाइल ॲप (PWA)
Open `{PUBLIC_BASE_URL}/app` in Chrome on your phone → menu ⋮ → **Add to Home screen / Install app**.
Screens: टेंडर शोध · बिड रेट · सबमिशन मंजुरी · डॉक्युमेंट व्हॉल्ट · GST सल्ला · प्रोफाइल.
APK: paste the `/app` URL into pwabuilder.com → Package for stores → Android. Then set `ANDROID_PACKAGE_NAME` and `ANDROID_SHA256_FINGERPRINTS` (shown by PWABuilder) so the app opens without the browser bar; `/.well-known/assetlinks.json` is served automatically.
Login: SMS OTP. Set `FAST2SMS_API_KEY` to use our own OTP system (hashed codes, 5-minute expiry, 5 attempts, +91 only) or `TWILIO_VERIFY_SERVICE_SID` for Twilio Verify. Uploaded documents are AES-encrypted (Fernet) in the database; Aadhaar numbers are never stored.
Required env vars on the host: `TWILIO_VERIFY_SERVICE_SID`, `FILE_ENCRYPTION_SECRET` (never change/lose it), `OPENAI_API_KEY` (AI chat),
and a persistent PostgreSQL `DATABASE_URL` (SQLite on free hosts is wiped on redeploy, which would delete users, sessions and files).

## Tender Hunter (assistant 1)
Reads public tender listing pages on a schedule and saves new tenders (search screen shows them).
1. `POST /admin/test-source {"url": "...{page}..."}` — shows what would be extracted (nothing saved).
2. `POST /admin/tender-sources` — add the source (optional `backup_url`, `state_filter`, `keywords`, `max_pages`).
3. `GET /admin/tender-sources` — status per source (ok / down, last error, new tenders found).
4. `POST /admin/run-hunter` — start a crawl now. A free cron service (e.g. cron-job.org) can call it every 6 hours with the
   `X-Admin-Key` header; that also wakes a sleeping free Render instance, so the crawl keeps running.
A default CPPP Maharashtra civil source is added automatically on first start. Alerts go to Telegram (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) or WhatsApp (`ADMIN_WHATSAPP`); test with `POST /admin/notify-test`. `GET /admin/telegram-chats` finds your chat id after you message the bot; `GET /admin/health` shows totals; `PATCH /admin/tender-sources/{id}` edits a source (backup_url, keywords…).
Example CPPP source: `https://eprocure.gov.in/cppp/latestactivetendersnew/mmpdata?page={page}` with `state_filter=Maharashtra`.
Pages that need a captcha or login cannot be read. Add more hosts with `ALLOWED_SCRAPE_HOSTS`.

## Content assistant (daily posters)
Every day after `CONTENT_HOUR_IST` (08:00 IST) it makes a Marathi poster (1080x1350), a caption and a 30-second video script and
sends them to your Telegram. Topics are limited to features that really exist; "tender of the day" uses only tenders found in
the last 24 hours. If `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_TOKEN` and `INSTAGRAM_BUSINESS_ID` are set, it also posts to the Page and
Instagram (one post a day). `POST /admin/content/run?force=true` makes one now, `GET /admin/content/latest` shows the last 7.
Posters use a sunset construction-site look; with `CONTENT_AI_BACKGROUND=true` an AI picture (no text in it) is used as background. After setting the bot token run `POST /admin/telegram-webhook` once: then typing `/poster` or `/status` to your bot works.
A ~20-second vertical video (720x1280) is made the same way and sent to Telegram; with the Meta settings it is posted as an Instagram Reel / Facebook video. Voice-over needs `GOOGLE_TTS_API_KEY`; without it the video is silent. Rendering uses ffmpeg (bundled via `imageio-ffmpeg`).
## Orchestrator (chief manager)
`orchestrator_agent` checks every agent, acts as the fail-safe co-pilot and sends a nightly report (21:00 IST) to Telegram
(`GET /admin/report`, or `/status` in Telegram). Backups: stale tender crawl is re-run (and the backup URL is used); a missing
daily post is re-made without the video; a stuck post is re-sent; each problem alerts the owner once a day.
An honesty guard blocks social posting if the caption has banned claims (guarantees, win rates, store badges, "first in India").
It never changes the database schema or keys, and portal submission with the DSC always waits for the owner.
YouTube is not automated: API uploads stay private until Google audits the project.

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
| POST | `/discover-tenders` | read a public listing page (allow-listed hosts) and save tenders |
| GET/POST | `/tenders/search`, `/tenders` | search / add tenders |
| GET/POST | `/me` | profile + plan status |
| GET | `/submissions?phone=` | list submissions |
| POST | `/submissions/{id}/decision` | approve/cancel inside the app |
| GET | `/app` | the PWA |
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
