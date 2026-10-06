"""Twilio WhatsApp + Marathi/English voice calls, YES/NO parsing, submission dispatch."""
from __future__ import annotations

import json
import re

import httpx
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import Gather, VoiceResponse

from agents import format_inr, logger
from config import get_settings
from database import Submission, normalize_phone

MARATHI_VOICE = "Google.mr-IN-Standard-A"
ENGLISH_VOICE = "Google.en-IN-Standard-A"

YES_WORDS = {"yes", "y", "ok", "okay", "हो", "होय", "हां", "हा", "ठीक", "1"}
NO_WORDS = {"no", "n", "cancel", "नाही", "नको", "नाहि", "रद्द", "2"}


def _client() -> Client:
    s = get_settings()
    return Client(s.twilio_account_sid, s.twilio_auth_token)


def parse_decision(body: str | None) -> str | None:
    """Map a reply to 'YES' / 'NO' / None."""
    text = re.sub(r"[^\w\s]", "", (body or "").strip().lower())
    if text in YES_WORDS:
        return "YES"
    if text in NO_WORDS:
        return "NO"
    return None


def send_whatsapp(to: str, body: str, content_variables: dict | None = None) -> dict:
    """Send a WhatsApp message. Without Twilio credentials it returns a dry-run result (nothing is sent)."""
    s = get_settings()
    to_addr = "whatsapp:" + normalize_phone(to)
    if not s.twilio_configured:
        logger.warning("Twilio not configured — WhatsApp dry run to %s", to_addr)
        return {"sent": False, "mode": "dry_run", "to": to_addr, "body": body}
    try:
        kwargs: dict = {"from_": s.twilio_whatsapp_from, "to": to_addr}
        if content_variables is not None and s.twilio_approval_content_sid:
            kwargs.update(content_sid=s.twilio_approval_content_sid, content_variables=json.dumps(content_variables))
        else:
            kwargs["body"] = body
        message = _client().messages.create(**kwargs)
        return {"sent": True, "mode": "twilio", "to": to_addr, "sid": message.sid}
    except Exception as exc:
        logger.error("WhatsApp send failed: %s", exc)
        return {"sent": False, "mode": "error", "to": to_addr, "error": str(exc)}


def send_approval_prompt(to: str, tender_title: str, bid_amount: float) -> dict:
    text = (
        f"भाऊ, {format_inr(bid_amount)} चे टेंडर सबमिट करू का?\n"
        f"टेंडर: {tender_title}\n\nउत्तर द्या: *YES* (सबमिट करा) किंवा *NO* (रद्द करा)"
    )
    return send_whatsapp(to, text, content_variables={"1": tender_title, "2": format_inr(bid_amount)})


def make_voice_call(to: str, submission_id: int) -> dict:
    s = get_settings()
    to_number = normalize_phone(to)
    if not (s.twilio_configured and s.twilio_voice_from):
        logger.warning("Twilio voice not configured — dry run call to %s", to_number)
        return {"called": False, "mode": "dry_run", "to": to_number}
    try:
        call = _client().calls.create(
            to=to_number, from_=s.twilio_voice_from,
            url=f"{s.public_base_url.rstrip('/')}/voice-prompt/{submission_id}", method="POST",
        )
        return {"called": True, "mode": "twilio", "to": to_number, "sid": call.sid}
    except Exception as exc:
        logger.error("Voice call failed: %s", exc)
        return {"called": False, "mode": "error", "to": to_number, "error": str(exc)}


def voice_prompt_twiml(submission: Submission) -> str:
    base = get_settings().public_base_url.rstrip("/")
    amount = f"{int(round(submission.bid_amount))}"
    response = VoiceResponse()
    gather = Gather(num_digits=1, action=f"{base}/voice-response/{submission.id}", method="POST", timeout=10)
    gather.say(
        f"नमस्कार भाऊ. टेंडर बॅाट बोलतोय. {submission.tender_title} या टेंडरसाठी रुपये {amount} ची बिड सबमिट करू का? "
        "सबमिट करण्यासाठी एक दाबा. रद्द करण्यासाठी दोन दाबा.",
        voice=MARATHI_VOICE, language="mr-IN",
    )
    gather.say(
        f"This is TenderBot. Shall I submit the bid of rupees {amount}? Press 1 to submit, press 2 to cancel.",
        voice=ENGLISH_VOICE, language="en-IN",
    )
    response.append(gather)
    response.say("उत्तर मिळाले नाही. आम्ही तुम्हाला व्हॉट्सॲपवर विचारू. धन्यवाद.", voice=MARATHI_VOICE, language="mr-IN")
    return str(response)


def voice_result_twiml(decision: str | None, extra: str = "") -> str:
    response = VoiceResponse()
    if decision == "YES":
        text = "ठीक आहे भाऊ, सबमिशनसाठी मंजुरी नोंदवली आहे. " + extra
    elif decision == "NO":
        text = "ठीक आहे भाऊ, टेंडर रद्द केले आहे."
    elif decision == "BLOCKED":
        text = "भाऊ, तुमचा प्लॅन सक्रिय नसल्याने सबमिशन होऊ शकत नाही. तपशील व्हॉट्सॲपवर पाठवला आहे."
    else:
        text = "क्षमस्व, तुमचे उत्तर समजले नाही. कृपया व्हॉट्सॲपवर YES किंवा NO पाठवा."
    response.say(text, voice=MARATHI_VOICE, language="mr-IN")
    return str(response)


def whatsapp_reply_twiml(message: str) -> str:
    reply = MessagingResponse()
    reply.message(message)
    return str(reply)


def dispatch_submission(submission: Submission) -> tuple[str, str]:
    """Execute an approved submission. Returns (status, detail).

    Portal submission needs your Digital Signature Certificate, so it is performed by the service behind
    SUBMISSION_WEBHOOK_URL. Without it the bid is marked approved and waits for portal submission — it is
    NEVER reported as SUBMITTED unless the downstream service confirms with a 2xx response.
    """
    url = get_settings().submission_webhook_url
    if not url:
        return ("APPROVED_AWAITING_PORTAL_SUBMISSION",
                "मंजुरी नोंदवली. पोर्टलवर DSC ने प्रत्यक्ष सबमिशन अजून बाकी आहे.")
    payload = {"submission_id": submission.id, "tender_ref": submission.tender_ref,
               "tender_title": submission.tender_title, "bid_amount": submission.bid_amount}
    try:
        response = httpx.post(url, json=payload, timeout=60)
        response.raise_for_status()
        return "SUBMITTED", "सबमिशन सेवेने यशस्वी असल्याचे कळवले."
    except Exception as exc:
        logger.error("submission webhook failed: %s", exc)
        return "APPROVED_SUBMISSION_FAILED", f"सबमिशन सेवा अयशस्वी: {exc}"
