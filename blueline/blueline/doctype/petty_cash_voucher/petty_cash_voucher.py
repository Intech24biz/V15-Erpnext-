import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

ALLOWED_PETTY_CASH_ACCOUNT_TYPES = ("Cash", "Bank")


class PettyCashVoucher(Document):
	def validate(self):
		self.validate_amount()
		self.validate_accounts()

	def validate_amount(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero"))

	def validate_accounts(self):
		for fieldname, label in (
			("petty_cash_account", _("Petty Cash Account")),
			("expense_account", _("Expense Account")),
		):
			account = self.get(fieldname)
			account_company = frappe.db.get_value("Account", account, "company")
			if account_company != self.company:
				frappe.throw(
					_("{0} {1} does not belong to Company {2}").format(label, account, self.company)
				)

		petty_cash_account_type = frappe.db.get_value("Account", self.petty_cash_account, "account_type")
		if petty_cash_account_type not in ALLOWED_PETTY_CASH_ACCOUNT_TYPES:
			frappe.throw(_("Petty Cash Account must be of type Cash or Bank"))

	def on_submit(self):
		je = self.create_journal_entry()
		self.db_set("journal_entry", je.name)

	def create_journal_entry(self):
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Cash Entry"
		je.posting_date = self.posting_date
		je.company = self.company
		je.user_remark = _("Petty Cash Voucher {0}: {1}").format(self.name, self.purpose)

		je.append(
			"accounts",
			{
				"account": self.expense_account,
				"cost_center": self.cost_center,
				"debit_in_account_currency": self.amount,
				"debit": self.amount,
			},
		)
		je.append(
			"accounts",
			{
				"account": self.petty_cash_account,
				"credit_in_account_currency": self.amount,
				"credit": self.amount,
			},
		)

		je.insert(ignore_permissions=True)
		je.submit()
		return je

	def on_cancel(self):
		if not self.journal_entry:
			return

		je_docstatus = frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus")
		if je_docstatus == 1:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			je.cancel()
