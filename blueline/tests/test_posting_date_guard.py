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


class TestStockAndAssetDoctypes(BluelineTestCase):
	"""Stock Reconciliation posts on posting_date; ERPNext v15 posts an Asset Repair on its
	completion_date and an Asset Value Adjustment's Journal Entry on its `date`."""

	DATE_FIELDS = {
		"Stock Reconciliation": "posting_date",
		"Asset Repair": "completion_date",
		"Asset Value Adjustment": "date",
	}

	def setUp(self):
		super().setUp()
		set_cutoff(nowdate())

	def test_guard_is_registered_on_validate_for_each(self):
		from blueline.server_scripts.posting_date_guard import DATE_FIELD_OVERRIDES

		doc_events = frappe.get_hooks("doc_events")
		guard = "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date"
		for doctype, field in self.DATE_FIELDS.items():
			with self.subTest(doctype=doctype):
				self.assertIn(guard, doc_events.get(doctype, {}).get("validate", []))
				self.assertTrue(frappe.get_meta(doctype).has_field(field), f"{doctype} has no {field}")
				self.assertEqual(DATE_FIELD_OVERRIDES.get(doctype, "posting_date"), field)

	def test_backdated_asset_documents_are_refused(self):
		# No Asset exists on this site to build a full document from, so the guard runs on a
		# document of each doctype carrying the company and the date field it posts on.
		from blueline.server_scripts.posting_date_guard import enforce_earliest_posting_date

		yesterday = add_days(nowdate(), -1)
		for doctype in ("Asset Repair", "Asset Value Adjustment"):
			field = self.DATE_FIELDS[doctype]
			with self.subTest(doctype=doctype):
				doc = frappe.new_doc(doctype)
				doc.update({"company": COMPANY, field: yesterday})
				self.assertRefused(lambda: act(GI_TECH, enforce_earliest_posting_date, doc), REFUSED)
				doc.set(field, nowdate())
				act(GI_TECH, enforce_earliest_posting_date, doc)  # on the cutoff: allowed

	def test_a_pending_asset_repair_is_not_checked(self):
		from blueline.server_scripts.posting_date_guard import enforce_earliest_posting_date

		doc = frappe.new_doc("Asset Repair")
		doc.update({"company": COMPANY, "failure_date": add_days(nowdate(), -30)})  # no completion date yet
		act(GI_TECH, enforce_earliest_posting_date, doc)

	def test_backdated_stock_reconciliation_is_refused_on_insert(self):
		bin_row = frappe.db.sql(
			"""select b.item_code, b.warehouse, b.actual_qty, b.valuation_rate from `tabBin` b
			join `tabWarehouse` w on w.name = b.warehouse
			where w.company = %s and b.actual_qty > 0 and b.valuation_rate > 0 limit 1""",
			COMPANY,
			as_dict=True,
		)
		if not bin_row:
			self.skipTest("no stock on hand for this company")
		bin_row = bin_row[0]

		def reconcile(posting_date):
			with as_user(GI_SALES):  # a Stock Manager, not a System Manager
				sr = frappe.new_doc("Stock Reconciliation")
				# The company has no default Stock Adjustment Account; use its Stock Adjustment-type account.
				account = frappe.db.get_value(
					"Account", {"company": COMPANY, "account_type": "Stock Adjustment", "is_group": 0}, "name"
				)
				cost_center = frappe.get_cached_value("Company", COMPANY, "cost_center")
				sr.update(
					{
						"company": COMPANY,
						"purpose": "Stock Reconciliation",
						"posting_date": posting_date,
						"set_posting_time": 1,
						"expense_account": account,
						"cost_center": cost_center,
					}
				)
				sr.append(
					"items",
					{
						"item_code": bin_row.item_code,
						"warehouse": bin_row.warehouse,
						"qty": bin_row.actual_qty + 1,
						"valuation_rate": bin_row.valuation_rate,
					},
				)
				sr.insert()
				return sr

		self.assertRefused(lambda: reconcile(add_days(nowdate(), -1)), REFUSED)
		self.assertTrue(reconcile(nowdate()).name)

