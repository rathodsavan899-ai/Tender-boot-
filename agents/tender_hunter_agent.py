"""Tender Hunter: reads public tender listing pages on a schedule and saves NEW tenders.

- Sources are rows in `tender_sources` (url may contain {page}; optional backup_url, state_filter, keywords).
- If the main URL fails or yields nothing, the backup URL is tried; 3 failures in a row mark the source "down".
- Only allow-listed public hosts are read (ALLOWED_SCRAPE_HOSTS). Pages that need a captcha/login cannot be read.
"""
from __future__ import annotations

import time
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents import communication_agent, logger, scraper_agent
from database import SessionLocal, Tender, TenderSource, utcnow

DEFAULT_SOURCE = {
    "name": "CPPP - महाराष्ट्र (सिव्हिल)",
    "url": "https://eprocure.gov.in/cppp/latestactivetendersnew/mmpdata?page={page}",
    "category": "civil",
    "state_filter": "Maharashtra",
    "keywords": "road,bridge,building,construction,drain,culvert,pipeline,water supply,repair,renovation,"
                "maintenance,compound wall,pavement,paver,school,hostel,tank,canal,embankment",
    "max_pages": 20,
}
_notified: dict[tuple[int, str], date] = {}
PAGE_PAUSE_SECONDS = 0.7
MAX_RUN_SECONDS = 150
DOWN_AFTER_FAILURES = 3


def seed_default_sources() -> None:
    """On first start (no sources yet) add the default Maharashtra civil-tender source."""
    with SessionLocal() as db:
        if db.scalar(select(TenderSource.id).limit(1)) is None:
            db.add(TenderSource(**DEFAULT_SOURCE))
            db.commit()
            logger.info("seeded default tender source")


def _fetch(url: str) -> str:
    """Download with 3 tries (transient errors are common on busy government sites)."""
    last: Exception | None = None
    for attempt in range(3):
        try:
            return scraper_agent.fetch_html(url)
        except ValueError:
            raise                      # host not allowed -> retrying is pointless
        except Exception as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def _alert_once_a_day(source: TenderSource, kind: str, text: str) -> None:
    key = (source.id, kind)
    if _notified.get(key) != date.today():
        _notified[key] = date.today()
        communication_agent.notify_admin(text)


def _keywords(source: TenderSource) -> list[str]:
    return [k.strip().lower() for k in (source.keywords or "").split(",") if k.strip()]


def _keep(rec: dict, source: TenderSource, kws: list[str], today: date) -> bool:
    if source.state_filter and source.state_filter.strip().lower() not in (rec["state"] or "").lower():
        return False
    if kws and not any(k in rec["title"].lower() for k in kws):
        return False
    return not (rec["closing_date"] and rec["closing_date"] < today)


def _crawl_url(db: Session, source: TenderSource, url_template: str) -> dict:
    """Walk the pages of one URL. Newest-first listings stop as soon as a page holds nothing new."""
    paged = "{page}" in url_template
    pages = range(1, max(source.max_pages, 1) + 1) if paged else range(1, 2)
    kws, today, started = _keywords(source), date.today(), time.time()
    found = new = 0
    for page in pages:
        url = url_template.replace("{page}", str(page))
        records = scraper_agent.parse_tender_listing(_fetch(url))
        if not records:
            break
        found += len(records)
        refs = [r["tender_ref"] for r in records]
        known = set(db.scalars(select(Tender.tender_ref).where(Tender.tender_ref.in_(refs))))
        fresh = [r for r in records if r["tender_ref"] not in known]
        for rec in fresh:
            if _keep(rec, source, kws, today):
                db.add(Tender(tender_ref=rec["tender_ref"], title=rec["title"], department=rec["department"],
                              category=source.category or "general", district=source.district,
                              estimated_cost=rec["estimated_cost"], closing_date=rec["closing_date"], state=rec["state"] or None,
                              source_url=url[:500]))
                new += 1
        db.commit()
        if paged and not fresh:        # everything on this page was already known -> we are caught up
            break
        if time.time() - started > MAX_RUN_SECONDS:
            break
        if paged:
            time.sleep(PAGE_PAUSE_SECONDS)
    return {"found": found, "new": new}


def crawl_source(db: Session, source: TenderSource) -> dict:
    attempts = [("main", source.url)] + ([("backup", source.backup_url)] if source.backup_url else [])
    error = "no_rows"
    result: dict | None = None
    used = None
    for label, url in attempts:
        try:
            outcome = _crawl_url(db, source, url)
            if outcome["found"] > 0:
                result, used = outcome, label
                break
            error = "no_rows (page opened but no tender table was recognised)"
        except Exception as exc:
            db.rollback()
            error = f"{type(exc).__name__}: {str(exc)[:150]}"
            logger.warning("tender source %s (%s) failed: %s", source.name, label, error)

    previous_status = source.status
    source.last_run_at = utcnow()
    if result is not None:
        source.status, source.consecutive_failures, source.last_error = "ok", 0, None
        source.last_ok_at = source.last_run_at
        source.last_found, source.last_new = result["found"], result["new"]
        source.total_new = (source.total_new or 0) + result["new"]
    else:
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        source.last_error = error[:300]
        source.last_found = source.last_new = 0
        source.status = "down" if source.consecutive_failures >= DOWN_AFTER_FAILURES else source.status
    db.commit()
    if result is None and source.status == "down" and previous_status != "down":
        communication_agent.notify_admin(f"⚠️ टेंडर स्रोत बंद: {source.name}\nकारण: {source.last_error}\n"
                                         "बॅकअप लिंक नसेल तर या स्रोताचे नवे टेंडर येत नाहीत.")
    elif result is not None and previous_status == "down":
        communication_agent.notify_admin(f"✅ टेंडर स्रोत पुन्हा चालू: {source.name}")
    if result is not None and used == "backup":
        _alert_once_a_day(source, "backup", f"ℹ️ {source.name}: मुख्य लिंक चालत नाही, बॅकअप लिंक वापरली जात आहे.")
    return {"source": source.name, "ok": result is not None, "used": used, "status": source.status,
            "found": source.last_found, "new": source.last_new, "error": source.last_error}


def run_all(db: Session) -> list[dict]:
    results = []
    for source in db.scalars(select(TenderSource).where(TenderSource.enabled.is_(True))):
        results.append(crawl_source(db, source))
    new_total = sum(r["new"] for r in results)
    if new_total:
        lines = [f"• {r['source']}: {r['new']}" for r in results if r["new"]]
        communication_agent.notify_admin(f"🆕 {new_total} नवे टेंडर सापडले\n" + "\n".join(lines))
    return results


def run_job() -> list[dict]:
    """Entry point for the scheduler / background task (own DB session)."""
    with SessionLocal() as db:
        results = run_all(db)
    logger.info("tender hunter run: %s", results)
    return results
