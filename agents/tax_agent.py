"""GST liability, Input Tax Credit and CA-ready breakdown. All numbers are computed from supplied inputs."""
from __future__ import annotations

from agents import format_inr, llm_available, llm_text, logger
from config import get_settings
from system_prompt import MASTER_SYSTEM_PROMPT

DISCLAIMER_MR = (
    "हे आकडे तुम्ही दिलेल्या माहितीवर आधारित अंदाज आहेत. अंतिम रिटर्न भरण्यापूर्वी तुमच्या सीए कडून खात्री करा. "
    "कामाच्या प्रकारानुसार GST दर वेगळा असू शकतो."
)

GENERAL_STRATEGIES_MR = [
    "ITC फक्त वैध टॅक्स इन्व्हॉइस आणि GSTR-2B मध्ये दिसणाऱ्या खरेदीवरच क्लेम करा; पुरवठादाराने रिटर्न भरले आहे का ते तपासा.",
    "प्रत्येक खरेदी बिलावर तुमचा GSTIN आणि योग्य HSN/SAC आहे याची खात्री करा, म्हणजे ITC नाकारला जाणार नाही.",
    "GSTR-1 आणि GSTR-3B वेळेत भरा; उशिरा भरल्यास दंड आणि व्याज लागू शकते.",
    "सरकारी विभागाकडून GST TDS कापला गेल्यास तो तुमच्या इलेक्ट्रॉनिक कॅश लेजरमध्ये जमा होतो; तो पुढील देयकात वापरा.",
]


def compute(taxable_value: float, gst_rate_percent: float, intra_state: bool,
            purchases: list[dict], gst_tds_applicable: bool) -> dict:
    s = get_settings()
    r2 = lambda v: round(v + 1e-9, 2)

    output_total = r2(taxable_value * gst_rate_percent / 100)
    if intra_state:
        half = r2(output_total / 2)
        output = {"cgst": half, "sgst": r2(output_total - half), "igst": 0.0, "total": output_total}
    else:
        output = {"cgst": 0.0, "sgst": 0.0, "igst": output_total, "total": output_total}
    invoice_total = r2(taxable_value + output_total)

    items, eligible_total, blocked_total = [], 0.0, 0.0
    for p in purchases:
        tax = r2(p["taxable_value"] * p["gst_rate_percent"] / 100)
        items.append({**p, "gst_amount": tax})
        if p["itc_eligible"]:
            eligible_total += tax
        else:
            blocked_total += tax
    eligible_total, blocked_total = r2(eligible_total), r2(blocked_total)

    net = r2(output_total - eligible_total)
    payable = max(net, 0.0)
    carry_forward = r2(-net) if net < 0 else 0.0

    tds = None
    receipt = invoice_total
    if gst_tds_applicable:
        applies = taxable_value > s.gst_tds_threshold
        amount = r2(taxable_value * s.gst_tds_rate_percent / 100) if applies else 0.0
        tds = {
            "applies": applies, "rate_percent": s.gst_tds_rate_percent, "amount": amount,
            "note_mr": ("GST TDS लागू (मर्यादेपेक्षा जास्त मूल्य); रक्कम तुमच्या कॅश लेजरमध्ये जमा होईल."
                        if applies else f"मूल्य {format_inr(s.gst_tds_threshold)} किंवा कमी असल्याने TDS लागू नाही."),
        }
        receipt = r2(invoice_total - amount)
        tds["cash_payable_after_tds_credit"] = max(r2(payable - amount), 0.0)

    breakdown = [
        {"particular": "करपात्र मूल्य (Taxable Value)", "amount": r2(taxable_value)},
        {"particular": f"आउटपुट GST @ {gst_rate_percent:g}%", "amount": output_total},
    ]
    if intra_state:
        breakdown += [{"particular": "  CGST", "amount": output["cgst"]}, {"particular": "  SGST", "amount": output["sgst"]}]
    else:
        breakdown.append({"particular": "  IGST", "amount": output["igst"]})
    breakdown += [
        {"particular": "एकूण इन्व्हॉइस मूल्य", "amount": invoice_total},
        {"particular": "पात्र ITC (वजा)", "amount": eligible_total},
        {"particular": "ब्लॉक/अपात्र ITC (क्लेम नाही)", "amount": blocked_total},
        {"particular": "निव्वळ GST देय", "amount": payable},
    ]
    if carry_forward:
        breakdown.append({"particular": "पुढे नेता येणारा ITC (क्रेडिट शिल्लक)", "amount": carry_forward})
    if tds:
        breakdown += [{"particular": "GST TDS (विभागाकडून कपात)", "amount": tds["amount"]},
                      {"particular": "प्रत्यक्ष मिळणारी रक्कम", "amount": receipt}]

    result = {
        "inputs": {"taxable_value": r2(taxable_value), "gst_rate_percent": gst_rate_percent,
                   "supply_type": "intra_state (CGST+SGST)" if intra_state else "inter_state (IGST)"},
        "output_tax": output, "invoice_total": invoice_total,
        "itc": {"eligible_total": eligible_total, "blocked_total": blocked_total, "items": items},
        "net_gst_payable": payable, "itc_carry_forward": carry_forward,
        "gst_tds": tds, "expected_receipt": receipt,
        "ca_ready_breakdown": breakdown,
        "disclaimer_mr": DISCLAIMER_MR,
    }
    result["summary_mr"] = (
        f"आउटपुट GST {format_inr(output_total)}, पात्र ITC {format_inr(eligible_total)}, "
        f"निव्वळ GST देय {format_inr(payable)}."
        + (f" ITC शिल्लक {format_inr(carry_forward)} पुढे नेता येईल." if carry_forward else "")
    )
    result["strategies_mr"] = _strategies(result)
    return result


def _strategies(result: dict) -> list[str]:
    strategies = list(GENERAL_STRATEGIES_MR)
    if result["itc"]["blocked_total"] > 0:
        strategies.insert(0, "काही खरेदीवरील ITC अपात्र धरला आहे; त्या खरेदीची पात्रता सीए कडून पुन्हा तपासा.")
    if not llm_available():
        return strategies
    try:
        system = (MASTER_SYSTEM_PROMPT +
                  "\nखालील गणिताच्या आधारे ३ छोट्या मराठी टॅक्स-नियोजन सूचना दे. फक्त दिलेले आकडे वापर; नवीन आकडे किंवा कायदेशीर कलमे बनवू नकोस. "
                  "प्रत्येक सूचना वेगळ्या ओळीत, बुलेटशिवाय.")
        text = llm_text(system, result["summary_mr"] + "\n" + "\n".join(f"{b['particular']}: {b['amount']}" for b in result["ca_ready_breakdown"]))
        ai_lines = [ln.strip(" -•\t") for ln in text.splitlines() if ln.strip()]
        return ai_lines[:3] + strategies
    except Exception as exc:
        logger.warning("tax strategy LLM failed: %s", exc)
        return strategies
