import frappe


MONTH_MAP = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR",
    5: "MAY", 6: "JUN", 7: "JUL", 8: "AUG",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
}

COMPANY_BRANCH_MAP = {
    "General Innovations (Pvt) Ltd": "GIIN",
    "General Innovations Private Limited": "GIIN",
    "Blueline Enterprises Pvt Ltd": "BLIN",
    "Blueline Enterprises (PVT) LTD": "BLIN",
}


def generate_serial_number(doc, method=None):
    """
    Auto-generate gazette-compliant Tax Invoice serial number
    Format: YYMMM_QQQQ_XXXXX
    Example: 26JUL_GIIN_01842
    Called via hooks: Sales Invoice before_submit
    """
    if doc.get("custom_tax_invoice_serial"):
        # Already generated — do not overwrite
        return

    posting_date = doc.posting_date
    if isinstance(posting_date, str):
        parts = posting_date.split("-")
        year = parts[0]
        month = int(parts[1])
        yy = year[2:]
    else:
        yy = posting_date.strftime("%y")
        month = posting_date.month

    mmm = MONTH_MAP.get(month, "JAN")

    # Get branch/company code
    qqqq = COMPANY_BRANCH_MAP.get(doc.company, "GIIN")

    # Get numeric part from invoice name
    raw = doc.name
    for prefix in ["TAX-", "SAL-SINV-", "ACC-SINV-", "SINV-"]:
        raw = raw.replace(prefix, "")

    serial = f"{yy}{mmm}_{qqqq}_{raw}"

    # Enforce 40 character limit per gazette
    if len(serial) > 40:
        serial = serial[:40]

    doc.custom_tax_invoice_serial = serial
    frappe.msgprint(
        f"Tax Invoice Serial No. generated: {serial}",
        alert=True
    )
