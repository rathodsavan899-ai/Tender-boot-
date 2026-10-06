"""Sub-contractor / material / labour marketplace.

STRICT DATA RULE: contacts and rates come ONLY from the Internal Verified Vendor Database (VerifiedVendor).
If nothing matches, say so — never invent a vendor, number or rate.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents import format_inr
from database import VerifiedVendor
from system_prompt import NO_VENDOR_MSG_MR


def search_vendors(db: Session, category: str, district: str | None = None, limit: int = 10) -> dict:
    stmt = select(VerifiedVendor).where(func.lower(VerifiedVendor.category).like(f"%{category.lower().strip()}%"))
    if district:
        stmt = stmt.where(func.lower(VerifiedVendor.district) == district.lower().strip())
    vendors = list(db.scalars(stmt.order_by(VerifiedVendor.last_verified_on.desc()).limit(limit)))
    if not vendors:
        return {"found": 0, "vendors": [], "message_mr": NO_VENDOR_MSG_MR, "source": "Internal Verified Vendor Database"}
    items = []
    for v in vendors:
        rate_text = f"{format_inr(v.rate)}" + (f" / {v.rate_unit}" if v.rate_unit else "") if v.rate is not None else None
        items.append({
            "name": v.name, "category": v.category, "district": v.district, "phone": v.phone,
            "rate": v.rate, "rate_text": rate_text, "last_verified_on": v.last_verified_on.isoformat(),
        })
    return {"found": len(items), "vendors": items, "source": "Internal Verified Vendor Database"}


def add_vendor(db: Session, name: str, category: str, district: str, phone: str, rate: float | None,
               rate_unit: str | None, verified_by: str | None, last_verified_on: date | None = None) -> VerifiedVendor:
    vendor = VerifiedVendor(
        name=name, category=category, district=district, phone=phone, rate=rate, rate_unit=rate_unit,
        verified_by=verified_by, last_verified_on=last_verified_on or date.today(),
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return vendor
