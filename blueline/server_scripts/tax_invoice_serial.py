import frappe
from frappe import _


SERIAL_FIELD = "custom_tax_invoice_serial"

# Credit Notes (is_return = 1) are numbered in their own series so they never take a
# number from the tax-invoice sequence. Keyed by the original invoice's series.
CREDIT_NOTE_SERIES = {
    "BTAX-": "BTAX-RET-",
    "TAX-": "TAX-RET-",
    "SVAT-": "SVAT-RET_",
    "ACC-SINV-.YYYY.-": "ACC-SINV-RET-.YYYY.-",
}
DEFAULT_CREDIT_NOTE_SERIES = "ACC-SINV-RET-.YYYY.-"

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

    Submit happens once per document, so the serial is always computed here and never
    taken from the incoming document: a value copied from another invoice or sent by the
    client is overwritten. Credit Notes are not tax invoices and get no serial.
    """
    if doc.get("is_return"):
        doc.set(SERIAL_FIELD, None)
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


def set_credit_note_series(doc, method=None):
    """
    Sales Invoice before_insert (runs before the name is assigned): a Credit Note always
    takes its number from the credit-note series matching the original invoice's series,
    whatever series it arrived with (ERPNext's mapper drops naming_series, so a return
    would otherwise fall back to the default tax-invoice series and consume its next number).
    """
    if not doc.get("is_return"):
        return

    original_series = doc.naming_series
    if doc.return_against:
        original_series = frappe.db.get_value("Sales Invoice", doc.return_against, "naming_series")

    if original_series in CREDIT_NOTE_SERIES.values():
        doc.naming_series = original_series
    else:
        doc.naming_series = CREDIT_NOTE_SERIES.get(original_series, DEFAULT_CREDIT_NOTE_SERIES)


def validate_serial_and_series(doc, method=None):
    """
    Sales Invoice validate. A draft never carries a Tax Invoice Serial (it is only ever
    assigned at submit), so anything copied in by Duplicate / Return / Amend or sent by the
    client is dropped. Credit-note series are reserved for Credit Notes.
    """
    if doc.docstatus == 0:
        doc.set(SERIAL_FIELD, None)

    if not doc.get("is_return") and doc.naming_series in CREDIT_NOTE_SERIES.values():
        frappe.throw(
            _("Series {0} is reserved for Credit Notes. Choose a tax invoice series.").format(
                frappe.bold(doc.naming_series)
            )
        )


def block_cancel_of_tax_invoice(doc, method=None):
    """
    Sales Invoice before_cancel: an invoice that was approved (submitted) and issued a Tax
    Invoice Serial can never be cancelled, by any user or role. It is reversed with a
    Credit Note instead, so its number, serial and the tax-invoice sequence stay intact.
    """
    serial = frappe.db.get_value("Sales Invoice", doc.name, SERIAL_FIELD)
    if not serial:
        return

    frappe.throw(
        _(
            "Sales Invoice {0} has been approved and issued Tax Invoice Serial {1}, so it cannot "
            "be cancelled. Issue a Credit Note instead: open the invoice and use "
            "Create > Return / Credit Note."
        ).format(frappe.bold(doc.name), frappe.bold(serial)),
        title=_("Cancel Not Allowed — Issue a Credit Note"),
    )
