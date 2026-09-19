import frappe
from frappe import _
from frappe.model.document import Document

# Account Link fields that must (a) belong to this document's company and (b) be leaf accounts.
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

# Non-Account Link fields that must belong to this document's company (no leaf check).
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


class CompanyCOAConfiguration(Document):
	def validate(self):
		self.validate_account_fields()
		self.validate_cost_center_and_warehouse()
		self.set_default_valuation_method()

	def validate_account_fields(self):
		for fieldname in ACCOUNT_FIELDS:
			value = self.get(fieldname)
			if not value:
				continue

			account = frappe.db.get_value("Account", value, ["company", "is_group"], as_dict=True)

			if account.company != self.company:
				self.throw_wrong_company(fieldname, value)

			if account.is_group:
				frappe.throw(
					_('{0} "{1}" is a group account. Please select a leaf account.').format(
						_(FIELD_LABELS[fieldname]), value
					)
				)

	def validate_cost_center_and_warehouse(self):
		for fieldname, linked_doctype in NON_ACCOUNT_COMPANY_FIELDS.items():
			value = self.get(fieldname)
			if not value:
				continue

			if frappe.db.get_value(linked_doctype, value, "company") != self.company:
				self.throw_wrong_company(fieldname, value)

	def throw_wrong_company(self, fieldname, value):
		frappe.throw(
			_('{0} "{1}" does not belong to Company {2}').format(
				_(FIELD_LABELS[fieldname]), value, self.company
			)
		)

	def set_default_valuation_method(self):
		if not self.default_valuation_method:
			self.default_valuation_method = "FIFO"
