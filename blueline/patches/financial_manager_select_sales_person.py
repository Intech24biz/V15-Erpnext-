"""Financial Manager: Select permission on Sales Person.

Filtering the Sales Commission Entry list by Matched Sales Person or Commission Credited To
validates the chosen name with frappe.client.validate_link, which needs Read or Select on
Sales Person. Financial Manager has neither by default, so the filter failed with "You do not
have Read or Select Permissions for Sales Person" and the list showed nothing. Select only:
the role can pick and filter by a sales person, but still cannot open Sales Person records.

Runs once per site. Like Role Permission Manager, adding a rule turns Sales Person's
permissions into custom permissions (the standard rules are copied over first).
"""

import frappe
from frappe.permissions import add_permission

DOCTYPE = "Sales Person"
ROLE = "Financial Manager"


def execute():
	if not frappe.db.exists("Role", ROLE):
		return

	existing = frappe.db.get_value(
		"Custom DocPerm",
		{"parent": DOCTYPE, "role": ROLE, "permlevel": 0, "if_owner": 0},
		["name", "select", "read"],
		as_dict=True,
	)
	if existing:
		if not (existing.select or existing.read):
			frappe.db.set_value("Custom DocPerm", existing.name, "select", 1)
	else:
		name = add_permission(DOCTYPE, ROLE, 0, "select")
		# A new Custom DocPerm row has Read ticked by default; this rule is Select only.
		if name:
			frappe.db.set_value("Custom DocPerm", name, "read", 0)

	frappe.clear_cache(doctype=DOCTYPE)
