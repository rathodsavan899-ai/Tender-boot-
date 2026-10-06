"""Payment delay tracking across department desks + formal Marathi follow-up letter generator."""
from __future__ import annotations

from datetime import date, timedelta

from agents import fmt_date, format_inr
from database import PaymentBill


def delay_days(bill_submitted_on: date, today: date | None = None) -> int:
    return max(((today or date.today()) - bill_submitted_on).days, 0)


def escalation_level(days: int) -> tuple[int, str]:
    if days < 30:
        return 1, "पहिले स्मरणपत्र"
    if days < 60:
        return 2, "दुसरे स्मरणपत्र"
    return 3, "अंतिम स्मरणपत्र / नोटीस"


def desk_summary(desk_trail: list[dict], today: date | None = None) -> tuple[str | None, list[str]]:
    """Return (current desk, human readable lines) from the recorded desk trail."""
    today = today or date.today()
    lines: list[str] = []
    entries = sorted(desk_trail, key=lambda e: e.get("received_on") or "")
    for i, entry in enumerate(entries):
        start = date.fromisoformat(entry["received_on"]) if entry.get("received_on") else None
        end = date.fromisoformat(entries[i + 1]["received_on"]) if i + 1 < len(entries) and entries[i + 1].get("received_on") else today
        held = f" — {max((end - start).days, 0)} दिवस" if start else ""
        remark = f" ({entry['remarks']})" if entry.get("remarks") else ""
        lines.append(f"{i + 1}. {entry['desk']}: {fmt_date(start)} पासून{held}{remark}")
    return (entries[-1]["desk"] if entries else None), lines


def generate_notice(bill: PaymentBill, contractor_name: str, officer_designation: str,
                    office_address: str | None, today: date | None = None) -> dict:
    today = today or date.today()
    days = delay_days(bill.bill_submitted_on, today)
    level, label = escalation_level(days)
    current_desk, trail_lines = desk_summary(bill.desk_trail or [], today)

    parts = [
        "प्रति,",
        f"{officer_designation},",
        f"{bill.department}" + (f",\n{office_address}" if office_address else ""),
        "",
        f"दिनांक: {fmt_date(today)}",
        "",
        f"विषय: {bill.work_name} — देयक क्र. {bill.bill_no} (रक्कम {format_inr(bill.bill_amount)}) चे प्रलंबित देयक अदा करणेबाबत — {label}",
    ]
    if bill.work_order_no:
        parts.append(f"संदर्भ: कार्यारंभ आदेश क्र. {bill.work_order_no}")
    parts += [
        "",
        "महोदय,",
        "",
        f"उपरोक्त विषयाच्या संदर्भात आमच्या {contractor_name} या फर्मने '{bill.work_name}' या कामाचे देयक क्र. {bill.bill_no}, "
        f"रक्कम {format_inr(bill.bill_amount)}, दिनांक {fmt_date(bill.bill_submitted_on)} रोजी आपल्या कार्यालयात सादर केले आहे. "
        f"आजपर्यंत {days} दिवस उलटूनही सदर देयकाची रक्कम अदा करण्यात आलेली नाही.",
    ]
    if trail_lines:
        parts += ["", "देयकाचा आतापर्यंतचा प्रवास (टेबलनिहाय):"] + trail_lines
        if current_desk:
            parts.append(f"सध्या देयक '{current_desk}' येथे प्रलंबित असल्याचे आमच्या नोंदीनुसार दिसते.")
    closing = {
        1: "तरी सदर देयकाची कार्यवाही तातडीने पूर्ण करून रक्कम लवकरात लवकर अदा करावी, ही नम्र विनंती.",
        2: "यापूर्वीही आम्ही विनंती केली असून अद्याप कार्यवाही न झाल्याने आर्थिक अडचण निर्माण झाली आहे. "
           "तरी सदर देयक तातडीने मंजूर करून रक्कम अदा करावी, ही विनंती.",
        3: "वारंवार विनंती करूनही देयक अदा न झाल्याने आमच्या कामकाजावर गंभीर परिणाम होत आहे. "
           "सदर देयक ७ दिवसांत अदा न झाल्यास, कराराच्या अटींनुसार आणि उपलब्ध कायदेशीर मार्गांनी पुढील कार्यवाही करण्यास आम्हाला भाग पडेल, याची कृपया नोंद घ्यावी.",
    }[level]
    parts += ["", closing, "", "धन्यवाद.", "", "आपला विश्वासू,", contractor_name, "(अधिकृत स्वाक्षरी व शिक्का)",
              "", "सोबत: देयकाची प्रत व पोचपावती"]
    return {
        "delay_days": days,
        "escalation_level": level,
        "escalation_label": label,
        "current_desk": current_desk,
        "desk_trail_summary": trail_lines,
        "notice_mr": "\n".join(parts),
        "suggested_next_followup_on": (today + timedelta(days=7 if level == 3 else 15)).isoformat(),
    }
