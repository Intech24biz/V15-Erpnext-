import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.meta import get_field_precision
from frappe.utils import cint, cstr, flt

PENDING_APPROVAL_STATUS = "Payment Received - Pending Approval"
APPROVED_STATUS = "Approved"
PAID_STATUS = "Paid"
CANCELLED_STATUS = "Cancelled"

# Set on doc.flags only by sales_commission.py's Credit Note path. `flags` is a reserved key
# that Frappe never fills from a client payload, so a user request cannot carry it.
CREDIT_NOTE_ADJUSTMENT_FLAG = "credit_note_adjustment"
# Same, for sales_commission.py moving an entry back (or flagging it) after a payment was undone.
PAYMENT_UNDONE_FLAG = "payment_undone"
SYSTEM_FLAGS = (CREDIT_NOTE_ADJUSTMENT_FLAG, PAYMENT_UNDONE_FLAG)

DEDUCTION_TYPE = "Deduction"
UNPAID_MESSAGE = (
	"This commission cannot be approved while the invoice still has an outstanding amount. "
	"Wait until the invoice is fully paid or credited."
)

# Once an entry reaches one of these, its approval ticks are history and can't change.
LOCKED_STATUSES = (APPROVED_STATUS, PAID_STATUS, CANCELLED_STATUS)

# approval checkbox -> field recording the user who ticked it (set server-side only)
APPROVAL_TICKS = {
	"approved_by_management": "management_approved_by",
	"approved_by_technical": "technical_approved_by",
}


