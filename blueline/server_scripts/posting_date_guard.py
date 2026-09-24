import frappe
from frappe import _
from frappe.utils import getdate


COMPANY_CONFIG_DOCTYPE = "Company COA Configuration"

EXEMPT_USERS = {"Administrator"}
EXEMPT_ROLES = {"System Manager"}

DEFAULT_DATE_FIELD = "posting_date"

# Doctypes whose relevant ledger date lives in a differently-named field.
DATE_FIELD_OVERRIDES = {
    "Period Closing Voucher": "transaction_date",
}


def enforce_earliest_posting_date(doc, method=None):
    """
    Block posting to the ledger before a company's configured
    earliest_allowed_posting_date (Company COA Configuration).
    System Manager may override; the override is recorded as a Comment on
    the document itself, so there is an audit trail even though it wasn't
    blocked.
    Called via hooks: validate on every ledger-posting doctype (see
    hooks.py doc_events) — runs on every save, including Save-as-draft,
    not just submit.
    """
    company = doc.get("company")
    if not company:
        return

    cutoff = _get_cutoff_date(company)
    if not cutoff:
        return

    date_fieldname = DATE_FIELD_OVERRIDES.get(doc.doctype, DEFAULT_DATE_FIELD)
    doc_date = doc.get(date_fieldname)
    if not doc_date:
        return

    doc_date = getdate(doc_date)
    if doc_date >= cutoff:
        return

    if _override_permitted():
        _record_override(doc, company, doc_date, cutoff, date_fieldname)
        return

    frappe.throw(
        _(
            "{0} cannot be dated {1} for company {2}: postings before {3} are not "
            "allowed. Contact a System Manager if this document genuinely needs to "
            "be backdated."
        ).format(_(doc.doctype), doc_date, company, cutoff)
    )


def _get_cutoff_date(company):
    # frappe.get_all (not get_list): Company COA Configuration is itself row-level
    # segregated by Company User Permissions, and the ordinary users creating
    # everyday transactions for a company are not expected to also hold a User
    # Permission on its COA Configuration record. get_list would make this guard
    # silently do nothing for exactly the users it exists to constrain, since an
    # invisible row reads identically to "no cutoff configured" — the cutoff has
    # to apply uniformly regardless of what the posting user can see.
    rows = frappe.get_all(
        COMPANY_CONFIG_DOCTYPE,
        filters={"name": company},
        pluck="earliest_allowed_posting_date",
        limit=1,
    )
    if not rows or not rows[0]:
        return None
    return getdate(rows[0])


def _override_permitted():
    user = frappe.session.user
    if user in EXEMPT_USERS:
        return True
    return bool(EXEMPT_ROLES & set(frappe.get_roles(user)))


def _record_override(doc, company, doc_date, cutoff, date_fieldname):
    message = _(
        "Posting date override: {user} saved this {doctype} with {field} = {doc_date} "
        "for company {company}, before the configured earliest allowed posting date "
        "of {cutoff}. Allowed because the user holds the System Manager role."
    ).format(
        user=frappe.session.user,
        doctype=_(doc.doctype),
        field=date_fieldname,
        doc_date=doc_date,
        company=company,
        cutoff=cutoff,
    )
    # Not doc.add_comment(): that inserts a Comment through the normal link-validation
    # path, which looks up doc.name in the database — fine for an existing document,
    # but this guard also fires on a brand-new document's very first insert, where
    # doc.name is already assigned (autoname runs before validate()) but the row
    # itself hasn't been written yet, so the lookup fails with LinkValidationError.
    # ignore_links is safe here specifically because we constructed this reference
    # ourselves from the document currently being saved.
    comment = frappe.get_doc(
        {
            "doctype": "Comment",
            "comment_type": "Info",
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "content": message,
        }
    )
    comment.flags.ignore_links = True
    comment.insert(ignore_permissions=True)
