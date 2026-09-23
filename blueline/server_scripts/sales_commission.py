import frappe
from frappe import _
from frappe.utils import flt

RULE_DOCTYPE = "Sales Commission Rule"
ENTRY_DOCTYPE = "Sales Commission Entry"

FIXED_AMOUNT = "Fixed Amount Per Unit"
PERCENTAGE = "Percentage of Line Value"

ACCRUED_STATUS = "Accrued"
PENDING_APPROVAL_STATUS = "Payment Received - Pending Approval"
APPROVED_STATUS = "Approved"
PAID_STATUS = "Paid"

# Same roles that hold permlevel-3 write on Sales Commission Entry (status/payment_entry).
MARK_PAID_ROLES = {"System Manager", "Financial Manager"}


def create_commission_entries(doc, method=None):
	"""Sales Invoice `on_submit`: accrue commission for every (item row x sales person)
	pair that matches an enabled Sales Commission Rule. A line with no matching rule is
	logged and skipped — this must never block the invoice submission itself.
	"""
	sales_team = [row for row in (doc.sales_team or []) if row.sales_person]
	if not sales_team:
		return

	for item in doc.items:
		for team_row in sales_team:
			try:
				_process_line(doc, item, team_row.sales_person)
			except Exception:
				frappe.log_error(
					title=f"Sales Commission accrual failed: {doc.name} / {item.item_code} / {team_row.sales_person}",
					message=frappe.get_traceback(),
				)


def _process_line(invoice, item, sales_person):
	rule = _find_matching_rule(invoice.company, sales_person, invoice.customer, item.item_code)
	if not rule:
		frappe.log_error(
			title=f"Sales Commission: no matching rule ({invoice.name} / {item.item_code} / {sales_person})",
			message=(
				f"No enabled Sales Commission Rule matched Company={invoice.company}, "
				f"Sales Person={sales_person}, Customer={invoice.customer}, Item={item.item_code}. "
				"No commission was accrued for this invoice line."
			),
		)
		return

	commission_amount = _calculate_commission(rule, item)

	entry = frappe.get_doc(
		{
			"doctype": ENTRY_DOCTYPE,
			"sales_invoice": invoice.name,
			"sales_invoice_item": item.name,
			"posting_date": invoice.posting_date,
			"sales_person": sales_person,
			"customer": invoice.customer,
			"item_code": item.item_code,
			"company": invoice.company,
			"qty": item.qty,
			"rate": item.rate,
			"amount": item.amount,
			"commission_rule": rule.name,
			"commission_type": rule.commission_type,
			"commission_amount": commission_amount,
			"status": ACCRUED_STATUS,
		}
	)
	# System-driven accrual: the invoice-submitting user need not hold Sales Commission
	# Entry create/write permission themselves.
	entry.insert(ignore_permissions=True)
	entry.submit()


def _find_matching_rule(company, sales_person, customer, item_code):
	"""(sales_person+customer+item_code) > (sales_person+item_code) >
	(sales_person+customer) > (sales_person only), all scoped to company.
	A blank customer/item_code on the rule means "any" — matched here as an explicit
	empty-string filter, not as "ignore this filter".
	"""
	tiers = [
		{"customer": customer or "", "item_code": item_code or ""},
		{"customer": "", "item_code": item_code or ""},
		{"customer": customer or "", "item_code": ""},
		{"customer": "", "item_code": ""},
	]
	for tier in tiers:
		# get_list (not get_all): rules are company data, segregated the same way as
		# Company COA Configuration. In the ordinary case the invoice-submitting user
		# already has User Permission for the invoice's own company, so this resolves
		# rules normally; a user submitting for a company they hold no User Permission
		# for will see no rules here (same trade-off as the rest of this feature).
		rules = frappe.get_list(
			RULE_DOCTYPE,
			filters={
				"sales_person": sales_person,
				"company": company,
				"enabled": 1,
				**tier,
			},
			fields=["name", "commission_type", "rate"],
			limit=1,
		)
		if rules:
			return rules[0]
	return None


