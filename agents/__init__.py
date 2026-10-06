"""Shared helpers for all TenderBot agents (LLM access, formatting)."""
from __future__ import annotations

import json
import logging
from datetime import date

from config import get_settings

logger = logging.getLogger("tenderbot")


class LLMUnavailable(RuntimeError):
    """Raised when GPT-4o is requested but OPENAI_API_KEY is not configured."""


def llm_available() -> bool:
    return bool(get_settings().openai_api_key.strip())


def _chat(json_mode: bool):
    if not llm_available():
        raise LLMUnavailable("OPENAI_API_KEY सेट केलेली नाही.")
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
        timeout=60,
        max_retries=2,
    )
    return llm.bind(response_format={"type": "json_object"}) if json_mode else llm


def llm_text(system: str, user: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    response = _chat(False).invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return str(response.content).strip()


def llm_json(system: str, user: str) -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage

    response = _chat(True).invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return json.loads(str(response.content))


def format_inr(amount: float | int | None) -> str:
    """Format a number with Indian digit grouping, e.g. 12,34,567.50 with the rupee sign."""
    if amount is None:
        return "—"
    value = round(float(amount), 2)
    negative = value < 0
    value = abs(value)
    whole = int(value)
    paise = int(round((value - whole) * 100))
    digits = str(whole)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    if paise:
        digits += f".{paise:02d}"
    return ("-" if negative else "") + "₹" + digits


def fmt_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"
