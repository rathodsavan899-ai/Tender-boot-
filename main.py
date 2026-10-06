"""TenderBot AI — FastAPI application."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from agents import LLMUnavailable, format_inr, llm_available
from agents import (analyzer_agent, bg_emd_agent, communication_agent, competitor_agent, marketplace_agent,
                    payment_delay_agent, scraper_agent, tax_agent, vault_agent)
from config import get_settings
from database import (Contractor, PaymentBill, SessionLocal, Submission, Tender, check_access, get_db,
                      get_or_create_contractor, init_db, normalize_phone, utcnow)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("tenderbot")
settings = get_settings()


# ------------------------------------------------------------------ scheduler
async def _vault_loop() -> None:
    while True:
        try:
            def job():
                with SessionLocal() as db:
                    return vault_agent.run_expiry_alerts(db)
            logger.info("vault expiry run: %s", await asyncio.to_thread(job))
        except Exception:
            logger.exception("vault expiry run failed")
        await asyncio.sleep(settings.vault_check_interval_hours * 3600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = asyncio.create_task(_vault_loop()) if settings.enable_scheduler else None
    yield
    if task:
        task.cancel()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)


# ------------------------------------------------------------------ schemas (Pydantic v2)
class VendorProfile(BaseModel):
    phone: str = Field(description="WhatsApp number, e.g. +919876543210")
    name: str
    contractor_class: str | None = None
    categories: list[str] = Field(default_factory=list)
    districts: list[str] = Field(default_factory=list)
    annual_turnover: float | None = Field(default=None, ge=0)
    documents_held: list[str] = Field(default_factory=list)


class TenderInfo(BaseModel):
    tender_id: str
    title: str
    department: str
    category: str
    district: str | None = None
    estimated_cost: float = Field(gt=0)
    emd_amount: float | None = Field(default=None, ge=0)
    required_documents: list[str] = Field(default_factory=list)
    minimum_class: str | None = None
    min_turnover: float | None = Field(default=None, ge=0)
    tender_text: str | None = Field(default=None, description="Raw tender text; requirements are extracted with GPT-4o if no required_documents given")
    source_url: str | None = None


class AnalyzeRequest(BaseModel):
    vendor: VendorProfile
    tender: TenderInfo
    send_whatsapp: bool = True


class BidRateRequest(BaseModel):
    phone: str
    tender: TenderInfo
    own_cost_estimate: float | None = Field(default=None, gt=0, description="Your own estimated execution cost (INR)")


class SubmitApprovalRequest(BaseModel):
    phone: str
    tender_id: str
    tender_title: str
    bid_amount: float = Field(gt=0)
    place_call: bool = True


class PaymentDesk(BaseModel):
    desk: str
    received_on: date | None = None
    remarks: str | None = None


class PaymentNoticeRequest(BaseModel):
    phone: str
    contractor_name: str
    department: str
    office_address: str | None = None
    officer_designation: str = "कार्यकारी अभियंता"
    work_name: str
    work_order_no: str | None = None
    bill_no: str
    bill_amount: float = Field(gt=0)
    bill_submitted_on: date
    desk_trail: list[PaymentDesk] = Field(default_factory=list)
    send_whatsapp: bool = False


class PurchaseItem(BaseModel):
    description: str
    taxable_value: float = Field(ge=0)
    gst_rate_percent: float = Field(ge=0, le=28)
    itc_eligible: bool = True


class TaxRequest(BaseModel):
    phone: str
    taxable_value: float = Field(gt=0)
    gst_rate_percent: float | None = Field(default=None, ge=0, le=28)
    intra_state: bool = True
    purchases: list[PurchaseItem] = Field(default_factory=list)
    gst_tds_applicable: bool = False


class EmdKitRequest(BaseModel):
    phone: str
    contractor_name: str
    tender_id: str
    tender_title: str
    department: str
    bg_type: str = Field(default="EMD_BG", pattern="^(EMD_BG|PERFORMANCE_BG)$")
    guarantee_amount: float = Field(gt=0)
    validity_months: int = Field(default=6, ge=1, le=120)
    bank_name: str | None = None
    branch: str | None = None
    account_number_last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    beneficiary: str | None = None
    send_whatsapp: bool = True


class VaultDocIn(BaseModel):
    phone: str
    doc_type: str
    doc_number: str | None = None
    expiry_date: date | None = None
    file_ref: str | None = None


class AwardedIngestRequest(BaseModel):
    source: str = Field(pattern="^(Mahatenders|CPPP)$")
    url: str | None = None
    category: str | None = None
    department: str | None = None
    records: list[dict] = Field(default_factory=list)


class VendorIn(BaseModel):
    name: str
    category: str
    district: str
    phone: str
    rate: float | None = None
    rate_unit: str | None = None
    verified_by: str | None = None
    last_verified_on: date | None = None


class SetPlanRequest(BaseModel):
    phone: str
    plan: str = Field(pattern="^(none|basic|vip)$")
    days: int = Field(default=30, ge=1, le=366)


class DiscoverRequest(BaseModel):
    url: str


# ------------------------------------------------------------------ helpers
def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not settings.admin_api_key:
        raise HTTPException(503, "ADMIN_API_KEY सेट केलेली नाही; admin एंडपॉइंट्स बंद आहेत.")
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(401, "अवैध admin key")


def contractor_for(db: Session, phone: str, **profile) -> Contractor:
    try:
        return get_or_create_contractor(db, phone, **profile)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


def gate(contractor: Contractor, feature: str) -> None:
    allowed, message = check_access(contractor, feature)
    if not allowed:
        raise HTTPException(402, detail={"message_mr": message, "plan_status": contractor.effective_plan(),
                                         "trial_day": contractor.trial_day()})


def plan_info(contractor: Contractor) -> dict:
    return {"plan_status": contractor.effective_plan(), "trial_day": contractor.trial_day(),
            "trial_days_total": settings.trial_days}


def apply_decision(db: Session, submission: Submission, decision: str, channel: str) -> dict:
    """Execute (YES) or cancel (NO) a pending submission. Idempotent for already-decided submissions."""
    if submission.status != "PENDING":
        return {"status": submission.status, "message_mr": "या सबमिशनवर आधीच निर्णय झाला आहे.", "already_decided": True}
    submission.decision_channel = channel
    submission.decided_at = utcnow()
    if decision == "NO":
        submission.status, submission.status_detail = "CANCELLED", "कंत्राटदाराने रद्द केले."
        message = "ठीक आहे भाऊ, टेंडर सबमिशन रद्द केले आहे."
    else:
        contractor = db.get(Contractor, submission.contractor_id)
        allowed, block_msg = check_access(contractor, "submit")
        if not allowed:
            submission.status, submission.status_detail = "CANCELLED", "प्लॅन/ट्रायलमुळे ब्लॉक."
            db.commit()
            return {"status": "CANCELLED", "message_mr": block_msg, "already_decided": False}
        submission.status, submission.status_detail = communication_agent.dispatch_submission(submission)
        message = {
            "SUBMITTED": f"✅ भाऊ, {format_inr(submission.bid_amount)} चे टेंडर सबमिट झाले आहे.",
            "APPROVED_AWAITING_PORTAL_SUBMISSION": (
                f"👍 मंजुरी नोंदवली ({format_inr(submission.bid_amount)}). पोर्टलवर DSC ने सबमिशन अजून बाकी आहे — अजून सबमिट झालेले नाही."),
            "APPROVED_SUBMISSION_FAILED": "⚠️ मंजुरी नोंदवली, पण सबमिशन सेवा अयशस्वी झाली. टेंडर अजून सबमिट झालेले नाही.",
        }[submission.status]
    db.commit()
    return {"status": submission.status, "message_mr": message, "detail": submission.status_detail, "already_decided": False}


def xml(content: str) -> Response:
    return Response(content=content, media_type="application/xml")


# ------------------------------------------------------------------ 1. health
@app.get("/")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {
        "app": settings.app_name, "version": settings.app_version, "status": "ok",
        "database": "connected", "gpt4o_configured": llm_available(),
        "twilio_configured": settings.twilio_configured,
        "tagline_mr": "कंत्राटदाराचा हक्काचा आणि विश्वासू डिजिटल मॅनेजर",
    }


# ------------------------------------------------------------------ 2. analyze tender
@app.post("/analyze-tender")
def analyze_tender(req: AnalyzeRequest, db: Session = Depends(get_db)) -> dict:
    v, t = req.vendor, req.tender
    contractor = contractor_for(db, v.phone, name=v.name, contractor_class=v.contractor_class,
                                categories=v.categories, districts=v.districts, annual_turnover=v.annual_turnover)
    gate(contractor, "analyze")

    required_docs, minimum_class, min_turnover, emd = t.required_documents, t.minimum_class, t.min_turnover, t.emd_amount
    source = "provided"
    if not required_docs:
        if not t.tender_text:
            raise HTTPException(422, "required_documents किंवा tender_text द्या.")
        try:
            extracted = analyzer_agent.extract_requirements(t.tender_text)
        except LLMUnavailable as exc:
            raise HTTPException(503, f"tender_text वरून अटी काढण्यासाठी GPT-4o आवश्यक: {exc}")
        required_docs = extracted["required_documents"]
        minimum_class = minimum_class or extracted["minimum_class"]
        min_turnover = min_turnover or extracted["min_turnover"]
        emd = emd or extracted["emd_amount"]
        source = "gpt4o_extracted"

    existing = db.scalar(select(Tender).where(Tender.tender_ref == t.tender_id))
    if existing is None:
        db.add(Tender(tender_ref=t.tender_id, title=t.title, department=t.department, category=t.category,
                      district=t.district, estimated_cost=t.estimated_cost, emd_amount=emd, source_url=t.source_url))
        db.commit()

    analysis = analyzer_agent.gap_analysis(required_docs, v.documents_held, v.contractor_class, minimum_class,
                                           v.annual_turnover, min_turnover)
    tender_view = {"tender_id": t.tender_id, "title": t.title, "department": t.department,
                   "estimated_cost": t.estimated_cost, "emd_amount": emd}
    alert_text = analyzer_agent.build_whatsapp_alert(tender_view, analysis)

    alert_allowed, alert_block = check_access(contractor, "alerts")
    if req.send_whatsapp and alert_allowed:
        whatsapp = communication_agent.send_whatsapp(contractor.phone, alert_text)
    else:
        whatsapp = {"sent": False, "mode": "skipped",
                    "reason_mr": alert_block if not alert_allowed else "send_whatsapp=false"}
    return {"requirements_source": source, "required_documents": required_docs, "analysis": analysis,
            "whatsapp_alert_text": alert_text, "whatsapp_delivery": whatsapp, **plan_info(contractor)}


# ------------------------------------------------------------------ 3. predict bid rate
@app.post("/predict-bid-rate")
def predict_bid_rate(req: BidRateRequest, db: Session = Depends(get_db)) -> dict:
    contractor = contractor_for(db, req.phone)
    gate(contractor, "predict_bid")
    prediction = competitor_agent.predict_l1(db, req.tender.category, req.tender.department,
                                             req.tender.estimated_cost, req.own_cost_estimate)
    return {"tender_id": req.tender.tender_id, "estimated_cost": req.tender.estimated_cost,
            "prediction": prediction, **plan_info(contractor)}


# ------------------------------------------------------------------ 4. request submit approval
@app.post("/request-submit-approval")
def request_submit_approval(req: SubmitApprovalRequest, db: Session = Depends(get_db)) -> dict:
    contractor = contractor_for(db, req.phone)
    gate(contractor, "submit")
    submission = Submission(contractor_id=contractor.id, tender_ref=req.tender_id,
                            tender_title=req.tender_title, bid_amount=req.bid_amount)
    db.add(submission)
    db.commit()
    db.refresh(submission)

    whatsapp = communication_agent.send_approval_prompt(contractor.phone, req.tender_title, req.bid_amount)
    submission.whatsapp_sid = whatsapp.get("sid")

    call: dict = {"called": False, "mode": "skipped"}
    voice_allowed, voice_block = check_access(contractor, "voice")
    if req.place_call:
        if voice_allowed:
            call = communication_agent.make_voice_call(contractor.phone, submission.id)
            submission.call_sid = call.get("sid")
        else:
            call = {"called": False, "mode": "blocked", "reason_mr": voice_block}
    db.commit()
    return {"submission_id": submission.id, "status": submission.status,
            "prompt_mr": f"भाऊ, {format_inr(req.bid_amount)} चे टेंडर सबमिट करू का?",
            "whatsapp": whatsapp, "voice_call": call, **plan_info(contractor)}


# ------------------------------------------------------------------ 5. WhatsApp webhook (YES/NO)
async def _verify_twilio(request: Request, form: dict) -> None:
    if not settings.validate_twilio_signature:
        return
    from twilio.request_validator import RequestValidator
    signature = request.headers.get("X-Twilio-Signature", "")
    url = settings.public_base_url.rstrip("/") + request.url.path
    if not RequestValidator(settings.twilio_auth_token).validate(url, form, signature):
        raise HTTPException(403, "अवैध Twilio signature")


@app.post("/whatsapp-webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)) -> Response:
    form = {k: str(v) for k, v in (await request.form()).items()}
    await _verify_twilio(request, form)
    try:
        phone = normalize_phone(form.get("From", ""))
    except ValueError:
        return xml(communication_agent.whatsapp_reply_twiml("नंबर ओळखता आला नाही."))

    contractor = db.scalar(select(Contractor).where(Contractor.phone == phone))
    pending = None
    if contractor:
        pending = db.scalar(select(Submission).where(Submission.contractor_id == contractor.id, Submission.status == "PENDING")
                            .order_by(Submission.created_at.desc()))
    if pending is None:
        return xml(communication_agent.whatsapp_reply_twiml("भाऊ, सध्या मंजुरीसाठी कोणतेही टेंडर प्रलंबित नाही."))

    decision = communication_agent.parse_decision(form.get("Body"))
    if decision is None:
        return xml(communication_agent.whatsapp_reply_twiml(
            f"भाऊ, {format_inr(pending.bid_amount)} चे टेंडर सबमिट करू का? कृपया *YES* किंवा *NO* पाठवा."))
    result = await asyncio.to_thread(apply_decision, db, pending, decision, "whatsapp")
    return xml(communication_agent.whatsapp_reply_twiml(result["message_mr"]))


# Voice-call endpoints used by Twilio (TwiML)
@app.post("/voice-prompt/{submission_id}")
def voice_prompt(submission_id: int, db: Session = Depends(get_db)) -> Response:
    submission = db.get(Submission, submission_id)
    if submission is None or submission.status != "PENDING":
        return xml(communication_agent.voice_result_twiml(None))
    return xml(communication_agent.voice_prompt_twiml(submission))


@app.post("/voice-response/{submission_id}")
async def voice_response(submission_id: int, request: Request, db: Session = Depends(get_db)) -> Response:
    form = {k: str(v) for k, v in (await request.form()).items()}
    await _verify_twilio(request, form)
    submission = db.get(Submission, submission_id)
    decision = {"1": "YES", "2": "NO"}.get(form.get("Digits", ""))
    if submission is None or decision is None:
        return xml(communication_agent.voice_result_twiml(None))
    result = await asyncio.to_thread(apply_decision, db, submission, decision, "voice")
    if decision == "YES" and result["status"] == "CANCELLED":
        return xml(communication_agent.voice_result_twiml("BLOCKED"))
    extra = "पोर्टलवरील सबमिशन अजून बाकी आहे." if submission.status == "APPROVED_AWAITING_PORTAL_SUBMISSION" else ""
    return xml(communication_agent.voice_result_twiml(decision, extra))


@app.get("/submissions/{submission_id}")
def submission_status(submission_id: int, db: Session = Depends(get_db)) -> dict:
    s = db.get(Submission, submission_id)
    if s is None:
        raise HTTPException(404, "सबमिशन सापडले नाही")
    return {"id": s.id, "tender_ref": s.tender_ref, "bid_amount": s.bid_amount, "status": s.status,
            "detail": s.status_detail, "channel": s.decision_channel}


# ------------------------------------------------------------------ 6. payment notice
@app.post("/generate-payment-notice")
def generate_payment_notice(req: PaymentNoticeRequest, db: Session = Depends(get_db)) -> dict:
    contractor = contractor_for(db, req.phone, name=req.contractor_name)
    gate(contractor, "payment_notice")
    trail = [{"desk": d.desk, "received_on": d.received_on.isoformat() if d.received_on else None, "remarks": d.remarks}
             for d in req.desk_trail]
    bill = db.scalar(select(PaymentBill).where(PaymentBill.contractor_id == contractor.id, PaymentBill.bill_no == req.bill_no,
                                               PaymentBill.department == req.department))
    if bill is None:
        bill = PaymentBill(contractor_id=contractor.id, department=req.department, work_name=req.work_name,
                           work_order_no=req.work_order_no, bill_no=req.bill_no, bill_amount=req.bill_amount,
                           bill_submitted_on=req.bill_submitted_on, desk_trail=trail)
        db.add(bill)
    else:
        bill.desk_trail = trail or bill.desk_trail
        bill.bill_amount = req.bill_amount
    notice = payment_delay_agent.generate_notice(bill, req.contractor_name, req.officer_designation, req.office_address)
    bill.last_notice_on = date.today()
    bill.notices_sent = (bill.notices_sent or 0) + 1
    db.commit()
    whatsapp = None
    if req.send_whatsapp:
        whatsapp = communication_agent.send_whatsapp(contractor.phone, notice["notice_mr"])
    return {"bill_id": bill.id, **notice, "whatsapp_delivery": whatsapp, **plan_info(contractor)}


# ------------------------------------------------------------------ 7. tax advice
@app.post("/get-tax-advice")
def get_tax_advice(req: TaxRequest, db: Session = Depends(get_db)) -> dict:
    contractor = contractor_for(db, req.phone)
    gate(contractor, "tax_draft")
    rate = req.gst_rate_percent if req.gst_rate_percent is not None else settings.gst_rate_percent
    result = tax_agent.compute(req.taxable_value, rate, req.intra_state,
                               [p.model_dump() for p in req.purchases], req.gst_tds_applicable)
    export_allowed, export_block = check_access(contractor, "tax_export")
    result["ca_ready_export"] = {"available": export_allowed}
    if not export_allowed:
        result["ca_ready_export"]["message_mr"] = export_block
        result["ca_ready_breakdown"] = None
        result["draft_only"] = True
    return {**result, **plan_info(contractor)}


# ------------------------------------------------------------------ extra feature endpoints
@app.post("/generate-emd-kit")
def generate_emd_kit(req: EmdKitRequest, db: Session = Depends(get_db)) -> dict:
    contractor = contractor_for(db, req.phone, name=req.contractor_name)
    gate(contractor, "bg_emd")
    kit = bg_emd_agent.build_kit(req.contractor_name, req.tender_id, req.tender_title, req.department, req.bg_type,
                                 req.guarantee_amount, req.validity_months, req.bank_name, req.branch,
                                 req.account_number_last4, req.beneficiary)
    kit["whatsapp_delivery"] = communication_agent.send_whatsapp(contractor.phone, kit["whatsapp_message"]) if req.send_whatsapp else None
    return {**kit, **plan_info(contractor)}


@app.get("/marketplace/search")
def marketplace_search(phone: str, category: str, district: str | None = None, db: Session = Depends(get_db)) -> dict:
    contractor = contractor_for(db, phone)
    gate(contractor, "marketplace")
    return marketplace_agent.search_vendors(db, category, district)


@app.post("/vault/documents")
def vault_add(req: VaultDocIn, db: Session = Depends(get_db)) -> dict:
    contractor = contractor_for(db, req.phone)
    gate(contractor, "vault")
    doc = vault_agent.add_document(db, contractor, req.doc_type, req.doc_number, req.expiry_date, req.file_ref)
    return vault_agent.serialize(doc)


@app.get("/vault/documents")
def vault_list(phone: str, db: Session = Depends(get_db)) -> dict:
    contractor = contractor_for(db, phone)
    gate(contractor, "vault")
    return {"documents": vault_agent.list_documents(db, contractor),
            "expiring_within_alert_window": vault_agent.expiring_documents(db, contractor)}


@app.post("/discover-tenders")
def discover_tenders(req: DiscoverRequest) -> dict:
    try:
        rows = scraper_agent.discover_active_tenders(req.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"पेज वाचता आले नाही: {exc}")
    return {"count": len(rows), "tenders": rows[:100]}


# ------------------------------------------------------------------ admin
@app.post("/admin/ingest-awarded-data", dependencies=[Depends(require_admin)])
def admin_ingest(req: AwardedIngestRequest, db: Session = Depends(get_db)) -> dict:
    if not req.url and not req.records:
        raise HTTPException(422, "url किंवा records द्या.")
    try:
        if req.url:
            return scraper_agent.ingest_awarded_from_url(db, req.url, req.source, req.category, req.department)
        return scraper_agent.ingest_awarded_json(db, req.records, req.source, req.category)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"इनजेस्ट अयशस्वी: {exc}")


@app.post("/admin/vendors", dependencies=[Depends(require_admin)])
def admin_add_vendor(req: VendorIn, db: Session = Depends(get_db)) -> dict:
    vendor = marketplace_agent.add_vendor(db, req.name, req.category, req.district, req.phone, req.rate,
                                          req.rate_unit, req.verified_by, req.last_verified_on)
    return {"id": vendor.id, "name": vendor.name}


@app.post("/admin/set-plan", dependencies=[Depends(require_admin)])
def admin_set_plan(req: SetPlanRequest, db: Session = Depends(get_db)) -> dict:
    from datetime import timedelta
    contractor = contractor_for(db, req.phone)
    contractor.plan = req.plan
    contractor.plan_expires_at = utcnow() + timedelta(days=req.days) if req.plan != "none" else None
    db.commit()
    return {"phone": contractor.phone, **plan_info(contractor)}


@app.post("/admin/run-vault-alerts", dependencies=[Depends(require_admin)])
def admin_run_vault_alerts(db: Session = Depends(get_db)) -> dict:
    return vault_agent.run_expiry_alerts(db)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
