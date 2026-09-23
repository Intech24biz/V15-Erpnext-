import frappe
from frappe.model.document import Document

PENDING_APPROVAL_STATUS = "Payment Received - Pending Approval"
APPROVED_STATUS = "Approved"


class SalesCommissionEntry(Document):
	def before_update_after_submit(self):
		# Ticking either approval checkbox re-saves an already-submitted entry, which
		# takes this path (not validate()) — see sales_commission.py for why.
		self.auto_promote_to_approved()

	def auto_promote_to_approved(self):
		# This is the only place "both boxes ticked" is actually checked. The matching
		# Pending Approval -> Approved transitions in the workflow fixture intentionally
		# carry no `condition` — Frappe evaluates a transition's condition against the
		# *pre-save* snapshot of the doc, so on the very save that ticks the second box,
		# `doc.approved_by_technical` in that condition would still read as the old,
		# unticked value and the transition would wrongly be refused. The transition's
		# `allowed` role list (Financial Manager/System Manager/Technical Approver) still
		# gates who may trigger it; `status` itself is locked to permlevel 3 so nobody
		# without System Manager's field-level access can set it directly.
		if (
			self.status == PENDING_APPROVAL_STATUS
			and self.approved_by_management
			and self.approved_by_technical
		):
			self.status = APPROVED_STATUS

	def on_cancel(self):
		# Cancellation bypasses validate_workflow and validate_update_after_submit
		# entirely (see sales_commission.py for why status is otherwise locked down),
		# so this is set directly rather than through the workflow.
		self.db_set("status", "Cancelled")
