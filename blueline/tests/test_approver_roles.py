"""Approver roles are changed by a System Manager in the Workflow screen and stay changed.

Before this, the GI workflows and their pending-approval notifications were fixtures, which
bench migrate re-imports with force=True, so any role change made on site was silently put
back. The self-approval block must hold whatever roles the workflow names."""

import json
import os

import frappe
from frappe.modules.import_file import import_file_by_path
from frappe.permissions import add_permission, update_permission_property

import blueline.hooks
from blueline.setup import after_migrate
from blueline.tests.utils import (
	FACTORIES,
	FINANCIAL_MANAGER,
	GI_MANAGEMENT,
	GI_SALES,
	GI_SALES_2,
	GI_TECH,
	SELF_APPROVAL_MESSAGE,
	SYSTEM_MANAGER,
	BluelineTestCase,
	act,
	as_user,
	reload,
	workflow,
)

PO_WORKFLOW = "GI Purchase Order Approval"
PO_NOTIFICATION = "GI Purchase Order Pending Approval"
NOT_VALID_ACTION = "Not a valid Workflow Action"
ONLY_SYSTEM_MANAGER = "Only a System Manager can change or delete a workflow."
SEEDED_DOCTYPES = {"Workflow", "Notification"}
# Fixture files bench migrate also imports, but which can't hold a workflow and whose import
# may run DDL (an implicit commit on MariaDB), so the migrate simulation leaves them out.
DDL_FIXTURE_DOCTYPES = {"Custom Field", "Workspace"}


def approve_roles(name=PO_WORKFLOW):
	return sorted(t.allowed for t in frappe.get_doc("Workflow", name).transitions if t.action == "Approve")


def set_approve_roles(roles, user=SYSTEM_MANAGER, name=PO_WORKFLOW):
	"""What a System Manager does in the Workflow screen: one Approve row per role."""
	with as_user(user):
		wf = frappe.get_doc("Workflow", name)
		template = next(t for t in wf.transitions if t.action == "Approve").as_dict()
		wf.transitions = [t for t in wf.transitions if t.action != "Approve"]
		for role in roles:
			row = {k: template[k] for k in ("state", "action", "next_state", "allow_self_approval", "condition")}
			wf.append("transitions", {**row, "allowed": role})
		wf.save()
	return approve_roles(name)


def simulate_migrate():
	"""What bench migrate does to this app's records: Frappe's own fixture import for every
	file in blueline/fixtures (same call and flags as frappe.utils.fixtures.sync_fixtures,
	minus its commit), then after_migrate."""
	fixtures = frappe.get_app_path("blueline", "fixtures")
	for fname in sorted(os.listdir(fixtures)):
		if not fname.endswith(".json"):
			continue
		path = os.path.join(fixtures, fname)
		with open(path) as f:
			if {d["doctype"] for d in json.load(f)} & DDL_FIXTURE_DOCTYPES:
				continue
		frappe.flags.in_fixtures = True
		try:
			import_file_by_path(path, data_import=True, force=True, reset_permissions=True)
		finally:
			frappe.flags.in_fixtures = False
	after_migrate()


class WorkflowTestCase(BluelineTestCase):
	def tearDown(self):
		super().tearDown()
		# get_workflow() reads a cached doc; the rollback doesn't reach the cache.
		for name in frappe.get_all("Workflow", pluck="name"):
			frappe.clear_document_cache("Workflow", name)
		frappe.clear_cache(doctype="Workflow")
		for doctype in FACTORIES:
			frappe.clear_cache(doctype=doctype)


class TestWorkflowsSurviveMigrate(WorkflowTestCase):
	def test_workflows_and_notifications_are_not_fixtures(self):
		self.assertFalse([f for f in blueline.hooks.fixtures if f["doctype"] in SEEDED_DOCTYPES])
		fixtures = frappe.get_app_path("blueline", "fixtures")
		for fname in os.listdir(fixtures):
			if not fname.endswith(".json"):
				continue
			with open(os.path.join(fixtures, fname)) as f:
				with self.subTest(file=fname):
					self.assertFalse({d["doctype"] for d in json.load(f)} & SEEDED_DOCTYPES)

	def test_migrate_keeps_a_system_managers_role_change(self):
		changed = set_approve_roles(["GI Management", "GI Sales Dept", "GI Sales Dept 2"])
		with as_user(SYSTEM_MANAGER):
			notification = frappe.get_doc("Notification", PO_NOTIFICATION)
			notification.append("recipients", {"receiver_by_role": "GI Sales Dept 2"})
			notification.save()

		simulate_migrate()

		frappe.clear_document_cache("Workflow", PO_WORKFLOW)
		self.assertEqual(approve_roles(), changed)
		self.assertIn(
			"GI Sales Dept 2", [r.receiver_by_role for r in frappe.get_doc("Notification", PO_NOTIFICATION).recipients]
		)

	def test_fresh_install_syncs_fixtures_before_seeding(self):
		"""install-app calls after_install before its own fixture sync; the seeded workflows
		need the fixture Roles / Workflow States / Actions to exist first."""
		from unittest import mock

		import blueline.setup

		calls = []
		with (
			mock.patch.object(blueline.setup, "sync_fixtures", lambda app: calls.append(("fixtures", app))),
			mock.patch.object(blueline.setup, "create_missing_seed_records", lambda: calls.append(("seed",))),
			mock.patch.object(frappe, "msgprint"),
		):
			blueline.setup.after_install()
		self.assertEqual(calls, [("fixtures", "blueline"), ("seed",)])

	def test_migrate_recreates_only_what_is_missing(self):
		frappe.delete_doc("Notification", "GI Petty Cash Pending Approval", ignore_permissions=True)
		set_approve_roles(["GI Management"], name="GI Quotation Approval")

		simulate_migrate()

		self.assertTrue(frappe.db.exists("Notification", "GI Petty Cash Pending Approval"))
		frappe.clear_document_cache("Workflow", "GI Quotation Approval")
		self.assertEqual(approve_roles("GI Quotation Approval"), ["GI Management"])


