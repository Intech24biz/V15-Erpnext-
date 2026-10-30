"""Earliest Allowed Posting Date (Company COA Configuration) is enforced on the server, on
`validate`, so it holds for a plain insert/save through the API exactly as for the form.
A System Manager may still back-date; the override is recorded on the document."""

import frappe
from frappe.utils import add_days, nowdate

from blueline.tests.utils import (
	COMPANY,
	GI_SALES,
	GI_TECH,
	SYSTEM_MANAGER,
	BluelineTestCase,
	act,
	as_user,
	make_petty_cash_voucher,
	make_sales_invoice,
)

CONFIG = "Company COA Configuration"
REFUSED = "postings before"


def set_cutoff(date):
	frappe.db.set_value(CONFIG, COMPANY, "earliest_allowed_posting_date", date)


def journal_entry(user, posting_date):
	with as_user(user):
		je = frappe.new_doc("Journal Entry")
		je.update({"voucher_type": "Journal Entry", "company": COMPANY, "posting_date": posting_date})
		for debit, credit in ((10, 0), (0, 10)):
			je.append(
				"accounts",
				{
					"account": "Cash - BEPL",
					"debit_in_account_currency": debit,
					"credit_in_account_currency": credit,
				},
			)
		je.insert()
		return je


class TestPostingDateGuard(BluelineTestCase):
	def setUp(self):
		super().setUp()
		self.assertTrue(frappe.db.exists(CONFIG, COMPANY), "local site needs Blueline's COA configuration")
		set_cutoff(nowdate())

	def test_backdated_documents_are_refused_on_insert(self):
		yesterday = add_days(nowdate(), -1)
		cases = {
			"Journal Entry": lambda: journal_entry(GI_TECH, yesterday),
			"Sales Invoice": lambda: self.backdated(make_sales_invoice(GI_SALES), yesterday, GI_SALES),
			"Petty Cash Voucher": lambda: self.backdated(make_petty_cash_voucher(GI_TECH), yesterday, GI_TECH),
		}
		for doctype, attempt in cases.items():
			with self.subTest(doctype=doctype):
				self.assertRefused(attempt, REFUSED)

	def backdated(self, doc, date, user):
		"""An existing draft re-saved with an earlier date, the same call the REST API makes."""
		with as_user(user):
			doc = frappe.get_doc(doc.doctype, doc.name)
			doc.posting_date = date
			if doc.doctype == "Sales Invoice":
				doc.set_posting_time = 1
				doc.due_date = nowdate()
			doc.save()

	def test_on_or_after_the_cutoff_is_allowed(self):
		self.assertTrue(journal_entry(GI_TECH, nowdate()).name)
		self.assertTrue(make_sales_invoice(GI_SALES).name)

	def test_no_cutoff_means_no_restriction(self):
		set_cutoff(None)
		self.assertTrue(journal_entry(GI_TECH, add_days(nowdate(), -400)).name)

	def test_system_manager_override_is_recorded_on_the_document(self):
		je = journal_entry(SYSTEM_MANAGER, add_days(nowdate(), -1))
		comments = frappe.get_all(
			"Comment",
			filters={"reference_doctype": "Journal Entry", "reference_name": je.name, "comment_type": "Info"},
			pluck="content",
		)
		self.assertTrue(any("Posting date override" in c and SYSTEM_MANAGER in c for c in comments), comments)

	def test_another_companys_cutoff_does_not_apply(self):
		other = frappe.db.get_value(CONFIG, {"name": ["!=", COMPANY]}, "name")
		if not other:
			self.skipTest("only one company is configured")
		frappe.db.set_value(CONFIG, other, "earliest_allowed_posting_date", add_days(nowdate(), 365))
		set_cutoff(None)
		self.assertTrue(act(GI_TECH, journal_entry, GI_TECH, nowdate()).name)
