import frappe


RESTRICTED_ROLE = "GI Sales Dept 2"
BYPASS_ROLES = {"GI Management", "GI Sales Dept", "GI Tech Dept"}
EXEMPT_USERS = {"Administrator"}
EXEMPT_ROLES = {"System Manager"}


def enforce_approval(doc, method=None):
    """
    Block direct submission by GI Sales Dept 2 users unless the document
    has already gone through workflow approval (workflow_state == "Approved").
    Called via hooks: before_submit on Quotation, Purchase Order,
    Sales Invoice, Payment Entry.
    """
    user = frappe.session.user

    if user in EXEMPT_USERS:
        return

    roles = set(frappe.get_roles(user))

    if EXEMPT_ROLES & roles:
        return

    if RESTRICTED_ROLE not in roles:
        return

    if BYPASS_ROLES & roles:
        return

    workflow_state = doc.get("workflow_state")
    if workflow_state != "Approved":
        frappe.throw(
            "Sales Dept 2 users cannot submit this document directly. "
            "It must first go through workflow approval — please use the "
            "\"Send for Approval\" action instead of submitting directly."
        )
