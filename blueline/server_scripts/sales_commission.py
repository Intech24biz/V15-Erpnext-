import frappe
from frappe import _
from frappe.utils import flt, fmt_money, now_datetime

from blueline.blueline.doctype.sales_commission_entry.sales_commission_entry import (
	CREDIT_NOTE_ADJUSTMENT_FLAG,
	DEDUCTION_NOT_PAYABLE,
	PAYMENT_UNDONE_FLAG,
	invoice_outstanding,
)

RULE_DOCTYPE = "Sales Commission Rule"
ENTRY_DOCTYPE = "Sales Commission Entry"

COMMISSION_TYPE = "Commission"
DEDUCTION_TYPE = "Deduction"

REDUCED = "Reduced"
CANCELLED_BY_CREDIT_NOTE = "Cancelled"
DEDUCTION_CREATED = "Deduction Created"

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

# Commission not yet paid out is reduced in place by a Credit Note; paid commission gets a
# separate negative Deduction entry instead, since what was paid can't be un-paid.
UNPAID_STATUSES = {ACCRUED_STATUS, PENDING_APPROVAL_STATUS, APPROVED_STATUS}

CREDIT_NOTE_SUBMIT_SAVEPOINT = "blueline_credit_note_submit"
COMMISSION_ADJUSTMENT_FAILED = (
	"Commission could not be adjusted for this Credit Note; nothing was changed. Contact the administrator."
)


def create_commission_entries(doc, method=None):
	"""Sales Invoice `on_submit`: accrue commission for every item row that matches an
	enabled Sales Commission Rule. Matching is driven purely by item_code (+ customer)
	against the rule table — the invoice's own Sales Team table is deliberately ignored,
	so no manual sales-person selection on the invoice ever affects who is credited.
	One sale can pay several people: every rule at the first matching tier gets its own
	entry. A line with no matching rule is logged and skipped — this must never block
	the invoice submission itself.

	A Credit Note accrues nothing of its own: it adjusts the original invoice's entries
	instead (see apply_credit_note), so a return is never counted twice.
	"""
	if doc.get("is_return"):
		apply_credit_note(doc)
		# Applied straight against the original (newer ERPNext's "Update Outstanding for
		# Self" unticked), the Credit Note may itself settle what was left to pay.
		if doc.return_against:
			release_if_settled(doc.return_against)
		return

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
	commission_amount = _calculate_commission(rule, item)
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
			"commission_amount": commission_amount,
			"original_commission_amount": commission_amount,
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
	"""Payment Entry `on_submit` and `on_update_after_submit`: check every Sales Invoice it
	references (see release_if_settled). Registered on both events because Payment
	Reconciliation can update an already-submitted Payment Entry's references without
	re-firing on_submit.
	"""
	for invoice_name in {
		row.reference_name
		for row in (doc.references or [])
		if row.reference_doctype == "Sales Invoice" and row.reference_name
	}:
		release_if_settled(invoice_name)


def release_on_journal_entry(doc, method=None):
	"""Journal Entry `on_submit`: a receipt, a write-off, or the Journal Entry Payment
	Reconciliation creates to apply a Credit Note to an invoice."""
	for invoice_name in {
		row.reference_name
		for row in (doc.accounts or [])
		if row.reference_type == "Sales Invoice" and row.reference_name
	}:
		release_if_settled(invoice_name)


def release_on_ledger_update(doc, method=None):
	"""Payment Ledger Entry `on_update`: ERPNext recalculates the invoice's outstanding in
	this entry's own on_update (which runs before this hook) whenever the entry is flagged
	to, whatever document made it — so this catches routes no document hook sees."""
	if doc.against_voucher_type == "Sales Invoice" and doc.against_voucher_no and not doc.delinked:
		release_if_settled(doc.against_voucher_no)


