"""Mark as Paid is tied to a real payout: an entry becomes Paid only with a submitted
Payment Entry of type Pay for the same company linked, the commission linked to one
payout never exceeds what it paid, and once Paid the link is locked and the payout can't
be cancelled."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import flt

from blueline.server_scripts.sales_commission import mark_commission_entry_paid
from blueline.tests.utils import (
	FINANCIAL_MANAGER,
	GI_MANAGEMENT,
	GI_TECH,
	SYSTEM_MANAGER,
	BluelineTestCase,
	act,
	approved_invoice,
	approved_payment_for,
	approved_payout,
	as_user,
	commission_entries,
	make_payout,
	reload,
	update_entry,
	workflow,
)

SCE = "Sales Commission Entry"
NEEDS_LINK = "that paid this commission out before marking it Paid"
LOCKED_LINK = "can't be changed once the entry is Paid"
OTHER_COMPANY = "General Innovations (Pvt) Ltd"


def entry(name):
	return frappe.get_doc(SCE, name)


def approve(name):
	update_entry(name, FINANCIAL_MANAGER, approved_by_management=1)
	update_entry(name, GI_MANAGEMENT, approved_by_technical=1)


def approved_entries():
	"""Paid invoice; its three entries (130, 130, 60) all Approved. Returns {person: name}."""
	invoice = approved_invoice()
	approved_payment_for(invoice)
	names = {e.matched_sales_person: e.name for e in commission_entries(invoice.name)}
	for name in names.values():
		approve(name)
	return names


def mark_paid_in_the_form(name, payout_name, user=FINANCIAL_MANAGER):
	"""The screen route: pick Payment Entry, Update, then Actions > Mark as Paid."""
	update_entry(name, user, payment_entry=payout_name)
	return act(user, apply_workflow, entry(name).as_json(), "Mark as Paid")


class TestPaidNeedsAPayout(BluelineTestCase):
	def test_cannot_become_paid_without_a_link_by_any_route(self):
		name = approved_entries()["W.B.Prasanna"]
		for user in (FINANCIAL_MANAGER, SYSTEM_MANAGER):
			with self.subTest(route="Mark as Paid action", user=user):
				self.assertRefused(lambda: act(user, apply_workflow, entry(name).as_json(), "Mark as Paid"), NEEDS_LINK)
			with self.subTest(route="status set to Paid", user=user):
				self.assertRefused(lambda: update_entry(name, user, status="Paid"), NEEDS_LINK)
		with as_user("Administrator"):
			doc = entry(name)
			doc.status = "Paid"
			doc.flags.ignore_permissions = True
			self.assertRefused(doc.save, NEEDS_LINK)
		self.assertEqual(entry(name).status, "Approved")

	def test_only_a_submitted_pay_entry_of_the_same_company(self):
		name = approved_entries()["W.B.Prasanna"]
		draft = make_payout(500)
		cancelled = approved_payout(500)
		act(SYSTEM_MANAGER, reload(cancelled).cancel)
		receipt = frappe.get_last_doc("Payment Entry", {"payment_type": "Receive", "docstatus": 1})
		other_company = approved_payout(500, company=OTHER_COMPANY)
		for payout, message in (
			(draft, "is not a submitted Payment Entry"),
			# Frappe's own link check refuses a cancelled document before ours runs.
			(cancelled, "Cannot link cancelled document"),
			(receipt, "must be of type Pay"),
			(other_company, f"belongs to {OTHER_COMPANY}"),
		):
			with self.subTest(payout=payout.name, why=message):
				self.assertRefused(lambda: update_entry(name, FINANCIAL_MANAGER, payment_entry=payout.name), message)
				self.assertRefused(lambda: act(FINANCIAL_MANAGER, mark_commission_entry_paid, name, payout.name), message)
		self.assertEqual((entry(name).status, entry(name).payment_entry), ("Approved", None))

	def test_link_only_on_an_approved_entry(self):
		invoice = approved_invoice()
		approved_payment_for(invoice)
		name = commission_entries(invoice.name)[0].name  # Pending Approval
		self.assertRefused(
			lambda: update_entry(name, SYSTEM_MANAGER, payment_entry=approved_payout(500).name),
			"only be linked once the commission entry is Approved",
		)

	def test_screen_route_and_api_route_both_mark_paid(self):
		names = approved_entries()
		payout = approved_payout(1000)
		mark_paid_in_the_form(names["W.B.Prasanna"], payout.name)
		act(FINANCIAL_MANAGER, mark_commission_entry_paid, names["M.Madusha Darshani"], payout.name)
		for person in ("W.B.Prasanna", "M.Madusha Darshani"):
			with self.subTest(person=person):
				e = entry(names[person])
				self.assertEqual((e.status, e.payment_entry), ("Paid", payout.name))

	def test_a_wrong_pick_can_be_cleared_before_marking_paid(self):
		name = approved_entries()["W.B.Prasanna"]
		update_entry(name, FINANCIAL_MANAGER, payment_entry=approved_payout(500).name)
		update_entry(name, FINANCIAL_MANAGER, payment_entry=None)
		self.assertIsNone(entry(name).payment_entry)


class TestNoOverspend(BluelineTestCase):
	def test_one_payout_covers_several_entries_up_to_its_amount(self):
		names = approved_entries()  # 130 + 130 + 60
		payout = approved_payout(260)
		act(FINANCIAL_MANAGER, mark_commission_entry_paid, names["W.B.Prasanna"], payout.name)
		act(FINANCIAL_MANAGER, mark_commission_entry_paid, names["M.Madusha Darshani"], payout.name)  # exactly 260
		self.assertRefused(
			lambda: act(FINANCIAL_MANAGER, mark_commission_entry_paid, names["M M M M PARIS"], payout.name),
			"more than was paid",
		)
		self.assertRefused(
			lambda: update_entry(names["M M M M PARIS"], FINANCIAL_MANAGER, payment_entry=payout.name), "more than was paid"
		)
		self.assertEqual(entry(names["M M M M PARIS"]).status, "Approved")
		linked = frappe.db.sql(f"select sum(commission_amount) from `tab{SCE}` where payment_entry = %s", payout.name)[0][0]
		self.assertEqual(flt(linked), 260)

	def test_a_link_picked_but_not_yet_paid_counts_too(self):
		names = approved_entries()
		payout = approved_payout(200)
		update_entry(names["W.B.Prasanna"], FINANCIAL_MANAGER, payment_entry=payout.name)  # 130, still Approved
		self.assertRefused(
			lambda: update_entry(names["M.Madusha Darshani"], FINANCIAL_MANAGER, payment_entry=payout.name),
			"more than was paid",
		)


class TestLockedOncePaid(BluelineTestCase):
	def paid(self):
		names = approved_entries()
		payout = approved_payout(1000)
		act(FINANCIAL_MANAGER, mark_commission_entry_paid, names["W.B.Prasanna"], payout.name)
		return names["W.B.Prasanna"], payout

	def test_cannot_be_marked_paid_again(self):
		name, payout = self.paid()
		self.assertRefused(
			lambda: act(FINANCIAL_MANAGER, mark_commission_entry_paid, name, approved_payout(500).name),
			"Only an Approved commission entry",
		)

	def test_link_is_read_only_for_everyone_once_paid(self):
		name, payout = self.paid()
		other = approved_payout(500)
		for user in (FINANCIAL_MANAGER, SYSTEM_MANAGER, "Administrator"):
			with self.subTest(user=user, change="replace"):
				self.assertRefused(lambda: update_entry(name, user, payment_entry=other.name), LOCKED_LINK)
			with self.subTest(user=user, change="clear"):
				self.assertRefused(lambda: update_entry(name, user, payment_entry=None), LOCKED_LINK)
		with as_user("Administrator"):
			doc = entry(name)
			doc.payment_entry = other.name
			doc.flags.ignore_permissions = True
			self.assertRefused(doc.save, LOCKED_LINK)
		self.assertEqual(entry(name).payment_entry, payout.name)

	def test_cancelling_the_payout_is_refused_naming_the_entries(self):
		name, payout = self.paid()
		with self.assertRaises(frappe.ValidationError) as ctx:
			act(SYSTEM_MANAGER, reload(payout).cancel)
		self.assertIn(name, str(ctx.exception))
		self.assertIn("can't be cancelled", str(ctx.exception))
		self.assertEqual(frappe.db.get_value("Payment Entry", payout.name, "docstatus"), 1)

	def test_an_unused_payout_can_still_be_cancelled(self):
		payout = approved_payout(100)
		act(SYSTEM_MANAGER, reload(payout).cancel)
		self.assertEqual(frappe.db.get_value("Payment Entry", payout.name, "docstatus"), 2)


class TestDeductionsAndLegacy(BluelineTestCase):
	def test_deduction_still_cannot_be_marked_paid(self):
		from blueline.tests.test_credit_note_commission import credit_note, paid_invoice_with_mixed_statuses

		invoice = paid_invoice_with_mixed_statuses()
		credit_note(invoice, qty=1)
		[deduction] = [e.name for e in commission_entries(invoice.name, entry_type="Deduction")]
		approve(deduction)
		payout = approved_payout(100)
		self.assertRefused(lambda: act(FINANCIAL_MANAGER, mark_commission_entry_paid, deduction, payout.name), "is a deduction")
		self.assertRefused(lambda: update_entry(deduction, FINANCIAL_MANAGER, payment_entry=payout.name), "is a deduction")

	def test_entries_paid_before_this_rule_are_left_as_they_are(self):
		name = approved_entries()["W.B.Prasanna"]
		frappe.db.set_value(SCE, name, "status", "Paid")  # as marked before the link existed
		update_entry(name, SYSTEM_MANAGER)  # an ordinary save still works
		e = entry(name)
		self.assertEqual((e.status, e.payment_entry), ("Paid", None))
