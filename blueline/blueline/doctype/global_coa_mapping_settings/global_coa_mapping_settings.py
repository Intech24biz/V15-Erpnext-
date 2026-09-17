import frappe
from frappe import _
from frappe.model.document import Document

# Account Link fields that must (a) belong to the row's company and (b) be leaf accounts.
ACCOUNT_FIELDS = (
	"default_cash_account",
	"default_bank_account",
	"temporary_opening_account",
	"stock_adjustment_account",
	"stock_received_but_not_billed",
	"expenses_included_in_valuation",
	"exchange_gain_loss_account",
	"foreign_currency_revaluation_account",
	"inter_company_clearing_account",
)

# Non-Account Link fields that must belong to the row's company (no leaf-account check).
NON_ACCOUNT_COMPANY_FIELDS = {
	"default_cost_center": "Cost Center",
	"default_warehouse": "Warehouse",
}

FIELD_LABELS = {
	"default_cash_account": "Default Cash Account",
	"default_bank_account": "Default Bank Account",
	"temporary_opening_account": "Temporary Opening Account",
	"default_cost_center": "Default Cost Center",
	"stock_adjustment_account": "Stock Adjustment Account",
	"stock_received_but_not_billed": "Stock Received But Not Billed",
	"expenses_included_in_valuation": "Expenses Included In Valuation",
	"default_warehouse": "Default Warehouse",
	"exchange_gain_loss_account": "Exchange Gain/Loss Account",
	"foreign_currency_revaluation_account": "Foreign Currency Revaluation Account",
	"inter_company_clearing_account": "Inter Company Clearing Account",
}


class GlobalCOAMappingSettings(Document):
	def validate(self):
		for row in self.company_mappings:
			self.validate_row(row)

	def validate_row(self, row):
		if not row.company:
			return

		for fieldname in ACCOUNT_FIELDS:
			value = row.get(fieldname)
			if not value:
				continue

			account = frappe.db.get_value("Account", value, ["company", "is_group"], as_dict=True)

			if account.company != row.company:
				frappe.throw(
					_('Row #{0}: {1} "{2}" does not belong to Company {3}').format(
						row.idx, _(FIELD_LABELS[fieldname]), value, row.company
					)
				)

			if account.is_group:
				frappe.throw(
					_('Row #{0}: {1} "{2}" is a group account. Please select a leaf account.').format(
						row.idx, _(FIELD_LABELS[fieldname]), value
					)
				)

		for fieldname, linked_doctype in NON_ACCOUNT_COMPANY_FIELDS.items():
			value = row.get(fieldname)
			if not value:
				continue

			record_company = frappe.db.get_value(linked_doctype, value, "company")
			if record_company != row.company:
				frappe.throw(
					_('Row #{0}: {1} "{2}" does not belong to Company {3}').format(
						row.idx, _(FIELD_LABELS[fieldname]), value, row.company
					)
				)

		if not row.default_valuation_method:
			row.default_valuation_method = "FIFO"
