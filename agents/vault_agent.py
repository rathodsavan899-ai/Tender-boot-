"""VIP document vault with auto-renewal alerts (PWD licence, Class-1 certificate, EPF, GST ...)."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents import fmt_date, logger
from agents.communication_agent import send_whatsapp
from config import get_settings
from database import Contractor, VaultDocument, check_access


def add_document(db: Session, contractor: Contractor, doc_type: str, doc_number: str | None,
                 expiry_date: date | None, file_ref: str | None) -> VaultDocument:
    doc = VaultDocument(contractor_id=contractor.id, doc_type=doc_type, doc_number=doc_number,
                        expiry_date=expiry_date, file_ref=file_ref)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def serialize(doc: VaultDocument, today: date | None = None) -> dict:
    today = today or date.today()
    days_left = (doc.expiry_date - today).days if doc.expiry_date else None
    status = "no_expiry" if days_left is None else "expired" if days_left < 0 else "expiring_soon" if days_left <= get_settings().expiry_alert_days else "valid"
    return {"id": doc.id, "doc_type": doc.doc_type, "doc_number": doc.doc_number,
            "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
            "days_left": days_left, "status": status, "file_ref": doc.file_ref}


def list_documents(db: Session, contractor: Contractor) -> list[dict]:
    docs = db.scalars(select(VaultDocument).where(VaultDocument.contractor_id == contractor.id)
                      .order_by(VaultDocument.expiry_date.is_(None), VaultDocument.expiry_date))
    return [serialize(d) for d in docs]


def expiring_documents(db: Session, contractor: Contractor, within_days: int | None = None) -> list[dict]:
    within = within_days if within_days is not None else get_settings().expiry_alert_days
    return [d for d in list_documents(db, contractor) if d["days_left"] is not None and d["days_left"] <= within]


def alert_text(contractor: Contractor, items: list[dict]) -> str:
    lines = [f"🔔 *TenderBot AI — कागदपत्र नूतनीकरण अलर्ट*", f"नमस्कार {contractor.name or 'भाऊ'},"]
    for it in items:
        when = f"{it['days_left']} दिवसांत संपत आहे" if it["days_left"] >= 0 else f"{abs(it['days_left'])} दिवसांपूर्वी संपले आहे"
        number = f" ({it['doc_number']})" if it["doc_number"] else ""
        lines.append(f"• {it['doc_type']}{number} — {fmt_date(date.fromisoformat(it['expiry_date']))} रोजी {when}")
    lines.append("टेंडर भरण्यापूर्वी नूतनीकरण पूर्ण करा.")
    return "\n".join(lines)


def run_expiry_alerts(db: Session, today: date | None = None) -> dict:
    """Send WhatsApp alerts for documents expiring within the alert window. Safe to run daily."""
    today = today or date.today()
    window = get_settings().expiry_alert_days
    sent = skipped_locked = 0
    for contractor in db.scalars(select(Contractor)):
        allowed, _ = check_access(contractor, "alerts")
        due: list[VaultDocument] = []
        for doc in contractor.documents:
            if doc.expiry_date is None:
                continue
            days_left = (doc.expiry_date - today).days
            if days_left > window:
                continue
            recently = doc.last_alert_on is not None and (today - doc.last_alert_on).days < (1 if days_left <= 3 else 7)
            if not recently:
                due.append(doc)
        if not due:
            continue
        if not allowed:
            skipped_locked += 1
            continue
        items = [serialize(d, today) for d in due]
        result = send_whatsapp(contractor.phone, alert_text(contractor, items))
        logger.info("vault alert to %s: %s", contractor.phone, result.get("mode"))
        for doc in due:
            doc.last_alert_on = today
        db.commit()
        sent += 1
    return {"contractors_alerted": sent, "skipped_plan_locked": skipped_locked}
