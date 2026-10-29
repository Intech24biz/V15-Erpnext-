"""Credit Note commission adjustment (client rule agreed 2026-10-29).

Unpaid commission (Accrued, Payment Received - Pending Approval, Approved) is reduced in
proportion to the returned amount, and cancelled on a full return. Paid commission gets a
separate negative Deduction entry. Cancelling the Credit Note undoes all of it. None of it
touches the ledger."""

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
from frappe.utils import flt

from blueline.blueline.page.sales_commission_register.sales_commission_register import get_entries
from blueline.server_scripts import sales_commission
from blueline.server_scripts.sales_commission import mark_commission_entry_paid
from blueline.tests.utils import (
	FINANCIAL_MANAGER,
	GI_MANAGEMENT,
	GI_SALES,
	SYSTEM_MANAGER,
	BluelineTestCase,
	act,
	approved_invoice,
	approved_payment_for,
	approved_payout,
	as_user,
	commission_entries,
	reload,
	update_entry,
	workflow,
)

SCE = "Sales Commission Entry"
CN_ONLY = "can only be set to or from"
NOT_ALLOWED_AFTER_SUBMIT = "Not allowed to change"
LOCKED = "cannot be changed once the entry is"
SAME_USER = "must be given by two different users"
ADJUSTMENT_FAILED = (
	"Commission could not be adjusted for this Credit Note; nothing was changed. Contact the administrator."
)
TECHNICAL_APPROVER = GI_MANAGEMENT

# approved_invoice() sells 2 x COMMISSION_ITEM at 1000: three payees on one line.
FULL = {"W.B.Prasanna": 130, "M.Madusha Darshani": 130, "M M M M PARIS": 60}
HALF = {person: amount / 2 for person, amount in FULL.items()}

LEDGER_TABLES = {
	# table: column naming the voucher a row belongs to
	"GL Entry": "voucher_no",
	"Payment Ledger Entry": "voucher_no",
	"Journal Entry": "name",
	"Journal Entry Account": "parent",
	"Payment Entry": "name",
	"Payment Entry Reference": "parent",
}


def credit_note(invoice, qty=None, creator=GI_SALES, approver=SYSTEM_MANAGER):
	"""Credit Note against `invoice` through the real Return mapper and approval workflow.
	`qty` (units returned per line) makes it a partial return."""
	with as_user(creator):
		cn = make_sales_return(invoice.name)
		if qty is not None:
			for item in cn.items:
				item.qty = -qty
		cn.insert()
	workflow(cn, "Send for Approval", creator)
	workflow(cn, "Approve", approver)
	return reload(cn)


def cancel(cn):
	act(SYSTEM_MANAGER, reload(cn).cancel)
	return reload(cn)


def entries_by_person(invoice, entry_type="Commission"):
	return {
		e.matched_sales_person: frappe.get_doc(SCE, e.name)
		for e in commission_entries(invoice.name, entry_type=entry_type)
	}


def amounts(invoice, entry_type="Commission"):
	return {p: flt(e.commission_amount) for p, e in entries_by_person(invoice, entry_type).items()}


def approve(entry_name):
	update_entry(entry_name, FINANCIAL_MANAGER, approved_by_management=1)
	update_entry(entry_name, TECHNICAL_APPROVER, approved_by_technical=1)


def paid_invoice_with_mixed_statuses():
	"""Fully paid invoice whose three entries are Paid (Prasanna), Approved (Darshani) and
	Payment Received - Pending Approval (Paris)."""
	invoice = approved_invoice()
	approved_payment_for(invoice)
	by_person = entries_by_person(invoice)
	approve(by_person["W.B.Prasanna"].name)
	payout = approved_payout(by_person["W.B.Prasanna"].commission_amount)
	act(FINANCIAL_MANAGER, mark_commission_entry_paid, by_person["W.B.Prasanna"].name, payout.name)
	approve(by_person["M.Madusha Darshani"].name)
	statuses = {p: e.status for p, e in entries_by_person(invoice).items()}
	assert statuses == {
		"W.B.Prasanna": "Paid",
		"M.Madusha Darshani": "Approved",
		"M M M M PARIS": "Payment Received - Pending Approval",
	}, statuses
	return invoice


def ledger_snapshot(exclude_vouchers=()):
	snapshot = {}
	for table, voucher_column in LEDGER_TABLES.items():
		rows = frappe.db.sql(f"select name, modified, {voucher_column} from `tab{table}`")
		snapshot[table] = {(name, modified) for name, modified, voucher in rows if voucher not in exclude_vouchers}
	return snapshot


