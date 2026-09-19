import frappe

OLD_PARENT = "Global COA Mapping Settings"
OLD_CHILD = "Company COA Mapping"
NEW_DOCTYPE = "Company COA Configuration"

CONFIG_FIELDS = (
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
)


def execute():
	copy_existing_mappings()
	remove_old_doctypes()


def copy_existing_mappings():
	"""Carry any rows already entered in the old child table over to per-company documents."""
	if not frappe.db.table_exists(OLD_CHILD):
		return

	columns = ", ".join(f"`{fieldname}`" for fieldname in CONFIG_FIELDS)
	rows = frappe.db.sql(
		f"select {columns} from `tab{OLD_CHILD}` where parent = %s order by idx",
		OLD_PARENT,
		as_dict=True,
	)

	for row in rows:
		if not row.company or frappe.db.exists(NEW_DOCTYPE, row.company):
			continue
		frappe.get_doc({"doctype": NEW_DOCTYPE, **row}).insert(ignore_permissions=True)


def remove_old_doctypes():
	# delete_doc on a DocType removes the DocType record only; it does not drop the SQL table
	# nor the Single's stored values, so both are cleaned up explicitly.
	for doctype in (OLD_PARENT, OLD_CHILD):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True)

	frappe.db.delete("Singles", {"doctype": OLD_PARENT})
	frappe.db.sql_ddl(f"drop table if exists `tab{OLD_CHILD}`")
