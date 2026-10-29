"""A commission entry can't be ticked or approved while its Sales Invoice still has an
outstanding amount — for every role and every route — and an undone payment takes released
commission back (untouched entries) or flags it (entries a person already acted on)."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import flt

from blueline.server_scripts.sales_commission import mark_commission_entry_paid
from blueline.tests.test_commission_release import pay, reconcile, standalone_credit_note
from blueline.tests.utils import (
	FINANCIAL_MANAGER,
	GI_MANAGEMENT,
	SYSTEM_MANAGER,
	BluelineTestCase,
	act,
	approved_invoice,
	approved_payout,
	as_user,
	commission_entries,
	update_entry,
)

SCE = "Sales Commission Entry"
UNPAID = (
	"This commission cannot be approved while the invoice still has an outstanding amount. "
	"Wait until the invoice is fully paid or credited."
)
PENDING = "Payment Received - Pending Approval"
TECHNICAL_APPROVER = GI_MANAGEMENT


def entry(name):
	return frappe.get_doc(SCE, name)


def by_person(invoice, entry_type="Commission"):
	return {e.matched_sales_person: e.name for e in commission_entries(invoice.name, entry_type=entry_type)}


def approve(name):
	update_entry(name, FINANCIAL_MANAGER, approved_by_management=1)
	update_entry(name, TECHNICAL_APPROVER, approved_by_technical=1)


def cancel_payment(pe):
	act(SYSTEM_MANAGER, frappe.get_doc("Payment Entry", pe.name).cancel)


def force_status(name, status):
	"""Put an entry in a status directly, as a guard-agnostic starting point."""
	frappe.db.set_value(SCE, name, "status", status, update_modified=False)


class TestRefusedWhileUnpaid(BluelineTestCase):
	def assert_every_route_refused(self, name, approve_action=True):
		for user, field in (
			(FINANCIAL_MANAGER, "approved_by_management"),
			(TECHNICAL_APPROVER, "approved_by_technical"),
			(SYSTEM_MANAGER, "approved_by_management"),
			(SYSTEM_MANAGER, "approved_by_technical"),
			("Administrator", "approved_by_management"),
			("Administrator", "approved_by_technical"),
		):
			with self.subTest(user=user, tick=field):
				self.assertRefused(lambda: update_entry(name, user, **{field: 1}), UNPAID)
		if approve_action:  # the workflow offers Approve only from Pending Approval
			self.assertRefused(lambda: act(SYSTEM_MANAGER, apply_workflow, entry(name).as_json(), "Approve"), UNPAID)
		for user in (SYSTEM_MANAGER, FINANCIAL_MANAGER, "Administrator"):
			with self.subTest(route="status set to Approved", user=user):
				self.assertRefused(lambda: update_entry(name, user, status="Approved"), UNPAID)
		with self.subTest(route="system-style save, ignore_permissions"):
			with as_user("Administrator"):
				doc = entry(name)
				doc.approved_by_management = 1
				doc.flags.ignore_permissions = True
				self.assertRefused(doc.save, UNPAID)
		e = entry(name)
		self.assertEqual((e.approved_by_management, e.approved_by_technical), (0, 0))
		self.assertNotEqual(e.status, "Approved")

	def test_unpaid_invoice_refuses_ticks_approve_and_approved_status(self):
		invoice = approved_invoice()
		name = commission_entries(invoice.name)[0].name
		self.assert_every_route_refused(name, approve_action=False)  # still Accrued
		force_status(name, PENDING)  # even if it had somehow reached Pending Approval
		self.assert_every_route_refused(name)

	def test_partly_paid_invoice_is_refused(self):
		invoice = approved_invoice()
		pay(invoice, 1999)
		name = commission_entries(invoice.name)[0].name
		self.assertEqual(entry(name).status, "Accrued")
		force_status(name, PENDING)
		self.assert_every_route_refused(name)

	def test_a_draft_created_ticked_is_refused(self):
		invoice = approved_invoice()
		source = entry(commission_entries(invoice.name)[0].name)
		draft = frappe.copy_doc(source)
		draft.update({"approved_by_management": 1, "status": "Accrued"})
		with as_user(SYSTEM_MANAGER):
			self.assertRefused(draft.insert, UNPAID)


class TestAllowedOnceSettled(BluelineTestCase):
	def test_fully_paid_invoice_passes(self):
		invoice = approved_invoice()
		pay(invoice, 2000)
		name = commission_entries(invoice.name)[0].name
		approve(name)
		self.assertEqual(entry(name).status, "Approved")

	def test_invoice_settled_by_payment_and_credit_note_passes(self):
		invoice = approved_invoice()
		cn = standalone_credit_note(invoice, qty=1)
		pay(invoice, 1000)
		name = by_person(invoice)["W.B.Prasanna"]
		self.assertRefused(lambda: update_entry(name, FINANCIAL_MANAGER, approved_by_management=1), UNPAID)
		reconcile(invoice, cn)
		approve(name)
		self.assertEqual((entry(name).status, flt(entry(name).commission_amount)), ("Approved", 65))

	def test_invoice_fully_credited_passes_for_what_is_left(self):
		"""Fully settled by credit alone: a full return cancels the commission, so the only
		thing left to approve is a deduction (TestDeductionsNotBlocked)."""
		invoice = approved_invoice()
		reconcile(invoice, standalone_credit_note(invoice))
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount")), 0)
		self.assertEqual({e.status for e in commission_entries(invoice.name)}, {"Cancelled"})


class TestUndonePayment(BluelineTestCase):
	def test_cancelled_payment_reopens_untouched_entries_and_flags_ticked_ones(self):
		invoice = approved_invoice()
		payment = pay(invoice, 2000)
		people = by_person(invoice)
		ticked, untouched = people["W.B.Prasanna"], [people["M.Madusha Darshani"], people["M M M M PARIS"]]
		update_entry(ticked, FINANCIAL_MANAGER, approved_by_management=1)

		cancel_payment(payment)

		for name in untouched:
			with self.subTest(entry=name):
				e = entry(name)
				self.assertEqual((e.status, e.unpaid_warning), ("Accrued", None))
				self.assertTrue(frappe.db.exists("Comment", {"reference_name": name, "content": ["like", "%Moved back to Accrued%"]}))
		e = entry(ticked)
		self.assertEqual((e.status, e.approved_by_management), (PENDING, 1), "a ticked entry keeps its status")
		self.assertIn(payment.name, e.unpaid_warning)
		self.assertIn("was not changed", e.unpaid_warning)
		self.assertTrue(frappe.db.exists("Comment", {"reference_name": ticked, "content": ["like", f"%{payment.name}%"]}))
		self.assertRefused(lambda: update_entry(ticked, TECHNICAL_APPROVER, approved_by_technical=1), UNPAID)

		# Paid again: the untouched ones are released again, the warning is cleared, approval resumes.
		pay(invoice, 2000)
		self.assertEqual({entry(n).status for n in untouched}, {PENDING})
		self.assertIsNone(entry(ticked).unpaid_warning)
		update_entry(ticked, TECHNICAL_APPROVER, approved_by_technical=1)
		self.assertEqual(entry(ticked).status, "Approved")

	def test_cancelled_payment_leaves_an_approved_entry_alone(self):
		invoice = approved_invoice()
		payment = pay(invoice, 2000)
		name = commission_entries(invoice.name)[0].name
		approve(name)
		cancel_payment(payment)
		e = entry(name)
		self.assertEqual((e.status, e.approved_by_management, e.approved_by_technical), ("Approved", 1, 1))
		self.assertIn("already Approved", e.unpaid_warning)

	def test_people_cannot_write_or_clear_the_warning(self):
		invoice = approved_invoice()
		payment = pay(invoice, 2000)
		name = commission_entries(invoice.name)[0].name
		approve(name)
		cancel_payment(payment)
		warning = entry(name).unpaid_warning
		self.assertTrue(warning)
		for user in (SYSTEM_MANAGER, "Administrator"):
			with self.subTest(user=user):
				update_entry(name, user, unpaid_warning="")
				self.assertEqual(entry(name).unpaid_warning, warning)


class TestDeductionsNotBlocked(BluelineTestCase):
	def test_deduction_is_approved_while_the_original_invoice_is_unpaid_again(self):
		invoice = approved_invoice()
		pay(invoice, 1000)
		second = pay(invoice, 1000)
		paid = by_person(invoice)["W.B.Prasanna"]
		approve(paid)
		act(FINANCIAL_MANAGER, mark_commission_entry_paid, paid, approved_payout(entry(paid).commission_amount).name)
		standalone_credit_note(invoice, qty=1)
		[deduction] = by_person(invoice, "Deduction").values()

		cancel_payment(second)  # the invoice the Credit Note was raised against owes 1000 again
		self.assertGreater(flt(frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount")), 0)
		self.assertEqual(entry(deduction).status, PENDING, "deductions aren't moved back")

		approve(deduction)
		self.assertEqual(entry(deduction).status, "Approved")
		self.assertIsNone(entry(deduction).unpaid_warning)


class TestOtherRulesUnchanged(BluelineTestCase):
	def test_two_people_and_wrong_role_still_apply_once_paid(self):
		invoice = approved_invoice()
		pay(invoice, 2000)
		name = commission_entries(invoice.name)[0].name
		self.assertRefused(lambda: update_entry(name, FINANCIAL_MANAGER, approved_by_technical=1), "You don't have permission to change")
		update_entry(name, SYSTEM_MANAGER, approved_by_technical=1)
		self.assertRefused(lambda: update_entry(name, SYSTEM_MANAGER, approved_by_management=1), "two different users")
		update_entry(name, FINANCIAL_MANAGER, approved_by_management=1)
		self.assertEqual(entry(name).status, "Approved")
		self.assertRefused(lambda: update_entry(name, FINANCIAL_MANAGER, approved_by_management=0), "cannot be changed once the entry is")