def release_if_settled(invoice_name):
	"""Once a Sales Invoice's outstanding amount has reached zero — by a Payment Entry, a
	Journal Entry, a Credit Note applied or reconciled against it, or any mix — move its
	Accrued commission entries to "Payment Received - Pending Approval", where the
	two-person approval starts. Never while anything is still outstanding. Only Accrued
	entries move, so calling this again (several hooks fire for one payment) changes
	nothing: an entry is released once.
	"""
	invoice = frappe.db.get_value(
		"Sales Invoice", invoice_name, ["docstatus", "is_return", "outstanding_amount"], as_dict=True
	)
	if not invoice or invoice.docstatus != 1 or invoice.is_return:
		return
	if invoice_outstanding(invoice_name) > 0:
		return
	_release_entries_for_invoice(invoice_name)
	_clear_unpaid_warnings(invoice_name)


def _release_entries_for_invoice(invoice_name):
	# get_all (not get_list): these are the system's own previously-created accrual
	# records, looked up by an explicit sales_invoice + status filter rather than shown
	# as a user-facing view — unlike the rule lookup above, a permission gap here would
	# leave commission stuck in Accrued with no retry, so this is a deliberate exception
	# to the get_list rule.
	entry_names = frappe.get_all(
		ENTRY_DOCTYPE,
		filters={"sales_invoice": invoice_name, "status": ACCRUED_STATUS, "entry_type": COMMISSION_TYPE},
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


def reopen_on_payment_cancel(doc, method=None):
	"""Payment Entry `on_cancel`."""
	for invoice_name in {
		row.reference_name
		for row in (doc.references or [])
		if row.reference_doctype == "Sales Invoice" and row.reference_name
	}:
		reopen_if_unsettled(invoice_name, _("Payment Entry {0} was cancelled").format(doc.name))


def reopen_on_journal_cancel(doc, method=None):
	"""Journal Entry `on_cancel` (including the Journal Entry that applied a Credit Note)."""
	for invoice_name in {
		row.reference_name
		for row in (doc.accounts or [])
		if row.reference_type == "Sales Invoice" and row.reference_name
	}:
		reopen_if_unsettled(invoice_name, _("Journal Entry {0} was cancelled").format(doc.name))


def reopen_on_unreconcile(doc, method=None):
	"""Unreconcile Payment `on_submit`: a payment or credit taken back off the invoice."""
	for invoice_name in {
		row.reference_name
		for row in (doc.allocations or [])
		if row.reference_doctype == "Sales Invoice" and row.reference_name
	}:
		reopen_if_unsettled(
			invoice_name, _("{0} {1} was unreconciled from the invoice").format(_(doc.voucher_type), doc.voucher_no)
		)


def reopen_if_unsettled(invoice_name, reason):
	"""After a payment, credit or reconciliation is undone: if the invoice has an outstanding
	amount again, its released commission is no longer payable.

	- Payment Received - Pending Approval with neither box ticked: nothing has been decided
	  yet, so it goes back to Accrued, and release_if_settled releases it again once the
	  invoice is fully paid or credited.
	- Anything further along (a tick given, Approved, Paid): a person has already acted on
	  it, so its status is not changed. It gets a Payment Warning, shown on the form, and a
	  timeline comment; the approval guard stops any further tick or approval meanwhile.
	"""
	outstanding = invoice_outstanding(invoice_name)
	if outstanding <= 0:
		return
	amount = fmt_money(
		outstanding, currency=frappe.db.get_value("Sales Invoice", invoice_name, "currency")
	)
	entry_names = frappe.get_all(
		ENTRY_DOCTYPE,
		filters={
			"sales_invoice": invoice_name,
			"entry_type": COMMISSION_TYPE,
			"docstatus": 1,
			"status": ["in", [PENDING_APPROVAL_STATUS, APPROVED_STATUS, PAID_STATUS]],
		},
		pluck="name",
		order_by="name asc",
	)
	for entry_name in entry_names:
		entry = frappe.get_doc(ENTRY_DOCTYPE, entry_name)
		ticked = entry.approved_by_management or entry.approved_by_technical
		if entry.status == PENDING_APPROVAL_STATUS and not ticked:
			entry.status = ACCRUED_STATUS
			comment = _(
				"Moved back to Accrued: {0}, and invoice {1} has {2} outstanding again. "
				"It will be released again once the invoice is fully paid or credited."
			).format(reason, invoice_name, amount)
		else:
			state = _("already {0}").format(_(entry.status)) if entry.status != PENDING_APPROVAL_STATUS else _("already ticked")
			entry.unpaid_warning = _(
				"{0}, and invoice {1} has {2} outstanding again. This entry is {3}, so its status "
				"was not changed. Check it before any commission is paid."
			).format(reason, invoice_name, amount, state)
			comment = entry.unpaid_warning
		_save_system_change(entry, PAYMENT_UNDONE_FLAG, comment)


def _clear_unpaid_warnings(invoice_name):
	for entry_name in frappe.get_all(
		ENTRY_DOCTYPE,
		filters={"sales_invoice": invoice_name, "unpaid_warning": ["is", "set"], "docstatus": 1},
		pluck="name",
	):
		entry = frappe.get_doc(ENTRY_DOCTYPE, entry_name)
		entry.unpaid_warning = None
		_save_system_change(
			entry, PAYMENT_UNDONE_FLAG, _("Invoice {0} is fully paid or credited again: Payment Warning cleared.").format(invoice_name)
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


def mark_credit_note_savepoint(doc, method=None):
	"""Sales Invoice `before_submit` (last in the list): on a Credit Note, remember the point
	before its submission writes anything, so a failed commission adjustment can undo the
	whole approval — the Credit Note's own postings included — not just the commission."""
	if not doc.get("is_return"):
		return
	frappe.db.savepoint(CREDIT_NOTE_SUBMIT_SAVEPOINT)
	doc.flags.commission_savepoint = CREDIT_NOTE_SUBMIT_SAVEPOINT


def apply_credit_note(credit_note):
	"""Credit Note `on_submit` (reached through create_commission_entries): adjust the
	commission accrued on the original invoice in proportion to the line amount returned.

	- Accrued / Payment Received - Pending Approval / Approved: Commission Amount is reduced
	  in place. A full return cancels the entry (status Cancelled; it stays submitted so a
	  cancelled Credit Note can restore it). Approval ticks are never touched.
	- Paid: a separate negative Deduction entry is created for the same person, flagged
	  Deduct from Next Payout and linked to the Credit Note and to the paid entry. It starts
	  in Payment Received - Pending Approval and needs the usual two-person sign-off.

	Every change is written to the entry's Adjustments table and its Version history, with
	the approving user. Nothing here reads or writes any accounting record.

	All or nothing: if any part fails, everything since the Credit Note's submission began
	is rolled back (no entry partly adjusted, the Credit Note not approved), the error is
	logged, and the approval is refused.
	"""
	if not credit_note.return_against:
		return

	own_savepoint = "blueline_credit_note_commission"
	frappe.db.savepoint(own_savepoint)
	try:
		returned = _returned_amount_by_line(credit_note)
		# get_all, matching _release_entries_for_invoice: the system's own records for this
		# specific invoice, which must be adjusted whoever approved the Credit Note.
		entry_names = frappe.get_all(
			ENTRY_DOCTYPE,
			filters={
				"sales_invoice": credit_note.return_against,
				"sales_invoice_item": ["in", list(returned) or [""]],
				"entry_type": COMMISSION_TYPE,
				"docstatus": 1,
			},
			pluck="name",
			order_by="name asc",
		)
		for entry_name in entry_names:
			entry = frappe.get_doc(ENTRY_DOCTYPE, entry_name)
			_adjust_entry(entry, credit_note, returned[entry.sales_invoice_item])
	except Exception:
		traceback = frappe.get_traceback()
		frappe.db.rollback(save_point=credit_note.flags.get("commission_savepoint") or own_savepoint)
		# Deferred: an Error Log inserted now would be rolled back with the refused request.
		frappe.log_error(
			title=f"Sales Commission credit note adjustment failed: {credit_note.name}",
			message=traceback,
			reference_doctype="Sales Invoice",
			reference_name=credit_note.name,
			defer_insert=True,
		)
		frappe.throw(_(COMMISSION_ADJUSTMENT_FAILED), title=_("Credit Note Not Approved"))


def _returned_amount_by_line(credit_note):
	"""{original Sales Invoice Item name: line amount returned}. ERPNext's Return / Credit
	Note mapper links each row back to its original line; a row added by hand is matched by
	item code when that item appears on exactly one original line."""
	original_lines = frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": credit_note.return_against, "parenttype": "Sales Invoice"},
		fields=["name", "item_code"],
	)
	known = {line.name for line in original_lines}
	by_item_code = {}
	for line in original_lines:
		by_item_code.setdefault(line.item_code, []).append(line.name)

	returned = {}
	for item in credit_note.items:
		amount = -flt(item.amount)
		if amount <= 0:
			continue
		line = item.get("sales_invoice_item")
		if line not in known:
			candidates = by_item_code.get(item.item_code, [])
			line = candidates[0] if len(candidates) == 1 else None
		if not line:
			frappe.log_error(
				title=f"Sales Commission: credit note line not matched ({credit_note.name} / {item.item_code})",
				message=(
					f"Credit Note row {item.idx} ({item.item_code}) could not be matched to a line on "
					f"{credit_note.return_against}. No commission was adjusted for this row."
				),
			)
			continue
		returned[line] = returned.get(line, 0) + amount
	return returned


def _adjust_entry(entry, credit_note, returned_amount):
	line_amount = flt(entry.amount)
	if line_amount <= 0 or entry.status not in UNPAID_STATUSES | {PAID_STATUS}:
		return

	precision = entry.precision("commission_amount")
	original = flt(entry.original_commission_amount)
	if not original and not entry.adjustments:
		original = flt(entry.commission_amount)  # entry accrued before this field existed

	active = [row for row in entry.adjustments if not row.reversed]
	returned_before = sum(flt(row.returned_amount) for row in active)
	returned_now = min(flt(returned_amount), line_amount - returned_before)
	if returned_now <= 0:
		return

	# Computed from the original amount and the total returned so far, so several partial
	# Credit Notes on one line add up exactly to the original commission, with no drift.
	full_return = flt(returned_before + returned_now, precision) >= flt(line_amount, precision)
	target = original if full_return else original * (returned_before + returned_now) / line_amount
	adjustment = flt(target - sum(flt(row.adjustment_amount) for row in active), precision)

	row = {
		"credit_note": credit_note.name,
		"returned_amount": returned_now,
		"adjustment_amount": adjustment,
		"amount_before": entry.commission_amount,
		"status_before": entry.status,
		"adjusted_by": frappe.session.user,
		"adjusted_on": now_datetime(),
	}

	if entry.status == PAID_STATUS:
		deduction = _create_deduction(entry, credit_note, returned_now, adjustment)
		row.update(adjustment_type=DEDUCTION_CREATED, deduction_entry=deduction.name)
		comment = _("Commission already paid: Deduction {0} of {1} created by Credit Note {2}.").format(
			deduction.name, fmt_money(adjustment, precision), credit_note.name
		)
	elif full_return:
		entry.commission_amount = 0
		entry.status = CANCELLED_STATUS
		row.update(adjustment_type=CANCELLED_BY_CREDIT_NOTE)
		comment = _("Cancelled by Credit Note {0} (full return).").format(credit_note.name)
	else:
		entry.commission_amount = flt(flt(entry.commission_amount) - adjustment, precision)
		row.update(adjustment_type=REDUCED)
		comment = _("Commission reduced by {0} by Credit Note {1}.").format(
			fmt_money(adjustment, precision), credit_note.name
		)

	row.update(amount_after=entry.commission_amount, status_after=entry.status)
	entry.original_commission_amount = original
	entry.append("adjustments", row)
	_save_credit_note_change(entry, comment)


def _create_deduction(entry, credit_note, returned_amount, amount):
	deduction = frappe.get_doc(
		{
			"doctype": ENTRY_DOCTYPE,
			"entry_type": DEDUCTION_TYPE,
			"deduct_from_next_payout": 1,
			"credit_note": credit_note.name,
			"against_commission_entry": entry.name,
			"sales_invoice": entry.sales_invoice,
			"sales_invoice_item": entry.sales_invoice_item,
			"posting_date": credit_note.posting_date,
			"matched_sales_person": entry.matched_sales_person,
			"commission_credited_to": entry.commission_credited_to,
			"customer": entry.customer,
			"item_code": entry.item_code,
			"company": entry.company,
			"rate": entry.rate,
			"amount": -returned_amount,
			"commission_rule": entry.commission_rule,
			"commission_type": entry.commission_type,
			"commission_amount": -amount,
			"original_commission_amount": -amount,
			"status": ACCRUED_STATUS,
		}
	)
	deduction.insert(ignore_permissions=True)
	deduction.submit()
	# Straight on to Pending Approval, by the same workflow transition a fully paid invoice's
	# entries take, so the existing pending-approval notification and the two-person
	# sign-off (two different users, locked once Approved) apply to it unchanged.
	deduction.status = PENDING_APPROVAL_STATUS
	deduction.save()
	return deduction


def reverse_credit_note(doc, method=None):
	"""Sales Invoice `on_cancel`: a cancelled Credit Note gives back exactly what it took —
	reduced amounts are restored, entries it cancelled return to their previous status,
	and the Deduction entries it created are cancelled. Its Adjustments rows stay, marked
	Reversed. Unlike accrual this blocks on failure: a cancelled Credit Note must not leave
	commission reduced with nothing behind it.
	"""
	if not doc.get("is_return"):
		return

	entry_names = frappe.get_all(
		"Sales Commission Adjustment",
		filters={"parenttype": ENTRY_DOCTYPE, "credit_note": doc.name, "reversed": 0},
		pluck="parent",
	)
	for entry_name in sorted(set(entry_names)):
		try:
			_reverse_entry(frappe.get_doc(ENTRY_DOCTYPE, entry_name), doc)
		except Exception:
			frappe.log_error(
				title=f"Sales Commission credit note reversal failed: {entry_name}",
				message=frappe.get_traceback(),
			)
			frappe.throw(
				_("Could not restore Sales Commission Entry {0} for this Credit Note. See Error Log.").format(
					entry_name
				)
			)

	# The Adjustments rows and Deduction entries above still link to this Credit Note by
	# design (they are its audit trail), which Frappe would otherwise treat as blocking.
	doc.ignore_linked_doctypes = (*(doc.get("ignore_linked_doctypes") or ()), ENTRY_DOCTYPE)

	# Cancelling a Credit Note that settled the invoice can leave it unpaid again.
	if doc.return_against:
		reopen_if_unsettled(doc.return_against, _("Credit Note {0} was cancelled").format(doc.name))


def _reverse_entry(entry, credit_note):
	precision = entry.precision("commission_amount")
	restored = []
	for row in entry.adjustments:
		if row.credit_note != credit_note.name or row.reversed:
			continue
		if row.adjustment_type == DEDUCTION_CREATED:
			_cancel_deduction(row.deduction_entry, credit_note)
		else:
			entry.commission_amount = flt(flt(entry.commission_amount) + flt(row.adjustment_amount), precision)
		row.reversed = 1
		row.reversed_by = frappe.session.user
		row.reversed_on = now_datetime()
		restored.append(row)

	if entry.status == CANCELLED_STATUS and flt(entry.commission_amount) > 0:
		# No longer fully returned: back to the status it had when a Credit Note cancelled it.
		cancelling = [row for row in entry.adjustments if row.adjustment_type == CANCELLED_BY_CREDIT_NOTE]
		entry.status = cancelling[-1].status_before

	_save_credit_note_change(
		entry, _("Credit Note {0} was cancelled: its adjustment was reversed.").format(credit_note.name)
	)


def _cancel_deduction(deduction_name, credit_note):
	deduction = frappe.get_doc(ENTRY_DOCTYPE, deduction_name)
	if deduction.docstatus != 1:
		return
	deduction.flags.ignore_permissions = True
	# The paid entry's Adjustments row links here: that's the audit trail, not a dependency.
	deduction.ignore_linked_doctypes = (ENTRY_DOCTYPE,)
	deduction.cancel()
	deduction.add_comment(
		"Info", _("Cancelled automatically: Credit Note {0} was cancelled.").format(credit_note.name)
	)


def _save_system_change(entry, flag, comment):
	"""A status / Payment Warning change made by the system after an undone payment. The
	commission workflow has no transition back to Accrued, so only this save skips it."""
	entry.flags.ignore_permissions = True
	entry.flags[flag] = True
	entry.save(ignore_version=False)
	entry.add_comment("Info", comment)


def _save_credit_note_change(entry, comment):
	"""The single place a Credit Note writes to an existing entry. Commission Amount and the
	Adjustments table are locked after submit for everyone; only this save lifts that lock
	(and the commission workflow, which has no Cancelled state). Version history is kept."""
	entry.flags.ignore_permissions = True
	entry.flags.ignore_validate_update_after_submit = True
	entry.flags[CREDIT_NOTE_ADJUSTMENT_FLAG] = True
	# A reversal's rows point at the Credit Note and Deduction it has just cancelled, which
	# Frappe's link check refuses; every value saved here is set by this module.
	entry.flags.ignore_links = True
	entry.save(ignore_version=False)
	entry.add_comment("Info", comment)


def guard_payout_cancel(doc, method=None):
	"""Payment Entry `before_cancel`: a payout that Paid commission entries point to can't be
	cancelled. ERPNext's own link check would refuse too, but only after on_cancel and with a
	generic message; this names the entries and refuses before anything is reversed."""
	paid = frappe.get_all(
		ENTRY_DOCTYPE,
		filters={"payment_entry": doc.name, "docstatus": 1, "status": PAID_STATUS},
		pluck="name",
		order_by="name asc",
	)
	if paid:
		frappe.throw(
			_(
				"Payment Entry {0} paid out commission entries {1}, which are marked Paid. "
				"It can't be cancelled while they point to it."
			).format(frappe.bold(doc.name), ", ".join(paid)),
			title=_("Commission Payout"),
		)


@frappe.whitelist()
def mark_commission_entry_paid(commission_entry, payment_entry):
	"""Link an Approved commission entry to the Payment Entry (type Pay) that paid it out and
	mark it Paid, in one step. The form does the same in two (pick Payment Entry, Update,
	then Actions > Mark as Paid); either way the rules are enforced by the entry itself
	(SalesCommissionEntry.validate_payment_link). No automatic bank-file matching.
	"""
	if not (MARK_PAID_ROLES & set(frappe.get_roles())):
		frappe.throw(
			_("Only System Manager or Financial Manager can mark a commission entry as Paid."),
			frappe.PermissionError,
		)

	entry = frappe.get_doc(ENTRY_DOCTYPE, commission_entry)

	if entry.status != APPROVED_STATUS:
		frappe.throw(_("Only an Approved commission entry can be marked as Paid."))

	if entry.entry_type == DEDUCTION_TYPE:
		# A deduction is settled by netting it off a later payout, which is not built yet.
		frappe.throw(_(DEDUCTION_NOT_PAYABLE).format(entry.name))

	entry.payment_entry = payment_entry
	entry.status = PAID_STATUS
	# Explicit role check above stands in for permission enforcement here: this bypasses
	# the base has_permission gate, which alone can't distinguish "System Manager/
	# Financial Manager" from any other role holding base write (e.g. Technical Approver).
	entry.flags.ignore_permissions = True
	entry.save()

	return {"ok": True, "message": _("Marked {0} as Paid.").format(entry.name)}
