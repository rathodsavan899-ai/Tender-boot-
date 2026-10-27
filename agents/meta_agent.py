"""Facebook Page + Instagram connection: exchange a token, store the Page token encrypted, check its health.

Setup is done once from the phone: get a short-lived user token in Graph API Explorer, send it to /admin/meta/connect.
The server exchanges it for a long-lived one, finds the Page and the linked Instagram account and keeps the Page token
(which does not expire while the permissions stay valid) encrypted in the database. Tokens are never logged or returned.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import httpx
from sqlalchemy import select

from agents import logger, vault_agent
from config import get_settings
from database import MetaConnection, SessionLocal, utcnow

logging.getLogger("httpx").setLevel(logging.WARNING)   # request URLs can contain tokens
REQUIRED_SCOPES = ["pages_manage_posts", "instagram_content_publish"]


def _g(path: str) -> str:
    return f"https://graph.facebook.com/{get_settings().meta_graph_version}/{path}"


def _err(data: dict) -> str:
    return str((data.get("error") or {}).get("message", ""))[:200]


def credentials() -> SimpleNamespace:
    """Page id / Page token / Instagram id from the database (preferred) or from the environment."""
    s = get_settings()
    try:
        with SessionLocal() as db:
            row = db.scalar(select(MetaConnection).order_by(MetaConnection.id.desc()))
            if row is not None:
                token = vault_agent._fernet().decrypt(row.page_token_enc.encode("utf-8")).decode("utf-8")
                return SimpleNamespace(facebook_page_id=row.page_id, facebook_page_token=token,
                                       instagram_business_id=row.instagram_id or "", page_name=row.page_name, source="database")
    except Exception as exc:
        logger.warning("meta credentials not read from database: %s", type(exc).__name__)
    return SimpleNamespace(facebook_page_id=s.facebook_page_id, facebook_page_token=s.facebook_page_token,
                           instagram_business_id=s.instagram_business_id, page_name=None, source="environment")


def connect(user_token: str, page_id: str | None = None) -> dict:
    s = get_settings()
    if not (s.meta_app_id and s.meta_app_secret):
        return {"ok": False, "error": "Render मध्ये META_APP_ID आणि META_APP_SECRET सेट करा"}
    try:
        exchanged = httpx.get(_g("oauth/access_token"), timeout=30, params={
            "grant_type": "fb_exchange_token", "client_id": s.meta_app_id, "client_secret": s.meta_app_secret,
            "fb_exchange_token": user_token}).json()
        long_token = exchanged.get("access_token")
        if not long_token:
            return {"ok": False, "error": _err(exchanged) or "टोकन बदलता आले नाही"}
        accounts = httpx.get(_g("me/accounts"), timeout=30, params={
            "fields": "name,instagram_business_account,access_token", "access_token": long_token}).json()
        pages = accounts.get("data") or []
        if not pages:
            return {"ok": False, "error": _err(accounts) or "कोणतेही Facebook Page सापडले नाही (pages_show_list परवानगी तपासा)"}
        page = next((p for p in pages if p.get("id") == page_id), None) if page_id else (pages[0] if len(pages) == 1 else None)
        if page is None:
            return {"ok": False, "error": "एकापेक्षा जास्त Pages आहेत; page_id द्या",
                    "pages": [{"id": p.get("id"), "name": p.get("name")} for p in pages]}
        instagram_id = (page.get("instagram_business_account") or {}).get("id")
        encrypted = vault_agent._fernet().encrypt(page["access_token"].encode("utf-8")).decode("utf-8")
        with SessionLocal() as db:
            db.add(MetaConnection(page_id=page["id"], page_name=page.get("name"), instagram_id=instagram_id,
                                  page_token_enc=encrypted))
            db.commit()
        return {"ok": True, "page": {"id": page["id"], "name": page.get("name")}, "instagram_id": instagram_id,
                "instagram_linked": bool(instagram_id),
                "note": None if instagram_id else "या Page ला Instagram Professional अकाउंट जोडलेले नाही"}
    except Exception as exc:
        logger.error("meta connect failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}


def health() -> dict:
    """Is the stored Page token valid, and does it carry the permissions we need?"""
    s = get_settings()
    cred = credentials()
    if not cred.facebook_page_token:
        return {"connected": False}
    out = {"connected": True, "source": cred.source, "page_id": cred.facebook_page_id, "page_name": cred.page_name,
           "instagram_id": cred.instagram_business_id or None}
    try:
        if s.meta_app_id and s.meta_app_secret:
            data = httpx.get(_g("debug_token"), timeout=30, params={
                "input_token": cred.facebook_page_token, "access_token": f"{s.meta_app_id}|{s.meta_app_secret}"}).json().get("data", {})
            scopes = data.get("scopes") or []
            out.update(valid=bool(data.get("is_valid")), scopes=scopes,
                       missing_scopes=[x for x in REQUIRED_SCOPES if x not in scopes],
                       expires_at=data.get("expires_at") or None)
        else:
            check = httpx.get(_g("me"), timeout=30, params={"access_token": cred.facebook_page_token})
            out.update(valid=check.status_code == 200, scopes=None, missing_scopes=[])
    except Exception as exc:
        out.update(valid=False, error=type(exc).__name__)
    return out
