"""Eligibility analysis: required-document gap check, class/turnover checks, WhatsApp alert text."""
from __future__ import annotations

import re

from agents import format_inr, llm_json

ALIAS_TOKENS: dict[str, set[str]] = {
    "aadhaar": {"aadhaar", "aadhar", "uidai"},
    "gst": {"gst", "gstin"},
    "pan": {"pan"},
    "epf": {"epf", "pf", "provident"},
    "esic": {"esic", "esi"},
    "pwd": {"pwd", "enlistment", "mpwd"},
    "itr": {"itr"},
    "solvency": {"solvency"},
    "turnover": {"turnover"},
    "labour": {"labour", "labor"},
    "udyam": {"udyam", "msme"},
    "dsc": {"dsc"},
    "profession_tax": {"ptrc", "professional"},
}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7}

EXTRACTION_SYSTEM_PROMPT = (
    "You extract eligibility requirements from Indian government tender text (may be Marathi or English). "
    "Return ONLY a JSON object with keys: required_documents (list of short document names), "
    "minimum_class (string or null), min_turnover (number in INR or null), emd_amount (number in INR or null). "
    "Extract ONLY what is explicitly written in the text. Never guess. Use null or an empty list when absent."
)


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[\s,;:/()\-_.]+", text.lower()) if t}


def _canonical(doc: str) -> str | None:
    tokens = _tokens(doc)
    for key, aliases in ALIAS_TOKENS.items():
        if tokens & aliases:
            return key
    return None


def _norm(doc: str) -> str:
    return " ".join(sorted(_tokens(doc)))


def parse_class(text: str | None) -> int | None:
    """'Class 1', 'Class-I', 'वर्ग 2' -> 1, 1, 2. Lower number = higher class."""
    if not text:
        return None
    match = re.search(r"(\d+)", text)
    if match:
        number = int(match.group(1))
        return number if 1 <= number <= 9 else None
    match = re.search(r"\b(vii|vi|iii|ii|iv|v|i)\b", text.lower())
    return ROMAN.get(match.group(1)) if match else None


def extract_requirements(tender_text: str) -> dict:
    """GPT-4o extraction of eligibility requirements from raw tender text."""
    data = llm_json(EXTRACTION_SYSTEM_PROMPT, tender_text[:24000])
    return {
        "required_documents": [str(d).strip() for d in (data.get("required_documents") or []) if str(d).strip()],
        "minimum_class": data.get("minimum_class"),
        "min_turnover": data.get("min_turnover"),
        "emd_amount": data.get("emd_amount"),
    }


def gap_analysis(required_documents: list[str], documents_held: list[str], contractor_class: str | None,
                 minimum_class: str | None, annual_turnover: float | None, min_turnover: float | None) -> dict:
    held_canon = {c for c in (_canonical(d) for d in documents_held) if c}
    held_norm = {_norm(d) for d in documents_held}

    matched, missing = [], []
    for doc in required_documents:
        canon = _canonical(doc)
        if (canon and canon in held_canon) or _norm(doc) in held_norm:
            matched.append(doc)
        else:
            missing.append(doc)

    issues: list[str] = []
    issues_en: list[str] = []
    unverified: list[str] = []
    unverified_en: list[str] = []

    required_class = parse_class(minimum_class)
    if minimum_class:
        have = parse_class(contractor_class)
        if required_class is None:
            unverified.append(f"किमान वर्ग '{minimum_class}' नीट समजला नाही — निविदा तपासा.")
            unverified_en.append(f"Could not understand the minimum class '{minimum_class}' — check the tender.")
        elif have is None:
            unverified.append(f"किमान वर्ग {minimum_class} आवश्यक आहे; तुमचा वर्ग प्रोफाइलमध्ये नाही.")
            unverified_en.append(f"Minimum class {minimum_class} is required; your class is not in your profile.")
        elif have > required_class:
            issues.append(f"तुमचा वर्ग ({contractor_class}) आवश्यक वर्गापेक्षा ({minimum_class}) कमी आहे.")
            issues_en.append(f"Your class ({contractor_class}) is lower than the required class ({minimum_class}).")

    if min_turnover:
        if annual_turnover is None:
            unverified.append(f"किमान उलाढाल {format_inr(min_turnover)} आवश्यक आहे; तुमची उलाढाल प्रोफाइलमध्ये नाही.")
            unverified_en.append(f"Minimum turnover {format_inr(min_turnover)} is required; your turnover is not in your profile.")
        elif annual_turnover < min_turnover:
            issues.append(f"तुमची उलाढाल {format_inr(annual_turnover)} आहे; आवश्यक किमान {format_inr(min_turnover)}.")
            issues_en.append(f"Your turnover is {format_inr(annual_turnover)}; the minimum required is {format_inr(min_turnover)}.")

    if missing or issues:
        eligible: bool | None = False
    elif unverified:
        eligible = None
    else:
        eligible = True

    return {
        "eligible": eligible,
        "matched_documents": matched,
        "missing_documents": missing,
        "issues": issues,
        "unverified": unverified,
        "issues_en": issues_en,
        "unverified_en": unverified_en,
    }


def build_whatsapp_alert(tender: dict, analysis: dict) -> str:
    lines = [
        "🏗️ *TenderBot AI — टेंडर विश्लेषण*",
        f"टेंडर: {tender['title']} ({tender['tender_id']})",
        f"विभाग: {tender['department']}",
        f"अंदाजित किंमत: {format_inr(tender['estimated_cost'])}",
    ]
    if tender.get("emd_amount"):
        lines.append(f"EMD: {format_inr(tender['emd_amount'])}")
    lines.append("")
    lines.append(f"✅ उपलब्ध कागदपत्रे: {len(analysis['matched_documents'])}")
    if analysis["missing_documents"]:
        lines.append("❌ कमी असलेली कागदपत्रे:")
        lines.extend(f"  • {d}" for d in analysis["missing_documents"])
    for issue in analysis["issues"]:
        lines.append(f"⚠️ {issue}")
    for note in analysis["unverified"]:
        lines.append(f"ℹ️ {note}")
    lines.append("")
    verdict = {
        True: "निष्कर्ष: भाऊ, तुम्ही या टेंडरसाठी पात्र दिसता. बिड रेट तपासायचा का?",
        False: "निष्कर्ष: भाऊ, वरील त्रुटी दूर केल्याशिवाय हे टेंडर भरणे धोक्याचे आहे.",
        None: "निष्कर्ष: काही अटी तपासता आल्या नाहीत; प्रोफाइल पूर्ण करा किंवा निविदा तपासा.",
    }[analysis["eligible"]]
    lines.append(verdict)
    return "\n".join(lines)
