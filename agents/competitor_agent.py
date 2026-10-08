"""Competitor AI & L1 rate prediction.

STRICT DATA RULE: uses ONLY public already-awarded tender results stored in AwardedTender
(Mahatenders / CPPP). If there are not enough samples it answers "जुना डेटा उपलब्ध नाही" — never guesses.
Percentages are relative to the tender's estimated cost (SSR-based estimate): negative = below, positive = above.
"""
from __future__ import annotations

import statistics
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents import format_inr, llm_available, llm_text, logger
from config import get_settings
from database import AwardedTender
from system_prompt import MASTER_SYSTEM_PROMPT, OLD_DATA_MSG_MR


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct / 100
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def _describe(pct: float) -> str:
    if pct < 0:
        return f"SSR/अंदाजित दरापेक्षा {abs(pct):.1f}% कमी"
    if pct > 0:
        return f"SSR/अंदाजित दरापेक्षा {pct:.1f}% जास्त"
    return "SSR/अंदाजित दराइतका"


def _describe_en(pct: float) -> str:
    if pct < 0:
        return f"{abs(pct):.1f}% below the estimate (SSR)"
    if pct > 0:
        return f"{pct:.1f}% above the estimate (SSR)"
    return "equal to the estimate (SSR)"


def _fetch(db: Session, category: str, department: str | None) -> tuple[list[AwardedTender], str]:
    base = select(AwardedTender).where(func.lower(AwardedTender.category).like(f"%{category.lower().strip()}%"))
    min_samples = get_settings().min_history_samples
    if department:
        rows = list(db.scalars(base.where(func.lower(AwardedTender.department).like(f"%{department.lower().strip()}%"))))
        if len(rows) >= min_samples:
            return rows, "विभाग + श्रेणी"
    return list(db.scalars(base)), "श्रेणी"


def predict_l1(db: Session, category: str, department: str | None, estimated_cost: float,
               own_cost_estimate: float | None = None) -> dict:
    min_samples = get_settings().min_history_samples
    rows, scope = _fetch(db, category, department)

    # Prefer similar-size tenders when that still leaves enough samples.
    banded = [r for r in rows if 0.5 * estimated_cost <= r.estimated_cost <= 2 * estimated_cost]
    if len(banded) >= min_samples:
        rows, scope = banded, scope + " + समान किमतीची रेंज (०.५x–२x)"

    if len(rows) < min_samples:
        return {
            "data_available": False,
            "samples_found": len(rows),
            "minimum_samples_required": min_samples,
            "message_mr": OLD_DATA_MSG_MR,
        }

    pcts = [r.percent_vs_estimate for r in rows]
    median = round(statistics.median(pcts), 2)
    aggressive = round(percentile(pcts, 25), 2)   # lower (more below SSR) = more aggressive
    conservative = round(percentile(pcts, 75), 2)
    dated = [r.award_date for r in rows if r.award_date]

    def bid_for(p: float) -> float:
        return round(estimated_cost * (1 + p / 100), 2)

    scenarios = {}
    for label, p in (("aggressive", aggressive), ("recommended", median), ("conservative", conservative)):
        item = {"percent_vs_estimate": p, "bid_amount": bid_for(p), "description_mr": _describe(p)}
        if own_cost_estimate:
            amount = bid_for(p)
            item["profit_amount"] = round(amount - own_cost_estimate, 2)
            item["profit_margin_percent"] = round((amount - own_cost_estimate) / amount * 100, 2)
        scenarios[label] = item

    winners = Counter(r.winner_name for r in rows if r.winner_name).most_common(5)
    result = {
        "data_available": True,
        "predicted_l1_percent": median,
        "predicted_l1_description_mr": _describe(median),
        "scenarios": scenarios,
        "data_basis": {
            "samples": len(rows),
            "match_scope": scope,
            "sources": sorted({r.source for r in rows}),
            "award_date_range": [min(dated).isoformat(), max(dated).isoformat()] if dated else None,
            "winning_percent_min": round(min(pcts), 2),
            "winning_percent_max": round(max(pcts), 2),
        },
        "frequent_winners": [{"name": n, "wins": c} for n, c in winners],
        "warnings_mr": [],
        "warnings_en": [],
    }

    if own_cost_estimate:
        breakeven = round((own_cost_estimate / estimated_cost - 1) * 100, 2)
        result["breakeven_percent_vs_estimate"] = breakeven
        if median < breakeven:
            result["warnings_mr"].append(
                f"सावधान: अंदाजे L1 ({median:+.1f}%) तुमच्या ब्रेक-इव्हन ({breakeven:+.1f}%) पेक्षा कमी आहे — "
                "या दराने बिड भरल्यास तोटा होईल."
            )
            result["warnings_en"].append(
                f"Warning: the predicted L1 ({median:+.1f}%) is below your break-even ({breakeven:+.1f}%) — bidding at this rate would make a loss."
            )
    result["narrative_mr"] = _narrative(result, estimated_cost, own_cost_estimate)
    en = (f"Across {len(rows)} past public awards ({', '.join(result['data_basis']['sources'])}), winning bids were about "
          f"{_describe_en(median)} (predicted L1: {median:+.1f}%). At this rate the bid is ≈ "
          f"{format_inr(result['scenarios']['recommended']['bid_amount'])}.")
    margin = result["scenarios"]["recommended"].get("profit_margin_percent")
    if margin is not None:
        en += f" Based on your cost estimate, the profit margin is ≈ {margin:.1f}%."
    result["narrative_en"] = en
    return result


def _narrative(result: dict, estimated_cost: float, own_cost: float | None) -> str:
    basis = result["data_basis"]
    base = (
        f"मागील {basis['samples']} सार्वजनिक अवार्ड्सनुसार ({', '.join(basis['sources'])}) विजेती बोली साधारण "
        f"{result['predicted_l1_description_mr']} राहिली आहे (अंदाजे L1: {result['predicted_l1_percent']:+.1f}%). "
        f"या दराने बिड रक्कम ≈ {format_inr(result['scenarios']['recommended']['bid_amount'])}."
    )
    if own_cost is not None:
        margin = result["scenarios"]["recommended"].get("profit_margin_percent")
        if margin is not None:
            base += f" तुमच्या खर्च अंदाजानुसार नफा मार्जिन ≈ {margin:.1f}%."
    if not llm_available():
        return base
    try:
        system = (
            MASTER_SYSTEM_PROMPT
            + "\nफक्त खाली दिलेले आकडे वापरून २-३ वाक्यांचा मराठी सारांश लिही. नवीन कोणताही आकडा किंवा नाव जोडू नकोस."
        )
        return llm_text(system, base)
    except Exception as exc:  # fall back to the deterministic text
        logger.warning("narrative LLM failed: %s", exc)
        return base