def _calculate_commission(rule, item):
	if rule.commission_type == FIXED_AMOUNT:
		return flt(item.qty) * flt(rule.rate)
	if rule.commission_type == PERCENTAGE:
		return flt(item.amount) * flt(rule.rate) / 100
	return 0.0


def release_commission_entries(doc, method=None):
	"""Payment Entry `on_submit` and `on_update_after_submit`: once a referenced Sales
	Invoice's outstanding_amount reaches 0, move its Accrued commission entries to
	"Payment Received - Pending Approval". Registered on both events because
	Payment Reconciliation can update an already-submitted Payment Entry's references
	without re-firing on_submit.
	"""
	invoice_names = {
		row.reference_name
		for row in (doc.references or [])
		if row.reference_doctype == "Sales Invoice" and row.reference_name
	}
	if not invoice_names:
		return

	for invoice_name in invoice_names:
		outstanding = frappe.db.get_value("Sales Invoice", invoice_name, "outstanding_amount")
		if outstanding is None or flt(outstanding) > 0:
			continue
		_release_entries_for_invoice(invoice_name)


def _release_entries_for_invoice(invoice_name):
	# get_all (not get_list): these are the system's own previously-created accrual
	# records, looked up by an explicit sales_invoice + status filter rather than shown
	# as a user-facing view — unlike the rule lookup above, a permission gap here would
	# leave commission stuck in Accrued with no retry, so this is a deliberate exception
	# to the get_list rule.
	entry_names = frappe.get_all(
		ENTRY_DOCTYPE,
		filters={"sales_invoice": invoice_name, "status": ACCRUED_STATUS},
		pluck="name",
	)
	for entry_name in entry_names:
		try:
			entry = frappe.get_doc(ENTRY_DOCTYPE, entry_name)
			entry.status = PENDING_APPROVAL_STATUS
			entry.flags.ignore_permissions = True
			entry.save()
		except Exception:
			frappe.log_error(
				title=f"Sales Commission release failed: {entry_name}",
				message=frappe.get_traceback(),
			)


@frappe.whitelist()
def mark_commission_entry_paid(commission_entry, payment_entry):
	"""Manual action: link an Approved commission entry to the real Payment Entry that
	paid it out and mark it Paid. No automatic bank-file matching.
	"""
	if not (MARK_PAID_ROLES & set(frappe.get_roles())):
		frappe.throw(
			_("Only System Manager or Financial Manager can mark a commission entry as Paid."),
			frappe.PermissionError,
		)

	entry = frappe.get_doc(ENTRY_DOCTYPE, commission_entry)

	if entry.status != APPROVED_STATUS:
		frappe.throw(_("Only an Approved commission entry can be marked as Paid."))

	pe = frappe.db.get_value("Payment Entry", payment_entry, ["name", "docstatus"], as_dict=True)
	if not pe or pe.docstatus != 1:
		frappe.throw(_("{0} is not a submitted Payment Entry.").format(payment_entry))

	references_match = frappe.db.exists(
		"Payment Entry Reference",
		{
			"parent": payment_entry,
			"reference_doctype": "Sales Invoice",
			"reference_name": entry.sales_invoice,
		},
	)
	if not references_match:
		frappe.throw(
			_("{0} does not reference Sales Invoice {1}.").format(payment_entry, entry.sales_invoice)
		)

	entry.payment_entry = payment_entry
	entry.status = PAID_STATUS
	# Explicit role check above stands in for permission enforcement here: this bypasses
	# the base has_permission gate, which alone can't distinguish "System Manager/
	# Financial Manager" from any other role holding base write (e.g. Technical Approver).
	entry.flags.ignore_permissions = True
	entry.save()

	return {"ok": True, "message": _("Marked {0} as Paid.").format(entry.name)}
