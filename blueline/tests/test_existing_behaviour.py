"""Regression cover for behaviour that existed before the client-review fixes, so those fixes
can be shown not to have broken it."""

import frappe
from frappe.utils import flt

from blueline.server_scripts.sales_commission import mark_commission_entry_paid
from blueline.tests.utils import (
	COMMISSION_ITEM,
	COMPANY,
	CUSTOMER,
	FINANCIAL_MANAGER,
	GI_MANAGEMENT,
	GI_SALES_2,
	GI_TECH,
	NON_STOCK_ITEM,
	SYSTEM_MANAGER,
	BluelineTestCase,
	act,
	approved_invoice,
	approved_payment_for,
	as_user,
	commission_entries,
	make_petty_cash_voucher,
	make_sales_invoice,
	pending_commission_entry,
	reload,
	update_entry,
	workflow,
)

SCE = "Sales Commission Entry"


class TestApprovalWorkflow(BluelineTestCase):
	def test_sales_dept_2_cannot_submit_directly(self):
		draft = make_sales_invoice(GI_MANAGEMENT)
		self.assertRefused(lambda: act(GI_SALES_2, reload(draft).submit), "Sales Dept 2 users cannot submit")

	def test_sales_dept_2_can_send_but_not_approve(self):
		draft = make_sales_invoice(GI_SALES_2)
		workflow(draft, "Send for Approval", GI_SALES_2)
		self.assertEqual(reload(draft).workflow_state, "Pending Approval")
		self.assertRefused(lambda: workflow(draft, "Approve", GI_SALES_2), "Not a valid Workflow Action")

	def test_approval_submits_and_generates_serial(self):
		invoice = approved_invoice()
		self.assertEqual((invoice.docstatus, invoice.workflow_state), (1, "Approved"))
		self.assertRegex(invoice.custom_tax_invoice_serial, r"^\d\d[A-Z]{3}_BLIN_")


class TestCommissionAccrual(BluelineTestCase):
	def test_entries_and_amounts_on_invoice_submit(self):
		invoice = approved_invoice(lines=[(COMMISSION_ITEM, 2, 1000)])
		by_person = {e.matched_sales_person: e for e in commission_entries(invoice.name)}
		self.assertEqual(set(by_person), {"M.Madusha Darshani", "W.B.Prasanna", "M M M M PARIS"})
		# Fixed Amount Per Unit 65 x 2 units; Percentage 3% of 2000.
		self.assertEqual(flt(by_person["W.B.Prasanna"].commission_amount), 130)
		self.assertEqual(flt(by_person["M M M M PARIS"].commission_amount), 60)
		self.assertEqual(by_person["W.B.Prasanna"].commission_credited_to, "W Chaminda Priyalal")
		self.assertEqual(by_person["M M M M PARIS"].commission_credited_to, "Sales Team  LDA Perera")
		self.assertTrue(all(e.status == "Accrued" and e.docstatus == 1 for e in by_person.values()))

	def test_line_without_a_rule_accrues_nothing_and_does_not_block(self):
		invoice = approved_invoice(lines=[(NON_STOCK_ITEM, 1, 100)])
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(commission_entries(invoice.name), [])

	def test_customer_and_item_rule_beats_item_only_rule(self):
		frappe.get_doc(
			{
				"doctype": "Sales Commission Rule",
				"sales_person": "J D SILVA",
				"item_code": COMMISSION_ITEM,
				"company": COMPANY,
				"commission_type": "Percentage of Line Value",
				"rate": 50,
				"enabled": 1,
			}
		).insert()
		invoice = approved_invoice()
		self.assertNotIn("J D SILVA", [e.matched_sales_person for e in commission_entries(invoice.name)])

	def test_item_only_rule_applies_when_no_customer_rule_matches(self):
		frappe.get_doc(
			{
				"doctype": "Sales Commission Rule",
				"sales_person": "J D SILVA",
				"item_code": NON_STOCK_ITEM,
				"company": COMPANY,
				"commission_type": "Percentage of Line Value",
				"rate": 10,
				"enabled": 1,
			}
		).insert()
		invoice = approved_invoice(lines=[(NON_STOCK_ITEM, 1, 500)])
		entries = commission_entries(invoice.name)
		self.assertEqual([(e.matched_sales_person, flt(e.commission_amount)) for e in entries], [("J D SILVA", 50)])


class TestCommissionRelease(BluelineTestCase):
	def test_full_payment_releases_to_pending_approval(self):
		invoice = approved_invoice()
		approved_payment_for(invoice)
		self.assertTrue(
			all(e.status == "Payment Received - Pending Approval" for e in commission_entries(invoice.name))
		)

	def test_partial_payment_leaves_entries_accrued(self):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		invoice = approved_invoice()
		with as_user(GI_TECH):
			pe = get_payment_entry("Sales Invoice", invoice.name, party_amount=100, bank_account="Cash - BEPL")
			pe.reference_no, pe.reference_date = "blueline-test", invoice.posting_date
			pe.insert()
		workflow(pe, "Send for Approval", GI_TECH)
		workflow(pe, "Approve", GI_MANAGEMENT)
		self.assertTrue(all(e.status == "Accrued" for e in commission_entries(invoice.name)))


