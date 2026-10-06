"""Tender discovery + historical awarded-tender ingestion from PUBLIC portals (Mahatenders / CPPP).

The scraper only reads publicly accessible HTML result tables (or saved HTML / JSON records you supply).
It does not bypass captchas or logins; portal pages that need them must be saved/exported by you and ingested.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents import logger
from config import get_settings
from database import AwardedTender

# Ordered: first match wins per column. Order matters ("awarded value" must not become "award date").
HEADER_KEYS: list[tuple[str, tuple[str, ...]]] = [
    ("estimated_cost", ("estimated", "tender value", "est. cost", "estimate", "engineer")),
    ("awarded_amount", ("awarded value", "award value", "contract value", "awarded amount", "accepted", "l1 value", "contract amount")),
    ("winner_name", ("awarded to", "winner", "successful", "contractor name", "bidder name", "vendor")),
    ("award_date", ("award date", "date of award", "aoc date", "awarded on", "aoc")),
    ("tender_ref", ("tender id", "tender ref", "reference", "tender no", "nit no", "e-tender")),
    ("department", ("department", "organisation", "organization", "office")),
    ("title", ("title", "name of work", "work", "description")),
]

DATE_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y")


def parse_amount(text: str | float | int | None) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    cleaned = re.sub(r"[^0-9.]", "", str(text).replace(",", ""))
    if cleaned.count(".") > 1 or cleaned in ("", "."):
        return None
    return float(cleaned)


def parse_date(text: str | date | None) -> date | None:
    if isinstance(text, date):
        return text
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(str(text).strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_tables(html: str, required: tuple[str, ...]) -> list[dict]:
    """Extract rows from HTML tables whose header row maps to every key in `required`."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        mapping: dict[int, str] = {}
        for idx, header in enumerate(headers):
            for key, needles in HEADER_KEYS:
                if key in mapping.values():
                    continue
                if any(n in header for n in needles):
                    mapping[idx] = key
                    break
        if not all(key in mapping.values() for key in required):
            continue
        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            record = {key: cells[idx] for idx, key in mapping.items() if idx < len(cells)}
            if record:
                out.append(record)
    return out


def normalise_record(raw: dict, source: str, source_url: str | None = None,
                     default_category: str | None = None, default_department: str | None = None) -> dict | None:
    """Convert a raw row/dict into an AwardedTender-ready record, or None if unusable."""
    estimated = parse_amount(raw.get("estimated_cost"))
    awarded = parse_amount(raw.get("awarded_amount"))
    if not estimated or not awarded or estimated <= 0 or awarded <= 0:
        return None
    title = (raw.get("title") or "").strip() or None
    winner = (raw.get("winner_name") or "").strip() or None
    ref = (raw.get("tender_ref") or "").strip()
    if not ref:
        digest = hashlib.sha1(f"{title}|{winner}|{awarded}".encode("utf-8")).hexdigest()[:12]
        ref = f"{source}-{digest}"
    return {
        "tender_ref": ref,
        "title": title,
        "department": (raw.get("department") or default_department or "").strip() or None,
        "category": (raw.get("category") or default_category or "").strip() or None,
        "district": (raw.get("district") or "").strip() or None,
        "estimated_cost": estimated,
        "awarded_amount": awarded,
        "percent_vs_estimate": round((awarded - estimated) / estimated * 100, 2),
        "winner_name": winner,
        "award_date": parse_date(raw.get("award_date")),
        "source": source,
        "source_url": raw.get("source_url") or source_url,
    }


def ingest_records(db: Session, records: list[dict]) -> dict:
    inserted = duplicates = 0
    for rec in records:
        exists = db.scalar(
            select(AwardedTender.id).where(
                AwardedTender.tender_ref == rec["tender_ref"], AwardedTender.source == rec["source"]
            )
        )
        if exists:
            duplicates += 1
            continue
        db.add(AwardedTender(**rec))
        inserted += 1
    db.commit()
    return {"inserted": inserted, "duplicates_skipped": duplicates}


def _assert_allowed_host(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    allowed = get_settings().scrape_hosts
    if urlparse(url).scheme not in ("http", "https") or not any(host == h or host.endswith("." + h) for h in allowed):
        raise ValueError(f"हा होस्ट परवानगी यादीत नाही. परवानगी असलेले: {', '.join(allowed)}")


def fetch_html(url: str) -> str:
    _assert_allowed_host(url)
    headers = {"User-Agent": "Mozilla/5.0 (TenderBotAI public-data reader)"}
    response = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.text


def ingest_awarded_from_html(db: Session, html: str, source: str, source_url: str | None = None,
                             category: str | None = None, department: str | None = None) -> dict:
    rows = parse_tables(html, required=("estimated_cost", "awarded_amount"))
    records = [r for r in (normalise_record(row, source, source_url, category, department) for row in rows) if r]
    result = ingest_records(db, records)
    result.update({"rows_found": len(rows), "usable_records": len(records)})
    logger.info("awarded ingest from %s: %s", source_url or "html", result)
    return result


def ingest_awarded_from_url(db: Session, url: str, source: str, category: str | None = None,
                            department: str | None = None) -> dict:
    return ingest_awarded_from_html(db, fetch_html(url), source, url, category, department)


def ingest_awarded_json(db: Session, items: list[dict], source: str, default_category: str | None = None) -> dict:
    records = [r for r in (normalise_record(i, source, i.get("source_url"), default_category) for i in items) if r]
    result = ingest_records(db, records)
    result.update({"received": len(items), "usable_records": len(records)})
    return result


def discover_active_tenders(url: str) -> list[dict]:
    """Read a public active-tenders listing page and return rows that expose an estimated value."""
    rows = parse_tables(fetch_html(url), required=("estimated_cost",))
    results = []
    for row in rows:
        value = parse_amount(row.get("estimated_cost"))
        if value:
            results.append({**row, "estimated_cost": value, "source_url": url})
    return results
