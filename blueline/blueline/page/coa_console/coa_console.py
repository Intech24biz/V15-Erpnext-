import frappe
from frappe import _

DOCTYPE = "Company COA Configuration"

CONFIG_FIELDS = [
	"company",
	"default_cash_account",
	"default_bank_account",
	"temporary_opening_account",
	"default_cost_center",
	"stock_adjustment_account",
	"stock_received_but_not_billed",
	"expenses_included_in_valuation",
	"default_valuation_method",
	"default_warehouse",
	"exchange_gain_loss_account",
	"foreign_currency_revaluation_account",
	"inter_company_clearing_account",
	"earliest_allowed_posting_date",
]

WRITE_ROLES = {"Financial Manager", "System Manager"}


def _check_permission():
	if not frappe.has_permission(DOCTYPE, "read"):
		frappe.throw(_("Not permitted to view {0}").format(_(DOCTYPE)), frappe.PermissionError)


@frappe.whitelist()
def get_configurations():
	_check_permission()

	# get_list (not get_all / db.sql) so the user's role permissions and Company User
	# Permissions are applied by the framework; a restricted user only receives their companies.
	configurations = frappe.get_list(
		DOCTYPE,
		fields=["name", *CONFIG_FIELDS],
		order_by="company asc",
		limit_page_length=0,
	)

	for config in configurations:
		config["can_write"] = bool(frappe.has_permission(DOCTYPE, "write", doc=config.name))

	return {
		"configurations": configurations,
		"can_write_any": bool(WRITE_ROLES & set(frappe.get_roles())),
	}
