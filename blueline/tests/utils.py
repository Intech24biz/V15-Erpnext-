"""Shared fixtures for the blueline suites.

These suites run against a site that holds real (copied) business data, so nothing here may
persist: every test is rolled back in tearDown, and the runner makes frappe.db.commit raise
for the whole run. Tests act as the real local users so role and permission checks are the
genuine ones, not mocked.
"""

import unittest
from contextlib import contextmanager

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, nowdate

COMPANY = "Blueline Enterprises Pvt Ltd"
CUSTOMER = "CBL Foods International Pvt Ltd"
SUPPLIER = "Blueline Test Supplier"
# Matches three enabled Sales Commission Rules (two reps under one group + one group rep).
COMMISSION_ITEM = "BLZLWRFOPVC 33mmX450M BLK"
NON_STOCK_ITEM = "11S+"

# Local users and the roles that matter here (see TESTING_GUIDE.md section 0.4).
SYSTEM_MANAGER = "ceo@gen-innov.com"  # System Manager, GI Management, Technical Approver
GI_MANAGEMENT = "office@gen-innov.com"  # GI Management, Technical Approver
GI_SALES = "sales@gen-innov.com"  # GI Sales Dept
GI_TECH = "tech@gen-innov.com"  # GI Tech Dept
GI_SALES_2 = "geninnov.tech2@gmail.com"  # GI Sales Dept 2 (restricted)
FINANCIAL_MANAGER = "mohamedsafras97831@gmail.com"  # Financial Manager

SELF_APPROVAL_MESSAGE = "You cannot approve a document you created or sent for approval."


class BluelineTestCase(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.db.rollback()
		frappe.set_user("Administrator")
		frappe.clear_messages()
		frappe.local.response.pop("docs", None)

	def assertRefused(self, fn, message):
		"""fn must raise a Frappe error whose text contains `message`."""
		with self.assertRaises(frappe.ValidationError) as ctx:
			fn()
		self.assertIn(message, str(ctx.exception))
		frappe.clear_messages()


@contextmanager
def as_user(user):
	previous = frappe.session.user
	frappe.set_user(user)
	try:
		yield
	finally:
		frappe.set_user(previous)


def act(user, fn, *args, **kwargs):
	with as_user(user):
		return fn(*args, **kwargs)


def workflow(doc, action, user):
	"""Run a workflow action exactly as the form button / REST API does."""
	with as_user(user):
		return apply_workflow(frappe.get_doc(doc.doctype, doc.name).as_json(), action)


def reload(doc):
	return frappe.get_doc(doc.doctype, doc.name)


# --- document factories: each inserts a Draft as `user`, so `user` becomes the owner -------


def make_sales_invoice(user="Administrator", lines=None, customer=CUSTOMER):
	with as_user(user):
		si = frappe.new_doc("Sales Invoice")
		si.company = COMPANY
		si.customer = customer
		si.posting_date = nowdate()
		si.due_date = add_days(nowdate(), 30)
		si.update_stock = 0
		for item_code, qty, rate in lines or [(COMMISSION_ITEM, 2, 1000)]:
			si.append("items", {"item_code": item_code, "qty": qty, "rate": rate})
		si.set_missing_values()
		si.insert()
		return si


def make_quotation(user="Administrator"):
	with as_user(user):
		qtn = frappe.new_doc("Quotation")
		qtn.company = COMPANY
		qtn.quotation_to = "Customer"
		qtn.party_name = CUSTOMER
		qtn.transaction_date = nowdate()
		qtn.valid_till = add_days(nowdate(), 30)
		qtn.append("items", {"item_code": NON_STOCK_ITEM, "qty": 1, "rate": 100})
		qtn.run_method("set_missing_values")
		qtn.insert()
		return qtn


def make_purchase_order(user="Administrator"):
	with as_user(user):
		po = frappe.new_doc("Purchase Order")
		po.company = COMPANY
		po.supplier = SUPPLIER
		po.transaction_date = nowdate()
		po.schedule_date = add_days(nowdate(), 7)
		po.append("items", {"item_code": NON_STOCK_ITEM, "qty": 1, "rate": 100, "schedule_date": po.schedule_date})
		po.run_method("set_missing_values")
		po.insert()
		return po


def make_payment_entry(user="Administrator", amount=100):
	with as_user(user):
		pe = frappe.new_doc("Payment Entry")
		pe.payment_type = "Receive"
		pe.company = COMPANY
		pe.posting_date = nowdate()
		pe.party_type = "Customer"
		pe.party = CUSTOMER
		pe.paid_from = frappe.get_cached_value("Company", COMPANY, "default_receivable_account")
		pe.paid_to = "Cash - BEPL"
		pe.paid_from_account_currency = pe.paid_to_account_currency = "LKR"
		pe.source_exchange_rate = pe.target_exchange_rate = 1
		pe.paid_amount = pe.received_amount = amount
		pe.insert()
		return pe


def make_petty_cash_voucher(user="Administrator"):
	with as_user(user):
		pcv = frappe.get_doc(
			{
				"doctype": "Petty Cash Voucher",
				"company": COMPANY,
				"posting_date": nowdate(),
				"requested_by": user,
				"petty_cash_account": "Petty Cash - BEPL",
				"expense_account": "Accounting Charges - BEPL",
				"cost_center": "Main - BEPL",
				"amount": 10,
				"purpose": "blueline test",
			}
		)
		pcv.insert()
		return pcv


FACTORIES = {
	"Quotation": make_quotation,
	"Purchase Order": make_purchase_order,
	"Sales Invoice": make_sales_invoice,
	"Payment Entry": make_payment_entry,
	"Petty Cash Voucher": make_petty_cash_voucher,
}