class TestOnlySystemManagerEditsWorkflows(WorkflowTestCase):
	def test_other_roles_are_refused_by_frappe(self):
		for user in (GI_MANAGEMENT, FINANCIAL_MANAGER, GI_SALES):
			with self.subTest(user=user):
				self.assertRaises(frappe.PermissionError, set_approve_roles, ["GI Management"], user)

	def test_widening_workflow_permissions_does_not_let_other_roles_in(self):
		add_permission("Workflow", "GI Management")
		update_permission_property("Workflow", "GI Management", 0, "write", 1)
		update_permission_property("Workflow", "GI Management", 0, "delete", 1)
		frappe.clear_cache(doctype="Workflow")

		self.assertRefused(lambda: set_approve_roles(["GI Management"], GI_MANAGEMENT), ONLY_SYSTEM_MANAGER)
		with as_user(GI_MANAGEMENT):
			self.assertRefused(lambda: frappe.get_doc("Workflow", PO_WORKFLOW).delete(), ONLY_SYSTEM_MANAGER)
		self.assertEqual(approve_roles(), ["GI Management", "GI Sales Dept", "GI Tech Dept"])

	def test_system_manager_can_change_roles_and_the_change_is_recorded(self):
		set_approve_roles(["GI Management", "GI Sales Dept"])
		version = frappe.get_last_doc("Version", filters={"ref_doctype": "Workflow", "docname": PO_WORKFLOW})
		self.assertEqual(version.owner, SYSTEM_MANAGER)
		data = json.loads(version.data)
		self.assertTrue(data.get("removed") or data.get("row_changed"), data)
		self.assertIn("GI Tech Dept", version.data)


class TestSelfApprovalWhenRolesChange(WorkflowTestCase):
	def test_adding_and_removing_an_approver_role(self):
		# Add GI Sales Dept 2 as an approver.
		set_approve_roles(["GI Management", "GI Sales Dept", "GI Tech Dept", "GI Sales Dept 2"])

		own = FACTORIES["Purchase Order"](GI_SALES_2)
		workflow(own, "Send for Approval", GI_SALES_2)
		self.assertRefused(lambda: workflow(own, "Approve", GI_SALES_2), SELF_APPROVAL_MESSAGE)

		sent_by_them = FACTORIES["Purchase Order"](GI_TECH)
		workflow(sent_by_them, "Send for Approval", GI_SALES_2)
		self.assertRefused(lambda: workflow(sent_by_them, "Approve", GI_SALES_2), SELF_APPROVAL_MESSAGE)

		someone_elses = FACTORIES["Purchase Order"](GI_TECH)
		workflow(someone_elses, "Send for Approval", GI_TECH)
		workflow(someone_elses, "Approve", GI_SALES_2)
		self.assertEqual(reload(someone_elses).docstatus, 1, "the added role can approve")

		# Remove GI Sales Dept 2 and GI Tech Dept again.
		set_approve_roles(["GI Management", "GI Sales Dept"])

		pending = FACTORIES["Purchase Order"](GI_SALES)
		workflow(pending, "Send for Approval", GI_SALES)
		self.assertRefused(lambda: workflow(pending, "Approve", GI_SALES_2), NOT_VALID_ACTION)
		self.assertRefused(lambda: workflow(pending, "Approve", GI_TECH), NOT_VALID_ACTION)
		# The creator still can't approve, with a role that kept Approve.
		self.assertRefused(lambda: workflow(pending, "Approve", GI_SALES), SELF_APPROVAL_MESSAGE)
		workflow(pending, "Approve", GI_MANAGEMENT)
		self.assertEqual(reload(pending).docstatus, 1)

	def test_system_manager_gets_no_exemption_after_a_role_change(self):
		set_approve_roles(["System Manager"])
		own = FACTORIES["Purchase Order"](SYSTEM_MANAGER)
		workflow(own, "Send for Approval", SYSTEM_MANAGER)
		self.assertRefused(lambda: workflow(own, "Approve", SYSTEM_MANAGER), SELF_APPROVAL_MESSAGE)
		self.assertRefused(lambda: act(SYSTEM_MANAGER, reload(own).submit), SELF_APPROVAL_MESSAGE)
