"""SQLAlchemy models, session handling and subscription/access rules."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Iterator

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from config import get_settings
from system_prompt import PAYWALL_MESSAGE_MR, UPGRADE_VIP_MESSAGE_MR

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_phone(raw: str) -> str:
    """Return E.164 phone (+91 assumed for 10-digit numbers). Raises ValueError if invalid."""
    cleaned = (raw or "").replace("whatsapp:", "").strip()
    digits = re.sub(r"\D", "", cleaned)
    if cleaned.startswith("+"):
        result = "+" + digits
    elif len(digits) == 10:
        result = "+91" + digits
    elif len(digits) == 12 and digits.startswith("91"):
        result = "+" + digits
    else:
        result = "+" + digits
    if not 9 <= len(result) - 1 <= 15:
        raise ValueError("अवैध फोन नंबर")
    return result


class Base(DeclarativeBase):
    pass


class Contractor(Base):
    __tablename__ = "contractors"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contractor_class: Mapped[str | None] = mapped_column(String(50), nullable=True)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    districts: Mapped[list] = mapped_column(JSON, default=list)
    annual_turnover: Mapped[float | None] = mapped_column(Float, nullable=True)
    plan: Mapped[str] = mapped_column(String(10), default="none")  # none | basic | vip
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trial_started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    documents: Mapped[list["VaultDocument"]] = relationship(back_populates="contractor", cascade="all, delete-orphan")

    def trial_day(self, now: datetime | None = None) -> int:
        now = now or utcnow()
        return (now.date() - self.trial_started_at.date()).days + 1

    def effective_plan(self, now: datetime | None = None) -> str:
        """trial | basic | vip | expired"""
        now = now or utcnow()
        if self.plan in ("basic", "vip") and (self.plan_expires_at is None or self.plan_expires_at > now):
            return self.plan
        if self.trial_day(now) <= get_settings().trial_days:
            return "trial"
        return "expired"


class Tender(Base):
    __tablename__ = "tenders"

    id: Mapped[int] = mapped_column(primary_key=True)
    tender_ref: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    department: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estimated_cost: Mapped[float] = mapped_column(Float)
    emd_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AwardedTender(Base):
    """Public, already-awarded tender results (Mahatenders / CPPP). Only source for competitor AI."""

    __tablename__ = "awarded_tenders"
    __table_args__ = (UniqueConstraint("tender_ref", "source", name="uq_awarded_ref_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tender_ref: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estimated_cost: Mapped[float] = mapped_column(Float)
    awarded_amount: Mapped[float] = mapped_column(Float)
    percent_vs_estimate: Mapped[float] = mapped_column(Float)  # negative = below estimate/SSR
    winner_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    award_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="Mahatenders")  # Mahatenders | CPPP
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class VerifiedVendor(Base):
    """Internal Verified Vendor Database. Only source for marketplace contacts and rates."""

    __tablename__ = "verified_vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100), index=True)  # JCB, crane, cement, steel, labour ...
    district: Mapped[str] = mapped_column(String(100), index=True)
    phone: Mapped[str] = mapped_column(String(20))
    rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    rate_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_verified_on: Mapped[date] = mapped_column(Date)
    verified_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class VaultDocument(Base):
    __tablename__ = "vault_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    contractor_id: Mapped[int] = mapped_column(ForeignKey("contractors.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(150))
    doc_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    file_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_alert_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    contractor: Mapped[Contractor] = relationship(back_populates="documents")


class PaymentBill(Base):
    __tablename__ = "payment_bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    contractor_id: Mapped[int] = mapped_column(ForeignKey("contractors.id"), index=True)
    department: Mapped[str] = mapped_column(String(300))
    work_name: Mapped[str] = mapped_column(Text)
    work_order_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bill_no: Mapped[str] = mapped_column(String(100))
    bill_amount: Mapped[float] = mapped_column(Float)
    bill_submitted_on: Mapped[date] = mapped_column(Date)
    desk_trail: Mapped[list] = mapped_column(JSON, default=list)
    last_notice_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notices_sent: Mapped[int] = mapped_column(Integer, default=0)


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    contractor_id: Mapped[int] = mapped_column(ForeignKey("contractors.id"), index=True)
    tender_ref: Mapped[str] = mapped_column(String(120))
    tender_title: Mapped[str] = mapped_column(Text)
    bid_amount: Mapped[float] = mapped_column(Float)
    # PENDING | CANCELLED | APPROVED_AWAITING_PORTAL_SUBMISSION | SUBMITTED | APPROVED_SUBMISSION_FAILED
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    decision_channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    whatsapp_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    call_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------- access rules
ALWAYS_OPEN_FEATURES = {"analyze", "tax_draft"}
BASIC_FEATURES = ALWAYS_OPEN_FEATURES | {"alerts", "vault", "tax_export"}
# VIP-only (also locked after trial without a plan): predict_bid, submit, voice, bg_emd,
# marketplace, payment_notice


def check_access(contractor: Contractor, feature: str) -> tuple[bool, str]:
    """Return (allowed, Marathi message when blocked)."""
    plan = contractor.effective_plan()
    if plan in ("trial", "vip"):
        return True, ""
    if plan == "basic":
        return (True, "") if feature in BASIC_FEATURES else (False, UPGRADE_VIP_MESSAGE_MR)
    # expired trial, no active paid plan
    return (True, "") if feature in ALWAYS_OPEN_FEATURES else (False, PAYWALL_MESSAGE_MR)


# ---------------------------------------------------------------- helpers
def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_or_create_contractor(db: Session, phone: str, **profile) -> Contractor:
    """Fetch contractor by phone (creating it, and starting the free trial, on first contact)."""
    phone = normalize_phone(phone)
    contractor = db.scalar(select(Contractor).where(Contractor.phone == phone))
    if contractor is None:
        contractor = Contractor(phone=phone, categories=[], districts=[])
        db.add(contractor)
    for key, value in profile.items():
        if value not in (None, [], ""):
            setattr(contractor, key, value)
    db.commit()
    db.refresh(contractor)
    return contractor