def invoice_outstanding(sales_invoice):
	"""The invoice's outstanding amount right now: read straight from the database (not the
	document cache), rounded to the currency's precision. A missing invoice counts as unpaid."""
	row = frappe.db.sql(
		"select outstanding_amount, currency from `tabSales Invoice` where name = %s",
		sales_invoice,
		as_dict=True,
	)
	if not row:
		return float("inf")
	df = frappe.get_meta("Sales Invoice").get_field("outstanding_amount")
	return flt(row[0].outstanding_amount, get_field_precision(df, currency=row[0].currency))


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

	def validate(self):
		# Entries are normally created already submitted, but System Manager may still
		# create one by hand; the same approval rules apply to a draft.
		if self.original_commission_amount is None:
			self.original_commission_amount = self.commission_amount
		self.keep_system_warning()
		self.apply_approval_rules()
		self.refuse_approval_while_unpaid()

	def is_system_change(self):
		return any(self.flags.get(flag) for flag in SYSTEM_FLAGS)

	def validate_workflow(self):
		# A Credit Note can cancel an entry from any state, or restore it, and an undone
		# payment moves it back to Accrued; the commission workflow has no transition for
		# either. Only those system paths skip it.
		if self.is_system_change():
			return
		super().validate_workflow()

	def before_update_after_submit(self):
		# Ticking either approval checkbox re-saves an already-submitted entry, which
		# takes this path (not validate()) — see sales_commission.py for why.
		self.refuse_manual_cancellation()
		self.keep_system_warning()
		self.apply_approval_rules()
		if self.is_system_change():
			# Cancelling or restoring for a Credit Note, or moving back after an undone
			# payment, never grants an approval.
			return
		self.auto_promote_to_approved()
		self.refuse_approval_while_unpaid()
		self.require_both_approvals()

	def keep_system_warning(self):
		# Payment Warning is written only by the system (sales_commission.reopen_if_unsettled).
		if self.is_system_change():
			return
		before = self.get_doc_before_save()
		self.unpaid_warning = before.unpaid_warning if before else None

	def refuse_approval_while_unpaid(self):
		# Holds for every user and role, Administrator and System Manager included, and for
		# every route: either tick, the Approve action, or any save that sets Approved.
		# Deductions are a Credit Note's own flow and are approved regardless.
		if self.entry_type == DEDUCTION_TYPE:
			return
		before = self.get_doc_before_save()
		newly_ticked = any(cint(self.get(tick)) and not (before and cint(before.get(tick))) for tick in APPROVAL_TICKS)
		becoming_approved = self.status == APPROVED_STATUS and not (before and before.status == APPROVED_STATUS)
		if not (newly_ticked or becoming_approved):
			return
		if invoice_outstanding(self.sales_invoice) > 0:
			frappe.throw(_(UNPAID_MESSAGE), title=_("Invoice Not Fully Paid"))

	def refuse_manual_cancellation(self):
		# Commission Amount and the Adjustments table are locked after submit by Frappe
		# itself; the Credit Note path lifts that lock for its own save only. Status is
		# editable after submit (Mark as Paid), so moving it to or from Cancelled — which
		# only a Credit Note does — is refused here for every user, Administrator included.
		if self.flags.get(CREDIT_NOTE_ADJUSTMENT_FLAG):
			return
		before = self.get_doc_before_save()
		if not before or before.status == self.status:
			return
		if CANCELLED_STATUS in (before.status, self.status):
			frappe.throw(
				_("{0} can only be set to or from {1} by approving or cancelling a Credit Note.").format(
					frappe.bold(_("Status")), frappe.bold(_(CANCELLED_STATUS))
				),
				title=_("Changed by Credit Note Only"),
			)

	def apply_approval_rules(self):
		# These hold for every user and role (Administrator and System Manager included)
		# and for system saves that set ignore_permissions.
		self.lock_approvals_once_approved()
		self.record_approvers()
		self.refuse_same_approver()

	def lock_approvals_once_approved(self):
		before = self.get_doc_before_save()
		if not before or before.status not in LOCKED_STATUSES:
			return
		for tick in APPROVAL_TICKS:
			if cint(self.get(tick)) != cint(before.get(tick)):
				frappe.throw(
					_("{0} cannot be changed once the entry is {1}.").format(
						frappe.bold(_(self.meta.get_label(tick))), _(before.status)
					),
					title=_("Approval Locked"),
				)

	def record_approvers(self):
		# The "... Approval By" fields are read_only only in the UI, so whatever the client
		# sent is discarded: a tick going 0 -> 1 records the session user, a cleared tick
		# clears it, and an unchanged tick keeps the stored value.
		before = self.get_doc_before_save()
		for tick, approver_field in APPROVAL_TICKS.items():
			ticked_before = cint(before.get(tick)) if before else 0
			if not cint(self.get(tick)):
				self.set(approver_field, None)
			elif not ticked_before:
				self.set(approver_field, frappe.session.user)
			else:
				self.set(approver_field, before.get(approver_field))

	def refuse_same_approver(self):
		before = self.get_doc_before_save()
		if before and before.status in LOCKED_STATUSES:
			return
		if not (self.approved_by_management and self.approved_by_technical):
			return
		if self.management_approved_by and self.management_approved_by == self.technical_approved_by:
			frappe.throw(
				_(
					"{0} and {1} must be given by two different users. {2} cannot give both approvals."
				).format(
					frappe.bold(_("Approved by Management")),
					frappe.bold(_("Approved by Technical")),
					frappe.bold(self.management_approved_by),
				),
				title=_("Same User Cannot Give Both Approvals"),
			)

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
		# Ticks given before approvers were recorded (and not recoverable from the version
		# history) can't be proven to come from two people, so they don't count.
		if not (self.management_approved_by and self.technical_approved_by):
			frappe.throw(
				_(
					"This entry's approvals were given before the approving users were recorded. "
					"Untick {0} and {1} and have two different users tick them again."
				).format(frappe.bold(_("Approved by Management")), frappe.bold(_("Approved by Technical"))),
				title=_("Approval Incomplete"),
			)

	def on_cancel(self):
		# Cancellation bypasses validate_workflow and validate_update_after_submit
		# entirely (see sales_commission.py for why status is otherwise locked down),
		# so this is set directly rather than through the workflow.
		self.db_set("status", "Cancelled")