class TestUnpaidCommission(BluelineTestCase):
	def test_full_return_of_unpaid_entry_cancels_it(self):
		invoice = approved_invoice()
		cn = credit_note(invoice)

		for person, entry in entries_by_person(invoice).items():
			with self.subTest(person=person):
				self.assertEqual((entry.docstatus, entry.status), (1, "Cancelled"))
				self.assertEqual(flt(entry.commission_amount), 0)
				self.assertEqual(flt(entry.original_commission_amount), FULL[person])
				[row] = entry.adjustments
				self.assertEqual((row.credit_note, row.adjustment_type, row.reversed), (cn.name, "Cancelled", 0))
				self.assertEqual((flt(row.amount_before), flt(row.amount_after)), (FULL[person], 0))
				self.assertEqual((row.status_before, row.status_after), ("Accrued", "Cancelled"))
				self.assertEqual(row.adjusted_by, SYSTEM_MANAGER)  # the user who approved the Credit Note
		self.assertEqual(commission_entries(invoice.name, entry_type="Deduction"), [])

	def test_partial_return_of_unpaid_entry_reduces_it_in_proportion(self):
		invoice = approved_invoice()
		cn = credit_note(invoice, qty=1)

		self.assertEqual(amounts(invoice), HALF)
		for person, entry in entries_by_person(invoice).items():
			with self.subTest(person=person):
				self.assertEqual(entry.status, "Accrued")
				self.assertEqual(flt(entry.original_commission_amount), FULL[person])
				[row] = entry.adjustments
				self.assertEqual((row.adjustment_type, flt(row.adjustment_amount)), ("Reduced", HALF[person]))
				self.assertEqual(flt(row.returned_amount), 1000)
				# No silent edit: a Version and a comment name the change.
				version = frappe.get_last_doc("Version", filters={"ref_doctype": SCE, "docname": entry.name})
				self.assertIn("commission_amount", version.data)
				self.assertEqual(version.owner, SYSTEM_MANAGER)
				self.assertTrue(
					frappe.db.exists(
						"Comment",
						{"reference_doctype": SCE, "reference_name": entry.name, "content": ["like", f"%{cn.name}%"]},
					)
				)

	def test_two_partial_returns_add_up_to_a_full_return(self):
		invoice = approved_invoice()
		credit_note(invoice, qty=1)
		credit_note(invoice, qty=1)
		for person, entry in entries_by_person(invoice).items():
			with self.subTest(person=person):
				self.assertEqual((entry.status, flt(entry.commission_amount)), ("Cancelled", 0))
				self.assertEqual([r.adjustment_type for r in entry.adjustments], ["Reduced", "Cancelled"])
				self.assertEqual(sum(flt(r.adjustment_amount) for r in entry.adjustments), FULL[person])

	def test_return_of_approved_but_unpaid_entry(self):
		invoice = approved_invoice()
		approved_payment_for(invoice)
		target = entries_by_person(invoice)["W.B.Prasanna"]
		approve(target.name)
		self.assertEqual(reload(target).status, "Approved")

		credit_note(invoice, qty=1)
		entry = reload(target)
		self.assertEqual((entry.status, flt(entry.commission_amount)), ("Approved", 65))
		# The approvals themselves are untouched by the system adjustment.
		self.assertEqual((entry.approved_by_management, entry.approved_by_technical), (1, 1))
		self.assertEqual((entry.management_approved_by, entry.technical_approved_by), (FINANCIAL_MANAGER, TECHNICAL_APPROVER))

		credit_note(invoice, qty=1)
		entry = reload(target)
		self.assertEqual((entry.status, flt(entry.commission_amount)), ("Cancelled", 0))
		self.assertEqual(entry.adjustments[-1].status_before, "Approved")
		self.assertEqual(commission_entries(invoice.name, entry_type="Deduction"), [])


