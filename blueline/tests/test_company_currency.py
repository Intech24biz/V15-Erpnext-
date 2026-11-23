"""Every amount is shown in its own company's currency, and amounts of companies with different
currencies are never added together. Read-only checks: nothing is created."""

import frappe

from blueline.blueline.page.business_kpi_dashboard.business_kpi_dashboard import (
	get_commission_payroll,
	get_financial_health,
	get_sales_performance,
)
from blueline.blueline.page.sales_commission_register.sales_commission_register import get_entries
from blueline.blueline.page.vat_dashboard.vat_dashboard import get_vat_data
from blueline.money import company_currency, currency_sections, format_money
from blueline.tests.utils import COMPANY, SYSTEM_MANAGER, BluelineTestCase, act


def companies():
	return frappe.get_all("Company", fields=["name", "default_currency"])


class TestCompanyCurrency(BluelineTestCase):
	def test_company_currency_is_the_company_default(self):
		for c in companies():
			with self.subTest(company=c.name):
				self.assertEqual(company_currency(c.name), c.default_currency)

	def test_amounts_use_the_currency_symbol(self):
		for c in companies():
			symbol = frappe.db.get_value("Currency", c.default_currency, "symbol") or c.default_currency
			with self.subTest(currency=c.default_currency):
				self.assertIn(symbol, format_money(1234.5, c.default_currency))

	def test_sections_never_mix_currencies(self):
		names = [c.name for c in companies()]
		data = currency_sections(names, lambda scope: {"scope": scope})
		self.assertEqual(len(data["sections"]), len({company_currency(n) for n in names}))
		for section in data["sections"]:
			with self.subTest(currency=section["currency"]):
				self.assertEqual({company_currency(n) for n in section["companies"]}, {section["currency"]})

	def test_one_company_keeps_the_top_level_keys(self):
		data = currency_sections([COMPANY], lambda scope: {"value": 1})
		self.assertEqual((data["value"], data["currency"]), (1, company_currency(COMPANY)))

	def test_vat_dashboard_is_in_the_selected_company_currency(self):
		for c in companies():
			with self.subTest(company=c.name):
				self.assertEqual(get_vat_data(c.name)["currency"], c.default_currency)

	def test_kpi_dashboard_all_companies_is_split_by_currency(self):
		for endpoint in (get_sales_performance, get_financial_health, get_commission_payroll):
			data = act(SYSTEM_MANAGER, endpoint)
			for section in data["sections"]:
				with self.subTest(endpoint=endpoint.__name__, currency=section["currency"]):
					self.assertEqual({company_currency(n) for n in section["companies"]}, {section["currency"]})

	def test_register_totals_are_kept_per_currency(self):
		data = act(SYSTEM_MANAGER, get_entries)
		for entry in data["entries"]:
			self.assertEqual(entry.currency, company_currency(entry.company))
		for status, bucket in data["summary"].items():
			currencies = [a["currency"] for a in bucket["amounts"]]
			with self.subTest(status=status):
				self.assertEqual(len(currencies), len(set(currencies)))

	def test_commission_adjustment_amounts_follow_the_company(self):
		meta = frappe.get_meta("Sales Commission Adjustment")
		for df in meta.fields:
			if df.fieldtype == "Currency":
				with self.subTest(field=df.fieldname):
					self.assertEqual(df.options, "Company:company:default_currency")
