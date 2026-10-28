import frappe
from frappe import _

SYSTEM_MANAGER = "System Manager"


def only_system_manager(doc, method=None):
	"""Workflow `validate` / `on_trash`: a workflow decides who may approve, so only a System
	Manager may change or delete one. Frappe already grants Workflow write to System Manager
	alone; this keeps it that way if Workflow permissions are later widened in Role
	Permission Manager. Every change is kept in the workflow's Version history (Frappe's
	Workflow tracks changes). bench migrate / install run as Administrator.
	"""
	if frappe.session.user == "Administrator" or SYSTEM_MANAGER in frappe.get_roles():
		return
	frappe.throw(
		_("Only a System Manager can change or delete a workflow."),
		frappe.PermissionError,
		title=_("Not Permitted"),
	)