class TestPaidCommission(BluelineTestCase):
	def test_return_of_paid_entry_creates_a_deduction(self):
		invoice = paid_invoice_with_mixed_statuses()
		paid = entries_by_person(invoice)["W.B.Prasanna"]
		cn = credit_note(invoice, qty=1)

		paid = reload(paid)
		self.assertEqual((paid.status, flt(paid.commission_amount)), ("Paid", 130), "paid commission must not change")
		[row] = paid.adjustments
		self.assertEqual(row.adjustment_type, "Deduction Created")

		[deduction] = entries_by_person(invoice, "Deduction").values()
		self.assertEqual(row.deduction_entry, deduction.name)
		self.assertEqual(flt(deduction.commission_amount), -65)
		self.assertEqual(
			(deduction.entry_type, deduction.deduct_from_next_payout, deduction.credit_note, deduction.against_commission_entry),
			("Deduction", 1, cn.name, paid.name),
		)
		self.assertEqual(
			(deduction.matched_sales_person, deduction.commission_credited_to),
			(paid.matched_sales_person, paid.commission_credited_to),
		)
		self.assertEqual((deduction.docstatus, deduction.status), (1, "Payment Received - Pending Approval"))
		self.assertEqual((deduction.approved_by_management, deduction.approved_by_technical), (0, 0))

	def test_deduction_shows_on_the_register_as_outstanding(self):
		invoice = paid_invoice_with_mixed_statuses()
		credit_note(invoice, qty=1)
		data = act(FINANCIAL_MANAGER, get_entries, company=invoice.company)

		[row] = [d for d in data["deductions"] if d["commission_credited_to"] == "W Chaminda Priyalal"]
		self.assertEqual(flt(row["amount"]), -65)
		self.assertEqual(len(row["entries"]), 1)
		# Kept out of the status totals, so nothing is netted silently there.
		listed = {e.name: e for e in data["entries"]}
		self.assertIn(row["entries"][0]["name"], listed)
		accrued_total = sum(
			flt(e.commission_amount) for e in data["entries"] if e.status == "Accrued" and e.entry_type == "Commission"
		)
		self.assertAlmostEqual(flt(data["summary"]["Accrued"]["commission_amount"]), accrued_total)

	def test_deduction_cannot_be_marked_paid(self):
		invoice = paid_invoice_with_mixed_statuses()
		credit_note(invoice, qty=1)
		[deduction] = entries_by_person(invoice, "Deduction").values()
		approve(deduction.name)
		self.assertEqual(reload(deduction).status, "Approved")
		payment = frappe.get_value("Sales Commission Entry", entries_by_person(invoice)["W.B.Prasanna"].name, "payment_entry")
		self.assertRefused(lambda: act(FINANCIAL_MANAGER, mark_commission_entry_paid, deduction.name, payment), "is a deduction")

	def test_deduction_is_not_released_by_a_payment(self):
		invoice = paid_invoice_with_mixed_statuses()
		credit_note(invoice, qty=1)
		[deduction] = entries_by_person(invoice, "Deduction").values()
		# Deductions start Pending Approval now; an Accrued one (e.g. made by hand) must
		# still never be released by a payment on the invoice.
		frappe.db.set_value(SCE, deduction.name, "status", "Accrued")
		sales_commission._release_entries_for_invoice(invoice.name)
		self.assertEqual(reload(deduction).status, "Accrued")


