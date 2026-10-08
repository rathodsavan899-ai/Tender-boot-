"""VIP document vault with auto-renewal alerts (PWD licence, Class-1 certificate, EPF, GST ...)."""
from __future__ import annotations

import base64
import hashlib
import os
from datetime import date, timedelta
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents import fmt_date, logger
from agents.communication_agent import send_whatsapp
from config import get_settings
from database import Contractor, VaultDocument, VaultFile, check_access


class FileStorageDisabled(RuntimeError):
    """FILE_ENCRYPTION_SECRET is not configured, so uploads are refused (never stored unencrypted)."""


class InvalidFile(ValueError):
    pass


def is_aadhaar(doc_type: str) -> bool:
    low = (doc_type or "").lower()
    return "aadhaar" in low or "aadhar" in low or "आधार" in low


@lru_cache(maxsize=1)
def _fernet_for(secret: str) -> Fernet:
    key = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), b"tenderbot-vault-v1", 200_000, dklen=32)
    return Fernet(base64.urlsafe_b64encode(key))


def _fernet() -> Fernet:
    secret = get_settings().file_encryption_secret.strip()
    if not secret:
        raise FileStorageDisabled("FILE_ENCRYPTION_SECRET सेट केलेली नाही")
    return _fernet_for(secret)


def sniff_type(data: bytes) -> str | None:
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _safe_name(name: str) -> str:
    base = os.path.basename((name or "file").replace("\\", "/"))
    cleaned = "".join(ch for ch in base if ch.isprintable() and ch not in '<>:"|?*')
    return (cleaned.strip() or "file")[:120]


def save_file(db: Session, contractor: Contractor, doc: VaultDocument, filename: str, data: bytes) -> VaultFile:
    """Validate (type by content, size), encrypt and store; replaces any previous file of this document."""
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if len(data) == 0:
        raise InvalidFile("empty")
    if len(data) > max_bytes:
        raise InvalidFile("too_big")
    content_type = sniff_type(data)
    if content_type is None:
        raise InvalidFile("bad_type")
    encrypted = _fernet().encrypt(data)
    old = db.scalar(select(VaultFile).where(VaultFile.document_id == doc.id))
    if old:
        db.delete(old)
        db.flush()
    row = VaultFile(contractor_id=contractor.id, document_id=doc.id, filename=_safe_name(filename),
                    content_type=content_type, size=len(data), data=encrypted)
    db.add(row)
    db.commit()
    return row


def load_file(db: Session, doc: VaultDocument) -> tuple[bytes, str, str] | None:
    row = db.scalar(select(VaultFile).where(VaultFile.document_id == doc.id))
    if row is None:
        return None
    try:
        return _fernet().decrypt(row.data), row.content_type, row.filename
    except InvalidToken:
        raise FileStorageDisabled("फाइल डिक्रिप्ट होऊ शकली नाही (secret बदलले असेल)")


def delete_document(db: Session, doc: VaultDocument) -> None:
    for row in db.scalars(select(VaultFile).where(VaultFile.document_id == doc.id)):
        db.delete(row)
    db.delete(doc)
    db.commit()


def add_document(db: Session, contractor: Contractor, doc_type: str, doc_number: str | None,
                 expiry_date: date | None, file_ref: str | None) -> VaultDocument:
    if is_aadhaar(doc_type):
        doc_number = None  # Aadhaar number is never stored; only the (encrypted) file
    doc = VaultDocument(contractor_id=contractor.id, doc_type=doc_type, doc_number=doc_number,
                        expiry_date=expiry_date, file_ref=file_ref)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def serialize(doc: VaultDocument, today: date | None = None, file_meta: tuple[str, int] | None = None) -> dict:
    today = today or date.today()
    days_left = (doc.expiry_date - today).days if doc.expiry_date else None
    status = "no_expiry" if days_left is None else "expired" if days_left < 0 else "expiring_soon" if days_left <= get_settings().expiry_alert_days else "valid"
    return {"id": doc.id, "doc_type": doc.doc_type, "doc_number": doc.doc_number,
            "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
            "days_left": days_left, "status": status, "file_ref": doc.file_ref,
            "has_file": file_meta is not None, "file_name": file_meta[0] if file_meta else None,
            "file_size": file_meta[1] if file_meta else None}


def list_documents(db: Session, contractor: Contractor) -> list[dict]:
    docs = db.scalars(select(VaultDocument).where(VaultDocument.contractor_id == contractor.id)
                      .order_by(VaultDocument.expiry_date.is_(None), VaultDocument.expiry_date))
    files = {row[0]: (row[1], row[2]) for row in db.execute(
        select(VaultFile.document_id, VaultFile.filename, VaultFile.size).where(VaultFile.contractor_id == contractor.id))}
    return [serialize(d, None, files.get(d.id)) for d in docs]


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
