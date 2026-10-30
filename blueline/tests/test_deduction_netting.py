"""Deductions are taken off the payee's next payout: when a commission entry is marked Paid,
the payee's Approved deductions (oldest first, whole ones, never taking the payee below zero
on that payout) are linked to the same Payment Entry and marked Paid, so the payout only has
to cover the net."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import flt

from blueline.blueline.page.sales_commission_register.sales_commission_register import get_entries
from blueline.server_scripts.sales_commission import mark_commission_entry_paid
from blueline.tests.test_credit_note_commission import (
	approve,
	cancel,
	credit_note,
	entries_by_person,
	paid_invoice_with_mixed_statuses,
)
from blueline.tests.utils import (
	COMMISSION_ITEM,
	FINANCIAL_MANAGER,
	SYSTEM_MANAGER,
	BluelineTestCase,
	act,
	approved_invoice,
	approved_payment_for,
	approved_payout,
	reload,
	update_entry,
)

SCE = "Sales Commission Entry"
OVERSPENT = "more than was paid"
PERSON = "W.B.Prasanna"


def entry(name):
	return frappe.get_doc(SCE, name)


def deduction_for(invoice, qty=1, approved=True):
	"""Credit Note against the invoice's Paid entry (PERSON); returns its Deduction entry."""
	credit_note(invoice, qty=qty)
	[deduction] = entries_by_person(invoice, "Deduction").values()
	if approved:
		approve(deduction.name)
	return reload(deduction)


def next_commission(qty=2):
	"""A new fully paid invoice with PERSON's commission entry Approved. Returns the entry."""
	invoice = approved_invoice(lines=[(COMMISSION_ITEM, qty, 1000)])
	approved_payment_for(invoice)
	commission = entries_by_person(invoice)[PERSON]
	approve(commission.name)
	return reload(commission)


def outstanding(company, payee):
	data = act(FINANCIAL_MANAGER, get_entries, company=company)
	return [e["name"] for d in data["deductions"] if d["commission_credited_to"] == payee for e in d["entries"]]