class TestDeductionApproval(BluelineTestCase):
	"""A deduction gets the same two-person sign-off as commission."""

	def deduction(self):
		invoice = paid_invoice_with_mixed_statuses()
		credit_note(invoice, qty=1)
		[deduction] = entries_by_person(invoice, "Deduction").values()
		return invoice, deduction

	def test_one_person_cannot_approve_a_deduction(self):
		_, deduction = self.deduction()
		self.assertRefused(
			lambda: update_entry(deduction.name, SYSTEM_MANAGER, approved_by_management=1, approved_by_technical=1),
			SAME_USER,
		)
		update_entry(deduction.name, SYSTEM_MANAGER, approved_by_technical=1)
		self.assertRefused(lambda: update_entry(deduction.name, SYSTEM_MANAGER, approved_by_management=1), SAME_USER)
		self.assertRefused(lambda: workflow(reload(deduction), "Approve", SYSTEM_MANAGER), "Both approvals are required")
		self.assertEqual(reload(deduction).status, "Payment Received - Pending Approval")

	def test_wrong_role_ticks_are_refused_on_a_deduction(self):
		_, deduction = self.deduction()
		self.assertRefused(
			lambda: update_entry(deduction.name, TECHNICAL_APPROVER, approved_by_management=1),
			"You don't have permission to change",
		)

	def test_two_different_people_approve_it_and_it_is_then_locked(self):
		_, deduction = self.deduction()
		update_entry(deduction.name, FINANCIAL_MANAGER, approved_by_management=1)
		self.assertEqual(reload(deduction).status, "Payment Received - Pending Approval")
		update_entry(deduction.name, TECHNICAL_APPROVER, approved_by_technical=1)
		deduction = reload(deduction)
		self.assertEqual(deduction.status, "Approved")
		self.assertEqual(
			(deduction.management_approved_by, deduction.technical_approved_by), (FINANCIAL_MANAGER, TECHNICAL_APPROVER)
		)
		self.assertEqual(flt(deduction.commission_amount), -65)
		self.assertRefused(lambda: update_entry(deduction.name, FINANCIAL_MANAGER, approved_by_management=0), LOCKED)
		self.assertRefused(lambda: update_entry(deduction.name, SYSTEM_MANAGER, approved_by_technical=0), LOCKED)

	def test_approved_unsettled_deduction_stays_outstanding_on_the_register(self):
		invoice, deduction = self.deduction()
		approve(deduction.name)
		data = act(FINANCIAL_MANAGER, get_entries, company=invoice.company)
		[row] = [d for d in data["deductions"] if d["commission_credited_to"] == "W Chaminda Priyalal"]
		self.assertEqual(flt(row["amount"]), -65)
		self.assertEqual([(e["name"], e["status"]) for e in row["entries"]], [(deduction.name, "Approved")])
		# The Approved status total is commission only; the approved deduction isn't netted into it.
		approved = [e for e in data["entries"] if e.status == "Approved" and e.entry_type == "Commission"]
		self.assertAlmostEqual(
			flt(data["summary"]["Approved"]["commission_amount"]), sum(flt(e.commission_amount) for e in approved)
		)

	def test_cancelling_the_credit_note_cancels_an_approved_deduction(self):
		invoice, deduction = self.deduction()
		approve(deduction.name)
		cancel(frappe.get_doc("Sales Invoice", deduction.credit_note))
		deduction = reload(deduction)
		self.assertEqual((deduction.docstatus, deduction.status), (2, "Cancelled"))
		data = act(FINANCIAL_MANAGER, get_entries, company=invoice.company)
		self.assertNotIn(deduction.name, [e["name"] for d in data["deductions"] for e in d["entries"]])


class TestAdjustmentFailure(BluelineTestCase):
	"""A failed adjustment refuses the Credit Note approval and leaves nothing half-done."""

	def entry_state(self, invoice):
		rows = frappe.db.sql(
			"""select name, docstatus, status, commission_amount, original_commission_amount, modified
			from `tabSales Commission Entry` where sales_invoice = %s order by name""",
			invoice.name,
		)
		names = [r[0] for r in rows] or [""]
		return (
			rows,
			frappe.db.count("Sales Commission Adjustment", {"parent": ["in", names]}),
			frappe.db.count("Version", {"ref_doctype": SCE, "docname": ["in", names]}),
			frappe.db.count("Comment", {"reference_doctype": SCE, "reference_name": ["in", names]}),
		)

	def queued_error_logs(self, credit_note_name):
		"""Error Log records deferred to Redis (written by the scheduler after the request);
		removed again so the test leaves nothing behind."""
		key = "insert_queue_for_Error Log"  # frappe.deferred_insert's queue; the wrapper adds the site prefix
		mine = [
			r
			for r in frappe.cache.lrange(key, 0, -1)
			if credit_note_name.encode() in r and b"forced commission adjustment failure" in r
		]
		for r in mine:
			frappe.cache.lrem(frappe.cache.make_key(key), 0, r)  # raw redis method: no prefixing
		return mine

	def test_forced_failure_leaves_entries_and_credit_note_unchanged(self):
		invoice = paid_invoice_with_mixed_statuses()
		with as_user(GI_SALES):
			cn = make_sales_return(invoice.name)
			cn.insert()
		workflow(cn, "Send for Approval", GI_SALES)
		before_entries = self.entry_state(invoice)
		before_cn = frappe.db.get_value("Sales Invoice", cn.name, ["docstatus", "workflow_state", "status"])
		before_ledger = ledger_snapshot()

		# The first entry (Paid: a deduction is created) is adjusted and saved normally,
		# then the second one fails.
		real = sales_commission._adjust_entry
		calls = []

		def adjust(entry, credit_note, returned):
			calls.append(entry.name)
			if len(calls) == 2:
				raise RuntimeError("forced commission adjustment failure")
			return real(entry, credit_note, returned)

		sales_commission._adjust_entry = adjust
		try:
			self.assertRefused(lambda: workflow(cn, "Approve", SYSTEM_MANAGER), ADJUSTMENT_FAILED)
		finally:
			sales_commission._adjust_entry = real
		self.assertEqual(len(calls), 2)

		# Checked straight away, without the extra rollback a web request would add.
		self.assertEqual(self.entry_state(invoice), before_entries)
		self.assertEqual(commission_entries(invoice.name, entry_type="Deduction"), [])
		self.assertEqual(
			frappe.db.get_value("Sales Invoice", cn.name, ["docstatus", "workflow_state", "status"]), before_cn
		)
		self.assertEqual(before_cn[:2], (0, "Pending Approval"))
		self.assertEqual(ledger_snapshot(), before_ledger, "the Credit Note's own postings are undone too")
		self.assertEqual(len(self.queued_error_logs(cn.name)), 1, "the Error Log must survive the rollback")

		# Once the cause is gone, the same Credit Note approves and adjusts normally.
		workflow(cn, "Approve", SYSTEM_MANAGER)
		self.assertEqual(reload(cn).docstatus, 1)
		self.assertEqual(entries_by_person(invoice)["M M M M PARIS"].status, "Cancelled")
		self.assertEqual(len(commission_entries(invoice.name, entry_type="Deduction")), 1)


