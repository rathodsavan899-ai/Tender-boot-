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

from agents import communication_agent, content_agent, logger, meta_agent, tender_hunter_agent
from config import get_settings
from database import AgentEvent, ContentPost, ContentVideo, SessionLocal, Tender, TenderSource, utcnow

HUNTER_STALE_HOURS = 8
RERUN_PAUSE_MINUTES = 60
DRAFT_STUCK_MINUTES = 15
REPORT_HOUR_IST = 21
PING_FRESH_MINUTES = 20
ICON = {"OK": "✅", "WARN": "⚠️", "FAIL": "❌", "NA": "➖"}
LANGS = (("mr", "मराठी"), ("en", "English"))

_last_ping: datetime | None = None


def note_ping() -> None:
    """Called by /ping (the uptime pinger). Lets the report show whether the 'never sleep' ping really arrives."""
    global _last_ping
    _last_ping = utcnow()


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


def _today_posts(db: Session) -> dict[str, ContentPost]:
    """Today's real post per language (the owner's manual /poster test posts are ignored)."""
    rows = db.scalars(select(ContentPost).where(ContentPost.post_date == content_agent.ist_today(),
                                                ContentPost.status != "test").order_by(ContentPost.id.desc()))
    out: dict[str, ContentPost] = {}
    for post in rows:
        out.setdefault(post.lang or "mr", post)
    return out


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
    posts = _today_posts(db)
    missing = [label for code, label in LANGS if code not in posts]
    if missing:
        hour = _hour_ist()
        if hour >= s.content_hour_ist + 2:
            return "FAIL", "आजची पोस्ट बनली नाही: " + ", ".join(missing)
        if hour >= s.content_hour_ist:
            return "WARN", "आजची पोस्ट बनत आहे / उशीर: " + ", ".join(missing)
        return "OK", f"सकाळी {s.content_hour_ist}:00 ला बनेल"
    parts, problems = [], []
    for code, label in LANGS:
        post = posts[code]
        try:
            delivery = json.loads(post.delivery or "{}")
        except ValueError:
            delivery = {}
        state = {"posted": "प्रकाशित", "scheduled": "वेळेवर प्रकाशनासाठी तयार", "sent": "Telegram वर", "draft": "तयार"}.get(post.status, post.status)
        parts.append(f"{label}: पोस्टर {'✔' if post.poster_png else '✘'} ({state})")
        age = (utcnow() - post.created_at).total_seconds()
        if post.status == "draft" and age > DRAFT_STUCK_MINUTES * 60:
            problems.append(f"{label} पोस्ट तयार झाली पण पाठवली गेली नाही")
        if post.status == "scheduled" and post.publish_after and (utcnow() - post.publish_after).total_seconds() > DRAFT_STUCK_MINUTES * 60:
            problems.append(f"{label} प्रकाशन उशीर")
        if not (delivery.get("telegram_text") or {}).get("sent"):
            problems.append(f"{label}: Telegram वर पोहोचली नाही")
        for name in ("facebook", "instagram"):
            result = delivery.get(name)
            if isinstance(result, dict) and not result.get("ok"):
                problems.append(f"{label} {name}: {result.get('error', 'अयशस्वी')}")
        if delivery.get("honesty_blocked"):
            problems.append(f"{label}: दिशाभूल-तपासणीने सोशल पोस्टिंग थांबवली")
    marathi = posts["mr"]
    has_video = db.scalar(select(ContentVideo.id).where(ContentVideo.post_id == marathi.id)) is not None
    parts.append("व्हिडिओ ✔" if has_video else "व्हिडिओ ✘")
    return ("WARN" if problems else "OK"), " · ".join(parts + problems)


def check_meta() -> tuple[str, str]:
    info = meta_agent.health()
    if not info.get("connected"):
        return "NA", "Facebook/Instagram जोडलेले नाही (/admin/meta/connect)"
    if info.get("valid") is False:
        return "FAIL", "टोकन अवैध किंवा संपले: पुन्हा जोडा"
    if info.get("missing_scopes"):
        return "WARN", "परवानग्या कमी: " + ", ".join(info["missing_scopes"])
    if not info.get("instagram_id"):
        return "WARN", f"Page '{info.get('page_name')}' जोडले, पण Instagram Professional अकाउंट जोडलेले नाही"
    return "OK", f"Page '{info.get('page_name')}' आणि Instagram जोडले"


def check_uptime() -> tuple[str, str]:
    if _last_ping is None:
        return "WARN", "अजून एकही uptime पिंग मिळाला नाही; फुकट सर्व्हर झोपू शकतो (GitHub keep-alive तपासा)"
    minutes = int((utcnow() - _last_ping).total_seconds() / 60)
    if minutes > PING_FRESH_MINUTES:
        return "WARN", f"शेवटचा पिंग {minutes} मिनिटांपूर्वी; सर्व्हर झोपू शकतो"
    return "OK", f"शेवटचा पिंग {minutes} मिनिटांपूर्वी"


def collect(db: Session) -> list[tuple[str, str, str]]:
    return [
        ("टेंडर शिकारी (Lead Hunter)", *check_hunter(db)),
        ("मार्केटिंग: मराठी + English पोस्टर, व्हिडिओ", *check_content(db)),
        ("Facebook / Instagram कनेक्शन", *check_meta()),
        ("सर्व्हर जागा ठेवणे (uptime पिंग)", *check_uptime()),
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

        # 2) content: publish what is due, re-send stuck posts, and make a missing post with a lighter backup (no video)
        try:
            due = content_agent.publish_due(db)
            if due:
                actions.append("वेळ झालेली पोस्ट प्रकाशित केली")
        except Exception as exc:
            logger.error("copilot publish_due failed: %s", type(exc).__name__)
        posts = _today_posts(db)
        for post in posts.values():
            if post.status == "draft" and (utcnow() - post.created_at).total_seconds() > DRAFT_STUCK_MINUTES * 60:
                try:
                    content_agent.deliver(db, post)
                    actions.append("अडकलेली पोस्ट पुन्हा पाठवली")
                except Exception as exc:
                    logger.error("copilot redelivery failed: %s", type(exc).__name__)
        if _hour_ist() >= s.content_hour_ist + 2:
            for code, label in LANGS:
                if code not in posts:
                    try:
                        content_agent.generate_today(db, with_video=False, lang=code)
                        actions.append(f"बॅकअप पोस्ट ({label}, व्हिडिओशिवाय) बनवली")
                    except Exception as exc:
                        db.rollback()
                        _alert_once(db, f"content-failed-{code}", f"❌ आजची {label} पोस्ट बनली नाही ({type(exc).__name__}). Render Logs तपासा.")
        status, msg = check_content(db)
        if status in ("WARN", "FAIL"):
            _alert_once(db, "content-problem", f"{ICON[status]} मार्केटिंग: {msg}")

        # 3) Facebook/Instagram token health (once a day alert)
        try:
            status, msg = check_meta()
            if status in ("FAIL", "WARN"):
                _alert_once(db, "meta-problem", f"{ICON[status]} Facebook/Instagram: {msg}")
        except Exception as exc:
            logger.error("meta health check failed: %s", type(exc).__name__)
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
