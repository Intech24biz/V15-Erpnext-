import frappe
from frappe.utils import cint

from blueline.blueline.doctype.sales_commission_entry.sales_commission_entry import APPROVAL_TICKS
from blueline.server_scripts.sales_commission import ENTRY_DOCTYPE


def execute():
	# Entries ticked before the "... Approval By" fields existed. Sales Commission Entry has
	# track_changes on, so the Version log names the user whose save set each tick. Where no
	# version shows it, the field stays blank and the entry can't be Approved until re-ticked.
	entries = frappe.get_all(
		ENTRY_DOCTYPE,
		or_filters={tick: 1 for tick in APPROVAL_TICKS},
		fields=["name", *APPROVAL_TICKS, *APPROVAL_TICKS.values()],
	)
	for entry in entries:
		updates = {}
		for tick, approver_field in APPROVAL_TICKS.items():
			if entry[tick] and not entry[approver_field]:
				user = _last_user_to_tick(entry.name, tick)
				if user:
					updates[approver_field] = user
		if updates:
			frappe.db.set_value(ENTRY_DOCTYPE, entry.name, updates, update_modified=False)


def _last_user_to_tick(entry_name, tick):
	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": ENTRY_DOCTYPE, "docname": entry_name},
		fields=["owner", "data"],
		order_by="creation desc",
	)
	for version in versions:
		for change in frappe.parse_json(version.data).get("changed") or []:
			if change[0] == tick and cint(change[2]):
				return version.owner
	return None
