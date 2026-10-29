"""Commission is released (Accrued -> Payment Received - Pending Approval) when the invoice's
outstanding amount reaches zero by any route — Payment Entry, Credit Note reconciled through
Payment Reconciliation, Journal Entry — never earlier, and only once.

Credit Notes here stand on their own and are applied with Payment Reconciliation, which is
how production's ERPNext (15.6, no "Update Outstanding for Self") always works; on newer
ERPNext the option is ticked to get the same behaviour."""

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
from frappe.utils import flt, nowdate

from blueline.server_scripts import sales_commission
from blueline.tests.utils import (
	COMPANY,
	FINANCIAL_MANAGER,
	GI_MANAGEMENT,
	GI_SALES,
	GI_TECH,
	SYSTEM_MANAGER,
	BluelineTestCase,
	approved_invoice,
	as_user,
	commission_entries,
	reload,
	update_entry,
	workflow,
)

PENDING = "Payment Received - Pending Approval"
CASH = "Cash - BEPL"


def statuses(invoice):
	return sorted({e.status for e in commission_entries(invoice.name, entry_type="Commission")})


def amounts(invoice):
	return sorted(flt(e.commission_amount) for e in commission_entries(invoice.name, entry_type="Commission"))


def outstanding(invoice):
	return flt(frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount"))


def standalone_credit_note(invoice, qty=None):
	"""A Credit Note that stands as its own negative balance (production's behaviour)."""
	with as_user(GI_SALES):
		cn = make_sales_return(invoice.name)
		if qty is not None:
			for row in cn.items:
				row.qty = -qty
		if cn.meta.get_field("update_outstanding_for_self"):
			cn.update_outstanding_for_self = 1
		cn.insert()
	workflow(cn, "Send for Approval", GI_SALES)
	workflow(cn, "Approve", SYSTEM_MANAGER)
	return reload(cn)


def reconcile(invoice, credit_note):
	"""Payment Reconciliation, as the accountant does it: apply the Credit Note to the invoice."""
	with as_user(FINANCIAL_MANAGER):
		pr = frappe.get_doc("Payment Reconciliation")
		pr.update(
			{
				"company": COMPANY,
				"party_type": "Customer",
				"party": invoice.customer,
				"receivable_payable_account": invoice.debit_to,
			}
		)
		pr.get_unreconciled_entries()
		invoices = [i.as_dict() for i in pr.invoices if i.invoice_number == invoice.name]
		payments = [p.as_dict() for p in pr.payments if p.reference_name == credit_note.name]
		assert invoices and payments, (invoices, payments)
		pr.allocate_entries({"invoices": invoices, "payments": payments})
		pr.reconcile()


def pay(invoice, amount):
	"""Payment Entry for `amount` against the invoice, approved by two people."""
	with as_user(GI_TECH):
		pe = get_payment_entry("Sales Invoice", invoice.name, party_amount=amount, bank_account=CASH)
		pe.reference_no, pe.reference_date = "blueline-test", nowdate()
		pe.insert()
	workflow(pe, "Send for Approval", GI_TECH)
	workflow(pe, "Approve", GI_MANAGEMENT)
	return reload(pe)


def journal_receipt(invoice, amount):
	"""Journal Entry receiving `amount` against the invoice (no GI workflow on Journal Entry)."""
	with as_user(FINANCIAL_MANAGER):
		je = frappe.new_doc("Journal Entry")
		je.update({"voucher_type": "Cash Entry", "company": COMPANY, "posting_date": nowdate()})
		je.append("accounts", {"account": CASH, "debit_in_account_currency": amount})
		je.append(
			"accounts",
			{
				"account": invoice.debit_to,
				"party_type": "Customer",
				"party": invoice.customer,
				"credit_in_account_currency": amount,
				"reference_type": "Sales Invoice",
				"reference_name": invoice.name,
			},
		)
		je.insert()
		je.submit()
	return je


class TestReleaseWithCreditNotes(BluelineTestCase):
	# approved_invoice(): 2 units at 1000, grand total 2000, three Accrued entries.

	def test_paid_net_of_a_credit_note_then_reconciled(self):
		invoice = approved_invoice()
		cn = standalone_credit_note(invoice, qty=1)
		self.assertEqual(flt(cn.outstanding_amount), -1000)
		self.assertEqual(amounts(invoice), [30, 65, 65])

		pay(invoice, 1000)  # the customer pays what they owe after the credit
		self.assertEqual(outstanding(invoice), 1000)
		self.assertEqual(statuses(invoice), ["Accrued"], "not released while anything is outstanding")

		reconcile(invoice, cn)
		self.assertEqual(outstanding(invoice), 0)
		self.assertEqual(statuses(invoice), [PENDING])
		self.assertEqual(amounts(invoice), [30, 65, 65], "release never changes the amounts")

	def test_credit_reconciled_first_then_paid(self):
		invoice = approved_invoice()
		cn = standalone_credit_note(invoice, qty=1)
		reconcile(invoice, cn)
		self.assertEqual(outstanding(invoice), 1000)
		self.assertEqual(statuses(invoice), ["Accrued"])

		pay(invoice, 1000)
		self.assertEqual(outstanding(invoice), 0)
		self.assertEqual(statuses(invoice), [PENDING])

	def test_full_return(self):
		invoice = approved_invoice()
		cn = standalone_credit_note(invoice)
		self.assertEqual(statuses(invoice), ["Cancelled"])
		reconcile(invoice, cn)
		self.assertEqual(outstanding(invoice), 0)
		# Settled, but there is nothing to release: the return cancelled the commission.
		self.assertEqual(statuses(invoice), ["Cancelled"])
		self.assertEqual(amounts(invoice), [0, 0, 0])

	def test_partial_return_alone_does_not_release(self):
		invoice = approved_invoice()
		cn = standalone_credit_note(invoice, qty=1)
		reconcile(invoice, cn)
		self.assertEqual(outstanding(invoice), 1000)
		self.assertEqual(statuses(invoice), ["Accrued"])

		pay(invoice, 400)
		self.assertEqual(statuses(invoice), ["Accrued"])
		pay(invoice, 600)
		self.assertEqual(statuses(invoice), [PENDING])
		self.assertEqual(amounts(invoice), [30, 65, 65])


class TestReleaseByJournalEntry(BluelineTestCase):
	def test_journal_entry_settles_and_releases(self):
		invoice = approved_invoice()
		journal_receipt(invoice, 1500)
		self.assertEqual(statuses(invoice), ["Accrued"])
		journal_receipt(invoice, 500)
		self.assertEqual(outstanding(invoice), 0)
		self.assertEqual(statuses(invoice), [PENDING])

	def test_payment_entry_route_still_releases(self):
		invoice = approved_invoice()
		pay(invoice, 2000)
		self.assertEqual(statuses(invoice), [PENDING])


class TestReleasedOnce(BluelineTestCase):
	def test_no_second_release_and_approval_is_kept(self):
		invoice = approved_invoice()
		pay(invoice, 2000)
		name = commission_entries(invoice.name)[0].name
		update_entry(name, FINANCIAL_MANAGER, approved_by_management=1)
		versions = frappe.db.count("Version", {"ref_doctype": "Sales Commission Entry", "docname": name})

		# Every trigger fires again on the settled invoice.
		sales_commission.release_if_settled(invoice.name)
		sales_commission.release_commission_entries(frappe.get_last_doc("Payment Entry", {"party": invoice.customer}))
		for ple in frappe.get_all("Payment Ledger Entry", filters={"against_voucher_no": invoice.name}, pluck="name"):
			sales_commission.release_on_ledger_update(frappe.get_doc("Payment Ledger Entry", ple))

		entry = frappe.get_doc("Sales Commission Entry", name)
		self.assertEqual(outstanding(invoice), 0)
		self.assertEqual((entry.status, entry.approved_by_management, entry.management_approved_by), (PENDING, 1, FINANCIAL_MANAGER))
		self.assertEqual(frappe.db.count("Version", {"ref_doctype": "Sales Commission Entry", "docname": name}), versions)

	def test_two_person_approval_still_required_after_any_route(self):
		invoice = approved_invoice()
		journal_receipt(invoice, 2000)
		name = commission_entries(invoice.name)[0].name
		update_entry(name, SYSTEM_MANAGER, approved_by_technical=1)
		self.assertRefused(lambda: update_entry(name, SYSTEM_MANAGER, approved_by_management=1), "two different users")
		self.assertEqual(frappe.db.get_value("Sales Commission Entry", name, "status"), PENDING)

	def test_cancelled_or_unsubmitted_invoices_are_ignored(self):
		invoice = approved_invoice()
		frappe.db.set_value("Sales Invoice", invoice.name, "outstanding_amount", 0)
		frappe.db.set_value("Sales Invoice", invoice.name, "docstatus", 2)
		sales_commission.release_if_settled(invoice.name)
		self.assertEqual(statuses(invoice), ["Accrued"])