class TestMarkAsPaid(BluelineTestCase):
	def approve(self, name):
		update_entry(name, FINANCIAL_MANAGER, approved_by_management=1)
		update_entry(name, GI_MANAGEMENT, approved_by_technical=1)

	def test_financial_manager_marks_paid(self):
		name, invoice, payment = pending_commission_entry()
		self.approve(name)
		result = act(FINANCIAL_MANAGER, mark_commission_entry_paid, name, payment.name)
		self.assertTrue(result["ok"])
		entry = frappe.get_doc(SCE, name)
		self.assertEqual((entry.status, entry.payment_entry), ("Paid", payment.name))

	def test_other_roles_cannot_mark_paid(self):
		name, invoice, payment = pending_commission_entry()
		self.approve(name)
		self.assertRefused(
			lambda: act(GI_MANAGEMENT, mark_commission_entry_paid, name, payment.name),
			"Only System Manager or Financial Manager",
		)

	def test_only_approved_entries_can_be_paid(self):
		name, invoice, payment = pending_commission_entry()
		self.assertRefused(
			lambda: act(FINANCIAL_MANAGER, mark_commission_entry_paid, name, payment.name),
			"Only an Approved commission entry",
		)

	def test_payment_must_reference_the_invoice(self):
		name, invoice, payment = pending_commission_entry()
		self.approve(name)
		other_payment = approved_payment_for(approved_invoice())
		self.assertRefused(
			lambda: act(FINANCIAL_MANAGER, mark_commission_entry_paid, name, other_payment.name),
			f"does not reference Sales Invoice {invoice.name}",
		)


class TestInvoiceWithoutSerialCancel(BluelineTestCase):
	"""Invoices that never received a Tax Invoice Serial (pre-dating the app) can still be
	cancelled; the original commission cancel guard applies to them."""

	def legacy(self, invoice):
		frappe.db.set_value("Sales Invoice", invoice.name, "custom_tax_invoice_serial", None)
		return reload(invoice)

	def test_accrued_entries_are_cancelled_with_the_invoice(self):
		invoice = self.legacy(approved_invoice())
		act(SYSTEM_MANAGER, invoice.cancel)
		entries = commission_entries(invoice.name)
		self.assertTrue(entries)
		self.assertTrue(all((e.status, e.docstatus) == ("Cancelled", 2) for e in entries))

	def test_approved_entries_block_the_cancel(self):
		name, invoice, payment = pending_commission_entry()
		update_entry(name, FINANCIAL_MANAGER, approved_by_management=1)
		update_entry(name, GI_MANAGEMENT, approved_by_technical=1)
		invoice = self.legacy(invoice)
		self.assertRefused(lambda: act(SYSTEM_MANAGER, invoice.cancel), "have already been approved or paid")


class TestRulesValidation(BluelineTestCase):
	def test_disabled_duplicate_is_allowed(self):
		rule = frappe.get_doc(
			{
				"doctype": "Sales Commission Rule",
				"sales_person": "W.B.Prasanna",
				"customer": CUSTOMER,
				"item_code": COMMISSION_ITEM,
				"company": COMPANY,
				"commission_type": "Fixed Amount Per Unit",
				"rate": 1,
				"enabled": 0,
			}
		).insert()
		self.assertTrue(rule.name)


class TestPettyCashVoucher(BluelineTestCase):
	def test_amount_must_be_positive(self):
		pcv = make_petty_cash_voucher(GI_TECH)
		pcv = reload(pcv)
		pcv.amount = 0
		self.assertRefused(lambda: act(GI_TECH, pcv.save), "Amount must be greater than zero")

	def test_accounts_must_belong_to_company(self):
		pcv = reload(make_petty_cash_voucher(GI_TECH))
		pcv.expense_account = frappe.db.get_value(
			"Account", {"company": "General Innovations (Pvt) Ltd", "root_type": "Expense", "is_group": 0}
		)
		self.assertRefused(lambda: act(GI_TECH, pcv.save), "does not belong to Company")

	def test_approval_posts_journal_entry(self):
		pcv = make_petty_cash_voucher(GI_TECH)
		workflow(pcv, "Send for Approval", GI_SALES_2)
		workflow(pcv, "Approve", GI_MANAGEMENT)
		je = frappe.get_doc("Journal Entry", reload(pcv).journal_entry)
		self.assertEqual(je.docstatus, 1)
		self.assertEqual(flt(je.total_debit), 10)


class TestCompanyCOAConfiguration(BluelineTestCase):
	def test_account_from_another_company_is_refused(self):
		config = frappe.get_doc("Company COA Configuration", COMPANY)
		config.default_cash_account = frappe.db.get_value(
			"Account", {"company": "General Innovations (Pvt) Ltd", "account_type": "Cash", "is_group": 0}
		)
		self.assertRefused(config.save, "does not belong to Company")

	def test_group_account_is_refused(self):
		config = frappe.get_doc("Company COA Configuration", COMPANY)
		config.default_bank_account = frappe.db.get_value("Account", {"company": COMPANY, "is_group": 1})
		self.assertRefused(config.save, "is a group account")
