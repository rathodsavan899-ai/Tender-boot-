"""Our own OTP system: generate a code, store only a keyed hash, send it by SMS (Fast2SMS OTP route), verify it.

Indian (+91) mobile numbers only. Codes expire (OTP_EXPIRY_MINUTES), allow 5 wrong attempts and work once.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

import httpx
from sqlalchemy import delete, select

from agents import logger
from config import get_settings
from database import OtpCode, SessionLocal, normalize_phone, utcnow

logging.getLogger("httpx").setLevel(logging.WARNING)  # never write request details to the logs

FAST2SMS_URL = "https://www.fast2sms.com/dev/bulkV2"
MAX_ATTEMPTS = 5
RESEND_SECONDS = 30


def _hash(phone: str, code: str) -> str:
    s = get_settings()
    key = (s.file_encryption_secret or s.fast2sms_api_key).encode("utf-8")
    return hmac.new(key, f"{phone}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def indian_number(e164: str) -> str | None:
    """'+919876543210' -> '9876543210'; None for anything that is not a valid Indian mobile number."""
    if e164.startswith("+91") and len(e164) == 13 and e164[3:].isdigit() and e164[3] in "6789":
        return e164[3:]
    return None


def _send_sms(number: str, code: str) -> tuple[bool, str | None]:
    try:
        response = httpx.post(
            FAST2SMS_URL,
            headers={"authorization": get_settings().fast2sms_api_key, "Content-Type": "application/json"},
            json={"route": "otp", "variables_values": code, "numbers": number},
            timeout=20,
        )
        data = response.json()
    except Exception as exc:
        logger.error("Fast2SMS request failed: %s", type(exc).__name__)
        return False, "network"
    if data.get("return") is True:
        return True, None
    logger.error("Fast2SMS rejected the OTP request: %s", str(data.get("message") or data)[:300])
    return False, "provider"


def send_otp(phone: str) -> dict:
    """Create and SMS a 6-digit code. Returns {"sent": bool, "error": None | cooldown | only_india | provider | network}."""
    s = get_settings()
    e164 = normalize_phone(phone)
    number = indian_number(e164)
    if number is None:
        return {"sent": False, "error": "only_india"}
    now = utcnow()
    with SessionLocal() as db:
        last = db.scalar(select(OtpCode).where(OtpCode.phone == e164).order_by(OtpCode.created_at.desc()))
        if last and (now - last.created_at).total_seconds() < RESEND_SECONDS:
            return {"sent": False, "error": "cooldown"}
        code = f"{secrets.randbelow(10**6):06d}"
        db.execute(delete(OtpCode).where(OtpCode.phone == e164))
        db.add(OtpCode(phone=e164, code_hash=_hash(e164, code), expires_at=now + timedelta(minutes=s.otp_expiry_minutes)))
        db.commit()
    sent, error = _send_sms(number, code)
    return {"sent": sent, "error": error}


def check_otp(phone: str, code: str) -> bool:
    """True only for the latest, unexpired, unused code, within MAX_ATTEMPTS tries."""
    e164 = normalize_phone(phone)
    code = (code or "").strip()
    if not (code.isdigit() and len(code) == 6):
        return False
    with SessionLocal() as db:
        row = db.scalar(select(OtpCode).where(OtpCode.phone == e164, OtpCode.used.is_(False))
                        .order_by(OtpCode.created_at.desc()))
        if row is None or row.expires_at < utcnow() or row.attempts >= MAX_ATTEMPTS:
            return False
        row.attempts += 1
        ok = hmac.compare_digest(row.code_hash, _hash(e164, code))
        if ok:
            row.used = True
        db.commit()
        return ok
