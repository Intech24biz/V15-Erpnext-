import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr

PENDING_APPROVAL_STATUS = "Payment Received - Pending Approval"
APPROVED_STATUS = "Approved"


class SalesCommissionEntry(Document):
	def validate_higher_perm_levels(self):
		# Frappe's own version of this silently resets any field the user can't write at its
		# permlevel back to the stored value — before any controller hook runs. For the
		# approval checkboxes and status that turned a wrong-role edit into a save that
		# "worked" and then quietly undid itself, so refuse it with a clear message first.
		# The framework reset below then stays as the backstop.
		self.refuse_unpermitted_field_changes()
		super().validate_higher_perm_levels()

	def refuse_unpermitted_field_changes(self):
		if self.is_new() or self.flags.ignore_permissions or frappe.session.user == "Administrator":
			return

		guarded = self.meta.get_high_permlevel_fields()
		stored = frappe.db.get_value(self.doctype, self.name, [df.fieldname for df in guarded], as_dict=True) or {}
		writable = self.get_permlevel_access("write")

		for df in guarded:
			normalize = cint if df.fieldtype == "Check" else cstr
			if normalize(self.get(df.fieldname)) == normalize(stored.get(df.fieldname)):
				continue
			if df.permlevel in writable:
				continue
			roles = sorted(
				{p.role for p in self.meta.permissions if p.permlevel == df.permlevel and p.write}
			)
			frappe.throw(
				_("You don't have permission to change {0}. Required role: {1}.").format(
					frappe.bold(_(df.label)), _(" or ").join(roles) or _("System Manager")
				),
				frappe.PermissionError,
				title=_("Not Permitted"),
			)

	def before_update_after_submit(self):
		# Ticking either approval checkbox re-saves an already-submitted entry, which
		# takes this path (not validate()) — see sales_commission.py for why.
		self.auto_promote_to_approved()
		self.require_both_approvals()

	def auto_promote_to_approved(self):
		# The matching Pending Approval -> Approved transitions in the workflow fixture
		# intentionally carry no `condition` — Frappe evaluates a transition's condition
		# against the *pre-save* snapshot of the doc, so on the very save that ticks the
		# second box, `doc.approved_by_technical` in that condition would still read as the
		# old, unticked value and the transition would wrongly be refused. Both-boxes is
		# enforced by require_both_approvals() instead.
		if (
			self.status == PENDING_APPROVAL_STATUS
			and self.approved_by_management
			and self.approved_by_technical
		):
			self.status = APPROVED_STATUS

	def require_both_approvals(self):
		# The workflow's "Approve" action is open to Financial Manager / Technical Approver /
		# System Manager with no condition (see above), and Financial Manager can write the
		# status field so it can "Mark as Paid". This is the single place that guarantees an
		# entry only ever becomes Approved with BOTH approvals ticked, whoever triggers it.
		if self.status != APPROVED_STATUS:
			return
		if frappe.db.get_value(self.doctype, self.name, "status") == APPROVED_STATUS:
			return
		if not (self.approved_by_management and self.approved_by_technical):
			frappe.throw(
				_("Both approvals are required before this entry can be Approved: tick {0} and {1}.").format(
					frappe.bold(_("Approved by Management")), frappe.bold(_("Approved by Technical"))
				),
				title=_("Approval Incomplete"),
			)

	def on_cancel(self):
		# Cancellation bypasses validate_workflow and validate_update_after_submit
		# entirely (see sales_commission.py for why status is otherwise locked down),
		# so this is set directly rather than through the workflow.
		self.db_set("status", "Cancelled")
