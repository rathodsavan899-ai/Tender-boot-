"""1-Click EMD & Bank Guarantee document kit (checklist + bank request letter + WhatsApp summary).

The checklist is the common set banks ask for; the tender's own conditions and your bank's rules prevail.
"""
from __future__ import annotations

from datetime import date

from agents import fmt_date, format_inr

BG_KINDS = {
    "EMD_BG": "बयाना रक्कम (EMD) बँक गॅरंटी",
    "PERFORMANCE_BG": "परफॉर्मन्स बँक गॅरंटी",
}

COMMON_DOCUMENTS = [
    "बँक गॅरंटी / EMD साठी विनंती पत्र (खाली तयार)",
    "टेंडर नोटीस / निविदा सूचनेची प्रत (EMD/BG अटींसह)",
    "फर्मचे PAN कार्ड आणि GST प्रमाणपत्र",
    "फर्मचा KYC (पत्ता पुरावा, भागीदार/मालकाचे ओळखपत्र)",
    "चालू खात्याचे (Current Account) तपशील",
    "मागील आर्थिक वर्षाचे ऑडिटेड बॅलन्स शीट / ITR",
    "क्रेडिट/ओव्हरड्राफ्ट लिमिट मंजुरी पत्र (असल्यास)",
    "वर्क ऑर्डर / स्वीकृती पत्र (परफॉर्मन्स BG साठी)",
]


def build_kit(contractor_name: str, tender_ref: str, tender_title: str, department: str, bg_type: str,
              guarantee_amount: float, validity_months: int, bank_name: str | None = None,
              branch: str | None = None, account_number_last4: str | None = None,
              beneficiary: str | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    kind = BG_KINDS[bg_type]
    beneficiary = beneficiary or department

    documents = list(COMMON_DOCUMENTS)
    if bg_type == "PERFORMANCE_BG":
        documents.append("करारनामा / कार्यारंभ आदेशाची प्रत")

    to_line = f"व्यवस्थापक, {bank_name}" + (f", {branch} शाखा" if branch else "") if bank_name else "शाखा व्यवस्थापक, संबंधित बँक"
    acct = f"\nखाते क्रमांक (शेवटचे ४ अंक): {account_number_last4}" if account_number_last4 else ""

    letter = (
        f"प्रति,\n{to_line}\n\nदिनांक: {fmt_date(today)}\n\n"
        f"विषय: {kind} जारी करणेबाबत विनंती — {tender_ref}\n\n"
        f"महोदय,\n\n"
        f"आम्ही, {contractor_name}, आपल्या बँकेचे ग्राहक आहोत.{acct}\n"
        f"आम्ही '{tender_title}' (निविदा क्र. {tender_ref}) या कामासाठी {department} यांच्याकडे निविदा सादर करीत आहोत. "
        f"निविदेतील अटींनुसार {format_inr(guarantee_amount)} रकमेची {kind} {beneficiary} यांच्या नावे "
        f"{validity_months} महिन्यांच्या वैधतेसह जारी करण्याची कृपा करावी.\n\n"
        f"आवश्यक कागदपत्रे सोबत जोडली आहेत. नियमानुसार लागणारे मार्जिन/शुल्क भरण्यास आम्ही तयार आहोत.\n\n"
        f"आपला विश्वासू,\n{contractor_name}\n(अधिकृत स्वाक्षरी व शिक्का)"
    )

    whatsapp = (
        f"🏦 *{kind} किट तयार*\nटेंडर: {tender_title} ({tender_ref})\n"
        f"रक्कम: {format_inr(guarantee_amount)} | वैधता: {validity_months} महिने\n\n"
        "बँकेत न्यायची कागदपत्रे:\n" + "\n".join(f"{i}. {d}" for i, d in enumerate(documents, 1)) +
        "\n\nटीप: बँकेचे नियम आणि निविदेतील अटी अंतिम समजाव्यात."
    )
    return {
        "guarantee_type": kind,
        "guarantee_amount": guarantee_amount,
        "validity_months": validity_months,
        "document_checklist": documents,
        "bank_request_letter_mr": letter,
        "whatsapp_message": whatsapp,
        "note_mr": "ही यादी सर्वसाधारण आहे; तुमच्या बँकेकडून आणि निविदेतील अटींनुसार खात्री करा.",
    }