class TestSeveralPayees(BluelineTestCase):
	def test_each_payee_is_adjusted_by_their_own_status(self):
		invoice = paid_invoice_with_mixed_statuses()
		cn = credit_note(invoice)

		by_person = entries_by_person(invoice)
		self.assertEqual((by_person["W.B.Prasanna"].status, flt(by_person["W.B.Prasanna"].commission_amount)), ("Paid", 130))
		self.assertEqual(by_person["M.Madusha Darshani"].status, "Cancelled")
		self.assertEqual(by_person["M M M M PARIS"].status, "Cancelled")

		deductions = entries_by_person(invoice, "Deduction")
		self.assertEqual(set(deductions), {"W.B.Prasanna"}, "only paid commission gets a deduction")
		self.assertEqual(flt(deductions["W.B.Prasanna"].commission_amount), -130)
		self.assertEqual(commission_entries(cn.name), [], "a Credit Note accrues no commission of its own")

	def test_a_credit_note_creates_no_negative_accrued_entries(self):
		"""Replaces the old behaviour (negative Accrued entries on the Credit Note)."""
		invoice = approved_invoice()
		before = frappe.db.count(SCE)
		cn = credit_note(invoice, qty=1)
		self.assertEqual(commission_entries(cn.name), [])
		self.assertEqual(frappe.db.count(SCE), before)
		self.assertEqual(frappe.db.count(SCE, {"commission_amount": ["<", 0], "entry_type": "Commission"}), 0)


class TestCreditNoteCancellation(BluelineTestCase):
	def test_cancelling_the_credit_note_restores_everything(self):
		invoice = paid_invoice_with_mixed_statuses()
		before = {p: (e.status, flt(e.commission_amount)) for p, e in entries_by_person(invoice).items()}
		ticks = {p: (e.management_approved_by, e.technical_approved_by) for p, e in entries_by_person(invoice).items()}

		cn = cancel(credit_note(invoice))
		self.assertEqual(cn.docstatus, 2)

		after = entries_by_person(invoice)
		self.assertEqual({p: (e.status, flt(e.commission_amount)) for p, e in after.items()}, before)
		self.assertEqual({p: (e.management_approved_by, e.technical_approved_by) for p, e in after.items()}, ticks)
		for person, entry in after.items():
			with self.subTest(person=person):
				[row] = entry.adjustments
				self.assertEqual((row.reversed, row.reversed_by), (1, SYSTEM_MANAGER))

		[deduction] = entries_by_person(invoice, "Deduction").values()
		self.assertEqual((deduction.docstatus, deduction.status), (2, "Cancelled"))

	def test_cancelling_a_partial_credit_note_restores_the_amount(self):
		invoice = approved_invoice()
		cn = credit_note(invoice, qty=1)
		cancel(cn)
		self.assertEqual(amounts(invoice), FULL)
		self.assertTrue(all(e.status == "Accrued" for e in entries_by_person(invoice).values()))

	def test_cancelling_the_first_of_two_credit_notes(self):
		invoice = approved_invoice()
		first = credit_note(invoice, qty=1)
		credit_note(invoice, qty=1)
		self.assertTrue(all(e.status == "Cancelled" for e in entries_by_person(invoice).values()))

		cancel(first)
		self.assertEqual(amounts(invoice), HALF)  # what the second Credit Note left
		self.assertTrue(all(e.status == "Accrued" for e in entries_by_person(invoice).values()))