class TestNetting(BluelineTestCase):
	def test_deduction_is_taken_off_the_next_payout(self):
		deduction = deduction_for(paid_invoice_with_mixed_statuses())  # -65
		commission = next_commission()  # 130, same payee
		self.assertEqual(deduction.commission_credited_to, commission.commission_credited_to)
		net = flt(commission.commission_amount) + flt(deduction.commission_amount)

		self.assertRefused(
			lambda: act(FINANCIAL_MANAGER, mark_commission_entry_paid, commission.name, approved_payout(net - 1).name),
			OVERSPENT,
		)
		payout = approved_payout(net)
		result = act(FINANCIAL_MANAGER, mark_commission_entry_paid, commission.name, payout.name)
		self.assertIn(deduction.name, result["message"])

		for name in (commission.name, deduction.name):
			with self.subTest(entry=name):
				e = entry(name)
				self.assertEqual((e.status, e.payment_entry), ("Paid", payout.name))
		linked = frappe.db.sql(f"select sum(commission_amount) from `tab{SCE}` where payment_entry = %s", payout.name)[0][0]
		self.assertEqual(flt(linked), net)
		self.assertNotIn(deduction.name, outstanding(commission.company, commission.commission_credited_to))

	def test_the_form_route_settles_deductions_too(self):
		deduction = deduction_for(paid_invoice_with_mixed_statuses())
		commission = next_commission()
		payout = approved_payout(flt(commission.commission_amount) + flt(deduction.commission_amount))
		update_entry(commission.name, FINANCIAL_MANAGER, payment_entry=payout.name)
		self.assertEqual(entry(deduction.name).status, "Approved", "picking the payout alone settles nothing")
		act(FINANCIAL_MANAGER, apply_workflow, entry(commission.name).as_json(), "Mark as Paid")
		self.assertEqual((entry(deduction.name).status, entry(deduction.name).payment_entry), ("Paid", payout.name))

	def test_an_unapproved_deduction_is_not_taken_off(self):
		deduction = deduction_for(paid_invoice_with_mixed_statuses(), approved=False)
		commission = next_commission()
		short = approved_payout(flt(commission.commission_amount) + flt(deduction.commission_amount))
		self.assertRefused(
			lambda: act(FINANCIAL_MANAGER, mark_commission_entry_paid, commission.name, short.name), OVERSPENT
		)
		act(FINANCIAL_MANAGER, mark_commission_entry_paid, commission.name, approved_payout(commission.commission_amount).name)
		deduction = reload(deduction)
		self.assertEqual((deduction.status, deduction.payment_entry), ("Payment Received - Pending Approval", None))
		self.assertIn(deduction.name, outstanding(commission.company, commission.commission_credited_to))

	def test_a_deduction_bigger_than_the_commission_waits_for_enough_commission(self):
		deduction = deduction_for(paid_invoice_with_mixed_statuses(), qty=2)  # full return: -130
		first, second = next_commission(qty=1), next_commission(qty=1)  # 65 each
		self.assertGreater(abs(flt(deduction.commission_amount)), flt(first.commission_amount))
		payout = approved_payout(first.commission_amount)

		act(FINANCIAL_MANAGER, mark_commission_entry_paid, first.name, payout.name)
		self.assertEqual(entry(deduction.name).status, "Approved", "would take the payee below zero")

		act(FINANCIAL_MANAGER, mark_commission_entry_paid, second.name, payout.name)
		deduction = reload(deduction)
		self.assertEqual((deduction.status, deduction.payment_entry), ("Paid", payout.name))
		linked = frappe.db.sql(f"select sum(commission_amount) from `tab{SCE}` where payment_entry = %s", payout.name)[0][0]
		self.assertEqual(flt(linked), flt(first.commission_amount) + flt(second.commission_amount) + flt(deduction.commission_amount))

	def test_another_payees_commission_leaves_the_deduction_alone(self):
		invoice = paid_invoice_with_mixed_statuses()
		deduction = deduction_for(invoice)
		other_invoice = approved_invoice()
		approved_payment_for(other_invoice)
		others = [
			e for e in entries_by_person(other_invoice).values() if e.commission_credited_to != deduction.commission_credited_to
		]
		if not others:
			self.skipTest("every payee on the test item is the deduction's payee")
		other = others[0]
		approve(other.name)
		act(FINANCIAL_MANAGER, mark_commission_entry_paid, other.name, approved_payout(other.commission_amount).name)
		self.assertEqual((entry(deduction.name).status, entry(deduction.name).payment_entry), ("Approved", None))


class TestSettledDeductionIsLocked(BluelineTestCase):
	def settled(self):
		deduction = deduction_for(paid_invoice_with_mixed_statuses())
		commission = next_commission()
		payout = approved_payout(flt(commission.commission_amount) + flt(deduction.commission_amount))
		act(FINANCIAL_MANAGER, mark_commission_entry_paid, commission.name, payout.name)
		return reload(deduction), payout

	def test_its_credit_note_can_no_longer_be_cancelled(self):
		deduction, payout = self.settled()
		cn = frappe.get_doc("Sales Invoice", deduction.credit_note)
		self.assertRefused(lambda: cancel(cn), "have already been taken off a payout")
		self.assertEqual(frappe.db.get_value("Sales Invoice", cn.name, "docstatus"), 1)
		self.assertEqual(entry(deduction.name).status, "Paid")

	def test_its_payout_can_no_longer_be_cancelled(self):
		deduction, payout = self.settled()
		self.assertRefused(lambda: act(SYSTEM_MANAGER, reload(payout).cancel), "can't be cancelled")

	def test_its_payment_entry_is_locked(self):
		deduction, payout = self.settled()
		self.assertRefused(
			lambda: update_entry(deduction.name, SYSTEM_MANAGER, payment_entry=approved_payout(500).name),
			"can't be changed once the entry is Paid",
		)

	def test_a_deduction_still_cannot_be_marked_paid_by_hand(self):
		deduction = deduction_for(paid_invoice_with_mixed_statuses())
		self.assertRefused(
			lambda: act(FINANCIAL_MANAGER, mark_commission_entry_paid, deduction.name, approved_payout(100).name),
			"is a deduction",
		)
