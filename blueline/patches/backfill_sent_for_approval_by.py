import frappe
from frappe.utils.fixtures import sync_fixtures

from blueline.server_scripts.self_approval import (
	APPROVAL_DOCTYPES,
	PENDING_APPROVAL_STATE,
	SENT_BY_FIELD,
)


def execute():
	# Fixtures normally sync after post_model_sync patches; the custom field must exist first.
	sync_fixtures("blueline")

	# Documents already waiting for approval at deploy time were sent before the field
	# existed. apply_workflow leaves a "Workflow" comment owned by whoever ran the action,
	# so the latest "Pending Approval" comment identifies the sender. A document with no
	# such comment (state changed by a plain save) is left blank: the creator check still applies.
	for doctype in APPROVAL_DOCTYPES:
		if not frappe.db.has_column(doctype, SENT_BY_FIELD):
			continue

		pending = frappe.get_all(
			doctype,
			filters={"docstatus": 0, "workflow_state": PENDING_APPROVAL_STATE, SENT_BY_FIELD: ["is", "not set"]},
			pluck="name",
		)
		for name in pending:
			sender = frappe.db.get_value(
				"Comment",
				{
					"reference_doctype": doctype,
					"reference_name": name,
					"comment_type": "Workflow",
					"content": PENDING_APPROVAL_STATE,
				},
				"owner",
				order_by="creation desc",
			)
			if sender:
				frappe.db.set_value(doctype, name, SENT_BY_FIELD, sender, update_modified=False)
