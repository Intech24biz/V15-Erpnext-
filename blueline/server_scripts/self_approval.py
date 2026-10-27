import frappe
from frappe import _
from frappe.model.workflow import get_workflow_name

PENDING_APPROVAL_STATE = "Pending Approval"
SENT_BY_FIELD = "custom_sent_for_approval_by"

# Every doctype that runs a GI "Draft -> Pending Approval -> Approved" workflow.
APPROVAL_DOCTYPES = ("Quotation", "Purchase Order", "Sales Invoice", "Payment Entry", "Petty Cash Voucher")


def record_sender(doc, method=None):
	"""`validate`: stamp who moved the document into Pending Approval. The value comes from
	the session on that transition and is otherwise restored from the saved record, so a
	client can never set or alter it (read_only on the field is only a UI hint).
	"""
	if not get_workflow_name(doc.doctype):
		return

	before = doc.get_doc_before_save()
	previous_state = before.get("workflow_state") if before else None

	if doc.get("workflow_state") == PENDING_APPROVAL_STATE and previous_state != PENDING_APPROVAL_STATE:
		doc.set(SENT_BY_FIELD, frappe.session.user)
	else:
		doc.set(SENT_BY_FIELD, before.get(SENT_BY_FIELD) if before else None)


def block_self_approval(doc, method=None):
	"""`before_submit`: in every GI workflow the only submitted state is Approved, so every
	submission is an approval. Checking here (not on the workflow action) covers the Approve
	button, apply_workflow over the API, bulk approval, and a raw submit — on a raw submit
	Frappe moves a Draft straight to Approved *after* this hook runs, so the workflow state
	can't be relied on. Applies to every user and role; there is no Administrator or System
	Manager exemption.
	"""
	if not get_workflow_name(doc.doctype):
		return

	# Owner from the stored record, not the incoming payload. A brand-new document being
	# inserted already submitted has no stored record; its owner is the session user.
	before = doc.get_doc_before_save()
	owner = before.owner if before else doc.owner

	if frappe.session.user in (owner, doc.get(SENT_BY_FIELD)):
		frappe.throw(
			_("You cannot approve a document you created or sent for approval."),
			title=_("Self-Approval Not Allowed"),
		)
