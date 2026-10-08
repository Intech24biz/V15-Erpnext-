import frappe
from frappe.model.utils.rename_field import rename_field

from blueline.server_scripts.sales_commission import ENTRY_DOCTYPE, resolve_commission_leader


def execute():
	# Sales Commission Entry.sales_person is now matched_sales_person (who the rule
	# matched on); commission_credited_to (the resolved group leader) is new.
	if frappe.db.has_column(ENTRY_DOCTYPE, "sales_person"):
		rename_field(ENTRY_DOCTYPE, "sales_person", "matched_sales_person")

	entries = frappe.get_all(
		ENTRY_DOCTYPE,
		filters={"matched_sales_person": ["is", "set"], "commission_credited_to": ["is", "not set"]},
		fields=["name", "matched_sales_person"],
	)
	for entry in entries:
		frappe.db.set_value(
			ENTRY_DOCTYPE,
			entry.name,
			"commission_credited_to",
			resolve_commission_leader(entry.matched_sales_person),
			update_modified=False,
		)
