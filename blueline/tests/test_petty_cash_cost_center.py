"""Petty Cash Voucher approval posts its Journal Entry on the voucher company's own cost centre,
whatever the approving user's or the site's default company is; and Financial Manager can
filter commission entries by sales person."""

import frappe
from frappe.utils import getdate, nowdate

from blueline.tests.utils import (
	COMPANY,
	FINANCIAL_MANAGER,
	GI_MANAGEMENT,
	GI_SALES_2,
	GI_TECH,
	SYSTEM_MANAGER,
	BluelineTestCase,
	as_user,
	reload,
	workflow,
)

OTHER_COMPANIES = ("General Innovations (Pvt) Ltd", "Global Intech Pte Ltd")


def posting_date_for(company):
	"""Today, or the last day of the company's latest fiscal year if that has already ended
	(Global Intech's books stop at an earlier year in this data)."""
	last = frappe.db.sql(
		"""select max(fy.year_end_date) from `tabFiscal Year` fy
		left join `tabFiscal Year Company` fyc on fyc.parent = fy.name
		where fy.disabled = 0 and (fyc.company = %s or fyc.company is null)""",
		company,
	)[0][0]
	return min(getdate(nowdate()), getdate(last)) if last else nowdate()


def voucher_for(company, user=GI_TECH):
	"""Draft Petty Cash Voucher for `company`, with a cash and an expense account of that company."""
	with as_user(user):
		pcv = frappe.get_doc(
			{
				"doctype": "Petty Cash Voucher",
				"company": company,
				"posting_date": posting_date_for(company),
				"requested_by": user,
				"petty_cash_account": frappe.db.get_value(
					"Account", {"company": company, "account_type": "Cash", "is_group": 0}
				),
				"expense_account": frappe.db.get_value(
					"Account", {"company": company, "root_type": "Expense", "is_group": 0}
				),
				"amount": 10,
				"purpose": "blueline test",
			}
		)
		pcv.insert()
		return pcv


def approve(pcv, approver=GI_MANAGEMENT):
	workflow(pcv, "Send for Approval", GI_SALES_2)
	workflow(pcv, "Approve", approver)
	return frappe.get_doc("Journal Entry", reload(pcv).journal_entry)


# The GI users in this data hold User Permissions for the two Sri Lankan companies only, so a
# Global Intech voucher is raised by Administrator and approved by the System Manager user.
PEOPLE = {
	"General Innovations (Pvt) Ltd": (GI_TECH, GI_MANAGEMENT),
	"Global Intech Pte Ltd": ("Administrator", SYSTEM_MANAGER),
}


class TestPettyCashCostCenter(BluelineTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.clear_cache)

	def assertPostedOnCompanyCostCenter(self, je, company):
		default = frappe.get_cached_value("Company", company, "cost_center")
		self.assertEqual(je.docstatus, 1)
		self.assertEqual({row.cost_center for row in je.accounts}, {default})

	def set_site_default_company(self, company):
		frappe.db.set_default("company", company)
		frappe.clear_cache()

	def test_site_default_company_is_another_company(self):
		self.set_site_default_company(OTHER_COMPANIES[1])
		self.assertPostedOnCompanyCostCenter(approve(voucher_for(COMPANY)), COMPANY)

	def test_approver_default_company_is_another_company(self):
		frappe.defaults.set_user_default("company", OTHER_COMPANIES[0], GI_MANAGEMENT)
		frappe.clear_cache(user=GI_MANAGEMENT)
		self.assertPostedOnCompanyCostCenter(approve(voucher_for(COMPANY)), COMPANY)

	def test_every_company(self):
		self.set_site_default_company(COMPANY)
		for company in OTHER_COMPANIES:
			with self.subTest(company=company):
				creator, approver = PEOPLE[company]
				self.assertPostedOnCompanyCostCenter(approve(voucher_for(company, creator), approver), company)

	def test_company_without_default_cost_center_is_named(self):
		pcv = voucher_for(COMPANY)
		workflow(pcv, "Send for Approval", GI_SALES_2)
		frappe.db.set_value("Company", COMPANY, "cost_center", None)
		frappe.clear_document_cache("Company", COMPANY)
		self.assertRefused(lambda: workflow(pcv, "Approve", GI_MANAGEMENT), f"{COMPANY}</strong> has no Default Cost Center")
		frappe.clear_document_cache("Company", COMPANY)

	def test_cost_center_of_another_company_is_refused(self):
		pcv = reload(voucher_for(COMPANY))
		pcv.cost_center = frappe.get_cached_value("Company", OTHER_COMPANIES[0], "cost_center")
		with as_user(GI_TECH):
			self.assertRefused(pcv.save, "does not belong to Company")


class TestFinancialManagerSalesPersonFilter(BluelineTestCase):
	def test_financial_manager_can_filter_by_sales_person(self):
		sales_person = frappe.db.get_value("Sales Person", {"is_group": 0})
		with as_user(FINANCIAL_MANAGER):
			self.assertTrue(frappe.has_permission("Sales Person", "select"))
			rule = frappe.db.get_value("Custom DocPerm", {"parent": "Sales Person", "role": "Financial Manager", "permlevel": 0}, ["select", "read"], as_dict=True)
			self.assertEqual((rule.select, rule.read), (1, 0), "Financial Manager gets Select only on Sales Person")
			from frappe.client import validate_link

			self.assertEqual(validate_link("Sales Person", sales_person).get("name"), sales_person)
