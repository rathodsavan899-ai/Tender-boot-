"""Chief orchestrator: health checks, fail-safe co-pilot (backup workers) and the owner's daily report.

It is deliberately plain code, not an AI that writes or deploys code: it watches the agents, re-runs a failed task with a
lighter backup, and tells the owner on Telegram. It never touches the database schema or keys, and portal (DSC)
submission always stays with the owner.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents import communication_agent, content_agent, logger, tender_hunter_agent
from config import get_settings
from database import AgentEvent, ContentPost, ContentVideo, SessionLocal, Tender, TenderSource, utcnow

HUNTER_STALE_HOURS = 8
RERUN_PAUSE_MINUTES = 60
DRAFT_STUCK_MINUTES = 15
REPORT_HOUR_IST = 21
ICON = {"OK": "✅", "WARN": "⚠️", "FAIL": "❌", "NA": "➖"}


def _once(db: Session, key: str) -> bool:
    """True the first time `key` is seen today (and remembers it)."""
    today = content_agent.ist_today()
    if db.scalar(select(AgentEvent.id).where(AgentEvent.key == key, AgentEvent.day == today)):
        return False
    db.add(AgentEvent(key=key, day=today))
    db.commit()
    return True


def _alert_once(db: Session, key: str, text: str) -> None:
    if _once(db, key):
        communication_agent.notify_admin(text)


def _hour_ist() -> int:
    return datetime.now(content_agent.IST).hour


def _today_post(db: Session) -> ContentPost | None:
    return db.scalar(select(ContentPost).where(ContentPost.post_date == content_agent.ist_today())
                     .order_by(ContentPost.id.desc()))


# ------------------------------------------------------------------ checks
def check_hunter(db: Session) -> tuple[str, str]:
    sources = list(db.scalars(select(TenderSource).where(TenderSource.enabled.is_(True))))
    if not sources:
        return "FAIL", "कोणताही टेंडर स्रोत चालू नाही"
    down = [s.name for s in sources if s.status == "down"]
    last_ok = max((s.last_ok_at for s in sources if s.last_ok_at), default=None)
    new_24h = db.scalar(select(func.count(Tender.id)).where(Tender.created_at >= utcnow() - timedelta(hours=24))) or 0
    if len(down) == len(sources):
        return "FAIL", "सर्व स्रोत बंद: " + ", ".join(down)
    if last_ok is None:
        return "WARN", "अजून एकही यशस्वी वाचन नाही"
    age = (utcnow() - last_ok).total_seconds() / 3600
    if age > HUNTER_STALE_HOURS:
        return "WARN", f"शेवटचे यशस्वी वाचन {int(age)} तासांपूर्वी"
    note = f" (बंद: {', '.join(down)})" if down else ""
    return ("WARN" if down else "OK"), f"{len(sources) - len(down)} स्रोत चालू, गेल्या २४ तासांत नवे टेंडर {new_24h}{note}"


def check_content(db: Session) -> tuple[str, str]:
    s = get_settings()
    post = _today_post(db)
    if post is None:
        hour = _hour_ist()
        if hour >= s.content_hour_ist + 2:
            return "FAIL", "आजची पोस्ट अजून बनली नाही"
        if hour >= s.content_hour_ist:
            return "WARN", "आजची पोस्ट बनत आहे / उशीर"
        return "OK", f"सकाळी {s.content_hour_ist}:00 ला बनेल"
    try:
        delivery = json.loads(post.delivery or "{}")
    except ValueError:
        delivery = {}
    has_video = db.scalar(select(ContentVideo.id).where(ContentVideo.post_id == post.id)) is not None
    parts = ["पोस्टर ✔" if post.poster_png else "पोस्टर ✘", "व्हिडिओ ✔" if has_video else "व्हिडिओ ✘"]
    problems = []
    if post.status == "draft" and (utcnow() - post.created_at).total_seconds() > DRAFT_STUCK_MINUTES * 60:
        problems.append("तयार झाली पण पाठवली गेली नाही")
    if not (delivery.get("telegram_text") or {}).get("sent"):
        problems.append("Telegram वर पोहोचली नाही")
    for name in ("facebook", "instagram"):
        result = delivery.get(name)
        if isinstance(result, dict):
            parts.append(f"{name} {'✔' if result.get('ok') else '✘'}")
            if not result.get("ok"):
                problems.append(f"{name}: {result.get('error', 'अयशस्वी')}")
    if delivery.get("honesty_blocked"):
        problems.append("दिशाभूल-तपासणीने सोशल पोस्टिंग थांबवली")
    return ("WARN" if problems else "OK"), " · ".join(parts + problems)


def collect(db: Session) -> list[tuple[str, str, str]]:
    hunter, content = check_hunter(db), check_content(db)
    return [
        ("टेंडर शिकारी (Lead Hunter)", *hunter),
        ("मार्केटिंग आणि व्हिडिओ", *content),
        ("बिलिंग आणि ट्रायल", "NA", "Razorpay पेमेंट अजून बनलेले नाही (ट्रायल १५ दिवसांचे नियम चालू)"),
        ("ग्राहक-शोध", "NA", "बनवलेले नाही: अनोळखी लोकांना परवानगीशिवाय संपर्क करणार नाही"),
        ("DSC सबमिशन", "OK", "पोर्टल सबमिशन फक्त तुमच्या मंजुरीनंतर"),
    ]


def report_text(db: Session) -> str:
    rows = collect(db)
    stamp = datetime.now(content_agent.IST).strftime("%d/%m %H:%M")
    return f"📊 TenderBot अहवाल ({stamp})\n\n" + "\n".join(f"{ICON[st]} {name}: {msg}" for name, st, msg in rows)


# ------------------------------------------------------------------ co-pilot (backup workers)
def copilot_run() -> dict:
    actions: list[str] = []
    s = get_settings()
    with SessionLocal() as db:
        # 1) tender hunting: if stale, re-run the crawl (the backup worker), but not more than once an hour
        status, msg = check_hunter(db)
        if status in ("WARN", "FAIL"):
            runs = [x.last_run_at for x in db.scalars(select(TenderSource)) if x.last_run_at]
            if not runs or (utcnow() - max(runs)).total_seconds() > RERUN_PAUSE_MINUTES * 60:
                try:
                    tender_hunter_agent.run_all(db)
                    actions.append("टेंडर शिकारी पुन्हा चालवला")
                except Exception as exc:
                    logger.error("copilot hunter rerun failed: %s", type(exc).__name__)
            status, msg = check_hunter(db)
            if status != "OK":
                _alert_once(db, "hunter-problem", f"{ICON[status]} टेंडर शिकारी: {msg}\nको-पायलटने पुन्हा प्रयत्न केला; अडचण अजून आहे. स्रोत तपासा.")

        # 2) content: stuck draft -> deliver again; missing after the deadline -> lighter backup run (no video)
        post = _today_post(db)
        if post is not None and post.status == "draft" and (utcnow() - post.created_at).total_seconds() > DRAFT_STUCK_MINUTES * 60:
            try:
                content_agent.deliver(db, post)
                actions.append("अडकलेली पोस्ट पुन्हा पाठवली")
            except Exception as exc:
                logger.error("copilot redelivery failed: %s", type(exc).__name__)
        elif post is None and _hour_ist() >= s.content_hour_ist + 2:
            try:
                content_agent.generate_today(db, with_video=False)
                actions.append("बॅकअप पोस्ट (व्हिडिओशिवाय) बनवली")
            except Exception as exc:
                _alert_once(db, "content-failed", f"❌ आजची पोस्ट बनली नाही ({type(exc).__name__}). Render Logs तपासा.")

        status, msg = check_content(db)
        if status in ("WARN", "FAIL"):
            _alert_once(db, "content-problem", f"{ICON[status]} मार्केटिंग: {msg}")
    return {"actions": actions}


def daily_report_job() -> bool:
    if _hour_ist() < REPORT_HOUR_IST:
        return False
    with SessionLocal() as db:
        if not _once(db, "daily-report"):
            return False
        communication_agent.notify_admin(report_text(db))
        return True


def tick() -> dict:
    """Called every 30 minutes by the scheduler."""
    result = copilot_run()
    result["report_sent"] = daily_report_job()
    return result
