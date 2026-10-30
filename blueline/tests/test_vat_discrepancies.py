"""VAT Dashboard: wrong-direction balances (Output with a debit balance, Input with a credit
balance) are listed as discrepancies whichever way the cards are grouped, and the raw and
regrouped summaries keep the same net."""

from datetime import date
from unittest.mock import patch

import frappe

from blueline.blueline.page.vat_dashboard import vat_dashboard
from blueline.tests.utils import COMPANY, BluelineTestCase

OUTPUT_OK = "Output VAT 18% - T"
OUTPUT_WRONG = "Output VAT Old - T"
INPUT_OK = "Input VAT 18% - T"
INPUT_WRONG = "Input VAT Imports - T"


def gl(account, debit=0, credit=0, day=date(2026, 10, 1)):
	return frappe._dict(account=account, posting_date=day, debit=debit, credit=credit)


def vat_data(rows):
	accounts = [
		frappe._dict(name=OUTPUT_OK, root_type="Liability"),
		frappe._dict(name=OUTPUT_WRONG, root_type="Liability"),
		frappe._dict(name=INPUT_OK, root_type="Asset"),
		frappe._dict(name=INPUT_WRONG, root_type="Asset"),
	]
	with patch.object(vat_dashboard, "_get_vat_accounts", return_value=accounts), patch.object(
		vat_dashboard, "_get_gl_entries", return_value=rows
	):
		return vat_dashboard.get_vat_data(COMPANY)


class TestDiscrepancies(BluelineTestCase):
	def test_wrong_direction_accounts_are_listed(self):
		data = vat_data(
			[
				gl(OUTPUT_OK, credit=1800),
				gl(OUTPUT_WRONG, debit=500),
				gl(INPUT_OK, debit=900),
				gl(INPUT_WRONG, credit=200),
			]
		)
		found = {(d["account"], d["classification"], d["amount"], d["actual_balance"]) for d in data["discrepancies"]}
		self.assertEqual(
			found,
			{(OUTPUT_WRONG, "output", 500, "debit"), (INPUT_WRONG, "input", 200, "credit")},
		)

	def test_a_clean_ledger_has_no_discrepancies(self):
		data = vat_data([gl(OUTPUT_OK, credit=1800), gl(INPUT_OK, debit=900), gl(OUTPUT_WRONG, credit=10)])
		self.assertEqual(data["discrepancies"], [])

	def test_raw_and_regrouped_summaries_have_the_same_net(self):
		data = vat_data([gl(OUTPUT_OK, credit=1800), gl(OUTPUT_WRONG, debit=500), gl(INPUT_OK, debit=900)])
		raw, regrouped = data["raw_summary"], data["summary"]
		self.assertEqual((raw["total_output"], raw["total_input"]), (1300, 900))
		self.assertEqual((regrouped["total_output"], regrouped["total_input"]), (1800, 1400))
		self.assertEqual(raw["net_vat"], regrouped["net_vat"])
		self.assertEqual(raw["net_vat"], 400)

	def test_a_balance_is_judged_over_the_period_not_per_entry(self):
		# A debit on an Output account (e.g. a correcting entry) is fine while the account's
		# net for the period is still a credit.
		data = vat_data([gl(OUTPUT_OK, credit=1000), gl(OUTPUT_OK, debit=300, day=date(2026, 10, 15))])
		self.assertEqual(data["discrepancies"], [])

	def test_no_data_returns_an_empty_list(self):
		self.assertEqual(vat_data([])["discrepancies"], [])
