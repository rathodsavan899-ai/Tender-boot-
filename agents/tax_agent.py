"""GST liability, Input Tax Credit and CA-ready breakdown. All numbers are computed from supplied inputs."""
from __future__ import annotations

from agents import format_inr, llm_available, llm_text, logger
from config import get_settings
from system_prompt import MASTER_SYSTEM_PROMPT

DISCLAIMER_MR = (
    "हे आकडे तुम्ही दिलेल्या माहितीवर आधारित अंदाज आहेत. अंतिम रिटर्न भरण्यापूर्वी तुमच्या सीए कडून खात्री करा. "
    "कामाच्या प्रकारानुसार GST दर वेगळा असू शकतो."
)

DISCLAIMER_EN = ("These figures are estimates based on the information you entered. Confirm with your CA before filing returns. "
                 "The GST rate can differ by type of work.")

GENERAL_STRATEGIES_EN = [
    "Claim ITC only on valid tax invoices that appear in GSTR-2B; check that your supplier has filed their return.",
    "Make sure every purchase bill carries your GSTIN and the correct HSN/SAC so ITC is not rejected.",
    "File GSTR-1 and GSTR-3B on time; late filing can attract penalty and interest.",
    "GST TDS deducted by a government department is credited to your electronic cash ledger; use it against later liability.",
]

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

    rows = [
        ("करपात्र मूल्य (Taxable Value)", "Taxable value", r2(taxable_value)),
        (f"आउटपुट GST @ {gst_rate_percent:g}%", f"Output GST @ {gst_rate_percent:g}%", output_total),
    ]
    if intra_state:
        rows += [("  CGST", "  CGST", output["cgst"]), ("  SGST", "  SGST", output["sgst"])]
    else:
        rows.append(("  IGST", "  IGST", output["igst"]))
    rows += [
        ("एकूण इन्व्हॉइस मूल्य", "Total invoice value", invoice_total),
        ("पात्र ITC (वजा)", "Eligible ITC (less)", eligible_total),
        ("ब्लॉक/अपात्र ITC (क्लेम नाही)", "Blocked / ineligible ITC (not claimed)", blocked_total),
        ("निव्वळ GST देय", "Net GST payable", payable),
    ]
    if carry_forward:
        rows.append(("पुढे नेता येणारा ITC (क्रेडिट शिल्लक)", "ITC balance to carry forward", carry_forward))
    if tds:
        rows += [("GST TDS (विभागाकडून कपात)", "GST TDS (deducted by department)", tds["amount"]),
                 ("प्रत्यक्ष मिळणारी रक्कम", "Amount actually received", receipt)]
    breakdown = [{"particular": mr, "particular_en": en, "amount": amt} for mr, en, amt in rows]

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
    result["summary_en"] = (
        f"Output GST {format_inr(output_total)}, eligible ITC {format_inr(eligible_total)}, "
        f"net GST payable {format_inr(payable)}."
        + (f" ITC balance {format_inr(carry_forward)} can be carried forward." if carry_forward else "")
    )
    result["strategies_mr"] = _strategies(result)
    result["strategies_en"] = (["Part of the ITC is treated as ineligible; ask your CA to re-check eligibility of those purchases."]
                               if blocked_total > 0 else []) + GENERAL_STRATEGIES_EN
    result["disclaimer_en"] = DISCLAIMER_EN
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
