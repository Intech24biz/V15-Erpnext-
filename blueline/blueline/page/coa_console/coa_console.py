import frappe
from frappe import _
from frappe.utils import strip_html

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

# `company` is the document name and is set-only-once, so it is never editable from the console.
EDITABLE_FIELDS = [fieldname for fieldname in CONFIG_FIELDS if fieldname != "company"]

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


@frappe.whitelist(methods=["POST"])
def save_configuration(company, values):
	# The client-side "Editable" badge is only a hint; write permission is re-checked here
	# against the specific document (role permissions + Company User Permissions).
	doc = None
	if isinstance(company, str) and frappe.db.exists(DOCTYPE, company):
		doc = frappe.get_doc(DOCTYPE, company)

	# A missing document and a forbidden one give the same answer so the endpoint cannot be
	# used to probe which companies have a configuration.
	if not doc or not frappe.has_permission(DOCTYPE, "write", doc=doc):
		frappe.throw(
			_("Not permitted to update the COA configuration for this company"),
			frappe.PermissionError,
		)

	values = frappe.parse_json(values)
	if not isinstance(values, dict):
		frappe.throw(_("Invalid values"))

	not_editable = sorted(set(values) - set(EDITABLE_FIELDS))
	if not_editable:
		frappe.throw(_("These fields cannot be edited here: {0}").format(", ".join(not_editable)))

	for fieldname, value in values.items():
		if value is not None and not isinstance(value, str):
			frappe.throw(_("Invalid value for {0}").format(fieldname))
		doc.set(fieldname, value or None)

	# doc.save() (not db.set_value) so validate() and Track Changes run, and the framework
	# checks write permission a second time; ignore_permissions is deliberately not set.
	try:
		doc.save()
	except frappe.ValidationError as e:
		frappe.db.rollback()
		frappe.clear_messages()
		return {"ok": False, "message": strip_html(str(e))}

	configuration = {fieldname: doc.get(fieldname) for fieldname in ["name", *CONFIG_FIELDS]}
	configuration["can_write"] = True

	return {
		"ok": True,
		"message": _("Saved COA configuration for {0}").format(doc.name),
		"configuration": configuration,
	}