class TestAdjustmentLock(BluelineTestCase):
	"""The Credit Note path is the only way in; people's lock on submitted entries holds."""

	def test_people_cannot_change_the_amount_or_the_adjustments(self):
		invoice = approved_invoice()
		credit_note(invoice, qty=1)
		entry = entries_by_person(invoice)["W.B.Prasanna"]
		for user in (SYSTEM_MANAGER, FINANCIAL_MANAGER, "Administrator"):
			with self.subTest(user=user):
				self.assertRefused(lambda: update_entry(entry.name, user, commission_amount=130), NOT_ALLOWED_AFTER_SUBMIT)
				self.assertRefused(
					lambda: update_entry(entry.name, user, original_commission_amount=1), NOT_ALLOWED_AFTER_SUBMIT
				)
		with as_user(SYSTEM_MANAGER):
			doc = reload(entry)
			doc.adjustments[0].adjustment_amount = 0
			self.assertRefused(doc.save, NOT_ALLOWED_AFTER_SUBMIT)
		self.assertEqual(flt(reload(entry).commission_amount), 65)

	def test_people_cannot_cancel_or_restore_an_entry_by_status(self):
		invoice = approved_invoice()
		approved_payment_for(invoice)
		target = entries_by_person(invoice)["W.B.Prasanna"]
		approve(target.name)
		for user in (FINANCIAL_MANAGER, SYSTEM_MANAGER):
			with self.subTest(user=user, change="Approved -> Cancelled"):
				self.assertRefused(lambda: update_entry(target.name, user, status="Cancelled"), CN_ONLY)
		with as_user("Administrator"):
			doc = reload(target)
			doc.status = "Cancelled"
			doc.flags.ignore_permissions = True
			self.assertRefused(doc.save, CN_ONLY)

		credit_note(invoice)
		self.assertEqual(reload(target).status, "Cancelled")
		for user in (FINANCIAL_MANAGER, SYSTEM_MANAGER):
			with self.subTest(user=user, change="Cancelled -> Approved"):
				self.assertRefused(lambda: update_entry(target.name, user, status="Approved"), CN_ONLY)
		self.assertRefused(lambda: update_entry(target.name, FINANCIAL_MANAGER, approved_by_management=0), LOCKED)


class TestNoLedgerChange(BluelineTestCase):
	def test_commission_entries_have_no_ledger_records(self):
		invoice = paid_invoice_with_mixed_statuses()
		credit_note(invoice, qty=1)
		names = frappe.get_all(SCE, filters={"sales_invoice": invoice.name}, pluck="name")
		self.assertTrue(names)
		self.assertEqual(frappe.db.count("GL Entry", {"voucher_type": SCE}), 0)
		self.assertEqual(frappe.db.count("GL Entry", {"against_voucher_type": SCE}), 0)
		self.assertEqual(frappe.db.count("Payment Ledger Entry", {"voucher_type": SCE}), 0)
		self.assertEqual(frappe.db.count("Journal Entry Account", {"reference_type": SCE}), 0)
		self.assertEqual(frappe.db.count("Payment Entry Reference", {"reference_doctype": SCE}), 0)

	def test_adjustment_and_reversal_change_no_ledger_record(self):
		invoice = paid_invoice_with_mixed_statuses()

		# End to end: apart from the Credit Note's own postings, nothing in the ledger moves.
		def active_deductions():
			return commission_entries(invoice.name, entry_type="Deduction", docstatus=1)

		before = ledger_snapshot()
		cn = credit_note(invoice, qty=1)
		self.assertEqual(ledger_snapshot(exclude_vouchers={cn.name}), before)
		self.assertEqual(len(active_deductions()), 1)

		# The commission code alone, run directly: the ledger is identical, row for row.
		before = ledger_snapshot()
		sales_commission.reverse_credit_note(cn)
		self.assertEqual(active_deductions(), [])
		self.assertEqual(amounts(invoice), FULL)
		sales_commission.apply_credit_note(cn)
		self.assertEqual(len(active_deductions()), 1)
		self.assertEqual(ledger_snapshot(), before)

		before = ledger_snapshot(exclude_vouchers={cn.name})
		cancel(cn)
		self.assertEqual(ledger_snapshot(exclude_vouchers={cn.name}), before)
		self.assertEqual(active_deductions(), [])
