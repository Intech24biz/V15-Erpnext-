"""Read-only question: does changing "Default Valuation Method" in the COA Console touch any
Item, Bin or Stock Ledger record? (Answer: no — it is stored on the Company COA
Configuration only, and nothing reads it yet.)"""

import frappe

from blueline.blueline.page.coa_console.coa_console import save_configuration
from blueline.tests.utils import COMPANY, BluelineTestCase


def stock_snapshot():
	return {
		"item_valuation_methods": frappe.db.sql("select name, valuation_method, modified from tabItem order by name"),
		"bins": frappe.db.sql(
			"select name, valuation_rate, stock_value, actual_qty, modified from tabBin order by name"
		),
		"stock_ledger": frappe.db.sql(
			"select name, valuation_rate, stock_value, stock_value_difference, modified "
			"from `tabStock Ledger Entry` order by name"
		),
		"stock_settings_valuation_method": frappe.db.get_single_value("Stock Settings", "valuation_method"),
	}


class TestDefaultValuationMethod(BluelineTestCase):
	def test_changing_it_in_the_console_touches_no_stock_records(self):
		current = frappe.db.get_value("Company COA Configuration", COMPANY, "default_valuation_method")
		new = "Moving Average" if current == "FIFO" else "FIFO"
		before = stock_snapshot()

		result = save_configuration(COMPANY, frappe.as_json({"default_valuation_method": new}))

		self.assertTrue(result["ok"], result)
		self.assertEqual(frappe.db.get_value("Company COA Configuration", COMPANY, "default_valuation_method"), new)
		self.assertEqual(stock_snapshot(), before)
