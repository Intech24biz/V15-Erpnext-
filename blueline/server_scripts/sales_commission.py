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
CANCELLED_STATUS = "Cancelled"

# Cancelling the invoice is safe to cascade automatically: no sign-off or payout exists yet.
AUTO_CANCEL_STATUSES = {ACCRUED_STATUS, PENDING_APPROVAL_STATUS}
# Cancelling the invoice is blocked instead: money and/or approval are already committed,
# so unwinding this needs a human finance decision, not a silent cascade.
BLOCK_CANCEL_STATUSES = {APPROVED_STATUS, PAID_STATUS}

# Same roles that hold permlevel-3 write on Sales Commission Entry (status/payment_entry).
MARK_PAID_ROLES = {"System Manager", "Financial Manager"}


def create_commission_entries(doc, method=None):
	"""Sales Invoice `on_submit`: accrue commission for every item row that matches an
	enabled Sales Commission Rule. Matching is driven purely by item_code (+ customer)
	against the rule table — the invoice's own Sales Team table is deliberately ignored,
	so no manual sales-person selection on the invoice ever affects who is credited.
	One sale can pay several people: every rule at the first matching tier gets its own
	entry. A line with no matching rule is logged and skipped — this must never block
	the invoice submission itself.
	"""
	for item in doc.items:
		try:
			_process_line(doc, item)
		except Exception:
			frappe.log_error(
				title=f"Sales Commission accrual failed: {doc.name} / {item.item_code}",
				message=frappe.get_traceback(),
			)


def _process_line(invoice, item):
	rules = _find_matching_rules(invoice.company, invoice.customer, item.item_code)
	if not rules:
		frappe.log_error(
			title=f"Sales Commission: no matching rule ({invoice.name} / {item.item_code})",
			message=(
				f"No enabled Sales Commission Rule matched Company={invoice.company}, "
				f"Customer={invoice.customer}, Item={item.item_code}. "
				"No commission was accrued for this invoice line."
			),
		)
		return

	by_person = {}
	for rule in rules:
		by_person.setdefault(rule.sales_person, []).append(rule)

	for sales_person, person_rules in by_person.items():
		if len(person_rules) > 1:
			# Sales Commission Rule.validate() forbids this (one enabled rule per sales
			# person + customer + item + company), so reaching here is a data bug. There is
			# no correct rate to pick, so this person is skipped; other payees still accrue.
			frappe.log_error(
				title=f"Sales Commission: duplicate rules for {sales_person} ({invoice.name} / {item.item_code})",
				message=(
					f"{len(person_rules)} enabled Sales Commission Rules for {sales_person} matched "
					f"Company={invoice.company}, Customer={invoice.customer}, Item={item.item_code} at the "
					f"same priority: {', '.join(r.name for r in person_rules)}. This violates the rule "
					"uniqueness check. No commission was accrued for this person on this line."
				),
			)
			continue
		try:
			_create_entry(invoice, item, person_rules[0])
		except Exception:
			frappe.log_error(
				title=f"Sales Commission accrual failed: {invoice.name} / {item.item_code} / {sales_person}",
				message=frappe.get_traceback(),
			)


def _create_entry(invoice, item, rule):
	entry = frappe.get_doc(
		{
			"doctype": ENTRY_DOCTYPE,
			"sales_invoice": invoice.name,
			"sales_invoice_item": item.name,
			"posting_date": invoice.posting_date,
			"matched_sales_person": rule.sales_person,
			"commission_credited_to": resolve_commission_leader(rule.sales_person),
			"customer": invoice.customer,
			"item_code": item.item_code,
			"company": invoice.company,
			"qty": item.qty,
			"rate": item.rate,
			"amount": item.amount,
			"commission_rule": rule.name,
			"commission_type": rule.commission_type,
			"commission_amount": _calculate_commission(rule, item),
			"status": ACCRUED_STATUS,
		}
	)
	# System-driven accrual: the invoice-submitting user need not hold Sales Commission
	# Entry create/write permission themselves.
	entry.insert(ignore_permissions=True)
	entry.submit()


def _find_matching_rules(company, customer, item_code):
	"""(customer+item_code) > (item_code only) > (customer only) > (catch-all: blank
	customer and item_code), all scoped to company. Returns every rule at the first tier
	that has any match — one per payee when a sale pays several people.
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
			filters={"company": company, "enabled": 1, **tier},
			fields=["name", "sales_person", "commission_type", "rate"],
			order_by="sales_person asc, name asc",
			limit_page_length=0,
		)
		if rules:
			return rules
	return []


def resolve_commission_leader(sales_person):
	"""Commission is credited to the rep's nearest group: their direct parent_sales_person
	if that parent is a group (is_group = 1), otherwise the rep themselves. Deliberately
	one level only — a sub-team lead keeps and distributes commission for their own
	sub-team, so this must not roll further up to the team above them.
	"""
	parent = frappe.db.get_value("Sales Person", sales_person, "parent_sales_person")
	if parent and frappe.db.get_value("Sales Person", parent, "is_group"):
		return parent
	return sales_person


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


def guard_commission_entries_on_cancel(doc, method=None):
	"""Sales Invoice `before_cancel`: nothing else propagates an invoice cancellation to
	its commission entries on its own, so without this a cancelled invoice could leave
	an Approved or even Paid commission entry behind with no trace back to a live
	invoice. Runs before the cancel is persisted, so a throw here aborts the invoice
	cancellation entirely.

	- Accrued / Payment Received - Pending Approval: no sign-off or payout exists yet,
	  so these are cancelled automatically along with the invoice.
	- Approved / Paid: money and/or approval are already committed. Cancelling those
	  silently would desync the commission record from a ledger event that no longer
	  exists, so this blocks the invoice cancellation instead and requires a human
	  finance decision first.
	"""
	# get_all, matching _release_entries_for_invoice above: these are the system's own
	# records for this specific invoice, not a user-facing filtered view.
	entries = frappe.get_all(
		ENTRY_DOCTYPE,
		filters={"sales_invoice": doc.name, "docstatus": 1},
		fields=["name", "status"],
	)
	if not entries:
		return

	blocking = [e.name for e in entries if e.status in BLOCK_CANCEL_STATUSES]
	if blocking:
		frappe.throw(
			_(
				"Cannot cancel {0}: linked Sales Commission Entries {1} have already been "
				"approved or paid. Resolve those commission entries first."
			).format(doc.name, ", ".join(blocking))
		)

	for entry in entries:
		if entry.status not in AUTO_CANCEL_STATUSES:
			continue
		try:
			commission_entry = frappe.get_doc(ENTRY_DOCTYPE, entry.name)
			commission_entry.flags.ignore_permissions = True
			commission_entry.cancel()
		except Exception:
			frappe.log_error(
				title=f"Sales Commission auto-cancel failed: {entry.name}",
				message=frappe.get_traceback(),
			)
			# Don't leave the invoice cancelled with a commission entry that failed to
			# follow it — better to block and surface the problem than to silently drift.
			frappe.throw(
				_("Could not cancel linked Sales Commission Entry {0}. See Error Log.").format(
					entry.name
				)
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
