"""The live GI workflows / notifications can be exported to a committed snapshot, drift from
it is reported, and new environments are seeded from it."""

import shutil
import tempfile
from unittest import mock

import frappe

from blueline import workflow_sync
from blueline.setup import create_missing_seed_records
from blueline.tests.test_approver_roles import (
	PO_NOTIFICATION,
	PO_WORKFLOW,
	WorkflowTestCase,
	set_approve_roles,
)
from blueline.tests.utils import SYSTEM_MANAGER, as_user

PETTY_CASH_NOTIFICATION = "GI Petty Cash Pending Approval"


class SnapshotTestCase(WorkflowTestCase):
	"""Snapshot files go to a temporary folder, never into the app."""

	def setUp(self):
		super().setUp()
		self.tmp = tempfile.mkdtemp()
		real_seed_path = workflow_sync.seed_path

		def seed_path(fname, snapshot=False):
			return f"{self.tmp}/{fname}" if snapshot else real_seed_path(fname)

		patcher = mock.patch.object(workflow_sync, "seed_path", seed_path)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(shutil.rmtree, self.tmp, True)
		with mock.patch("builtins.print"):
			workflow_sync.export_snapshot()

	def drift(self):
		with mock.patch("builtins.print"):
			return workflow_sync.check_drift()


class TestDrift(SnapshotTestCase):
	def test_no_drift_right_after_export(self):
		self.assertEqual(self.drift(), {})

	def test_an_approver_role_change_is_reported(self):
		set_approve_roles(["GI Management", "GI Sales Dept 2"])
		frappe.clear_document_cache("Workflow", PO_WORKFLOW)
		changes = self.drift()[f"Workflow {PO_WORKFLOW}"]
		self.assertTrue(any("added row" in c and "allowed=GI Sales Dept 2" in c for c in changes), changes)

	def test_a_notification_recipient_change_is_reported(self):
		with as_user(SYSTEM_MANAGER):
			notification = frappe.get_doc("Notification", PO_NOTIFICATION)
			notification.append("recipients", {"receiver_by_role": "GI Sales Dept 2"})
			notification.save()
		changes = self.drift()[f"Notification {PO_NOTIFICATION}"]
		self.assertTrue(any("receiver_by_role=GI Sales Dept 2" in c for c in changes), changes)

	def test_a_deleted_record_is_reported_missing(self):
		frappe.delete_doc("Notification", PETTY_CASH_NOTIFICATION, ignore_permissions=True)
		self.assertEqual(self.drift()[f"Notification {PETTY_CASH_NOTIFICATION}"], ["missing on this site"])

	def test_exporting_again_clears_the_drift(self):
		set_approve_roles(["GI Management", "GI Sales Dept 2"])
		frappe.clear_document_cache("Workflow", PO_WORKFLOW)
		with mock.patch("builtins.print"):
			workflow_sync.export_snapshot()
		self.assertEqual(self.drift(), {})


class TestSeedingFromSnapshot(SnapshotTestCase):
	def test_a_missing_record_is_recreated_as_in_the_snapshot(self):
		with as_user(SYSTEM_MANAGER):
			notification = frappe.get_doc("Notification", PETTY_CASH_NOTIFICATION)
			notification.append("recipients", {"receiver_by_role": "GI Sales Dept 2"})
			notification.save()
		with mock.patch("builtins.print"):
			workflow_sync.export_snapshot()
		frappe.delete_doc("Notification", PETTY_CASH_NOTIFICATION, ignore_permissions=True)

		create_missing_seed_records()

		roles = [r.receiver_by_role for r in frappe.get_doc("Notification", PETTY_CASH_NOTIFICATION).recipients]
		self.assertIn("GI Sales Dept 2", roles)

	def test_without_a_snapshot_the_original_seed_is_used(self):
		shutil.rmtree(self.tmp)
		self.assertEqual(
			[r["name"] for r in workflow_sync.seed_records("workflow.json")],
			[r["name"] for r in workflow_sync.load("workflow.json")],
		)


class TestDriftAgainstTheOriginalSeed(WorkflowTestCase):
	"""No snapshot committed: records created from the seed files must compare equal to them.
	(Live child rows carry fields the seed files leave out; that is not drift.)"""

	def test_records_freshly_seeded_show_no_drift(self):
		with mock.patch.object(workflow_sync, "load", side_effect=lambda f, snapshot=False: None if snapshot else REAL_LOAD(f)):
			for doctype, name in (("Workflow", "GI Petty Cash Approval"), ("Notification", PETTY_CASH_NOTIFICATION)):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
			create_missing_seed_records()
			frappe.clear_document_cache("Workflow", "GI Petty Cash Approval")
			with mock.patch("builtins.print"):
				drift = workflow_sync.check_drift()
		for record in ("Workflow GI Petty Cash Approval", f"Notification {PETTY_CASH_NOTIFICATION}"):
			with self.subTest(record=record):
				self.assertNotIn(record, drift)


REAL_LOAD = workflow_sync.load


class TestDriftAcrossVersions(SnapshotTestCase):
	"""A snapshot or seed written on another Frappe/ERPNext version can carry fields this
	site's doctypes don't have (15.110's Workflow Document State.send_email on 15.5): only
	fields the live doctype has are compared, so those are never drift. Real changes still are."""

	UNKNOWN = "field_this_version_does_not_have"

	def edit_snapshot(self, fname, change):
		import json

		path = f"{self.tmp}/{fname}"
		with open(path) as f:
			records = json.load(f)
		for record in records:
			change(record)
		with open(path, "w") as f:
			json.dump(records, f)

	def add_unknown_fields(self):
		def workflow(record):
			record[self.UNKNOWN] = 1
			for table in ("states", "transitions"):
				for row in record[table]:
					row[self.UNKNOWN] = 1

		def notification(record):
			record[self.UNKNOWN] = "Markdown"
			for row in record["recipients"]:
				row[self.UNKNOWN] = 0

		self.edit_snapshot("workflow.json", workflow)
		self.edit_snapshot("notification.json", notification)

	def test_fields_the_live_doctype_lacks_are_not_drift(self):
		self.assertFalse(frappe.get_meta("Workflow Document State").has_field(self.UNKNOWN))
		self.add_unknown_fields()
		self.assertEqual(self.drift(), {})

	def test_a_real_change_to_an_existing_field_is_still_drift(self):
		self.add_unknown_fields()

		def retitle(record):
			if record["name"] == PO_NOTIFICATION:
				record["subject"] = "A different subject"

		self.edit_snapshot("notification.json", retitle)
		changes = self.drift()[f"Notification {PO_NOTIFICATION}"]
		self.assertEqual(len(changes), 1, changes)
		self.assertTrue(changes[0].startswith("subject: 'A different subject' -> "), changes)

	def test_a_removed_row_is_still_drift(self):
		self.add_unknown_fields()
		set_approve_roles(["GI Management"])  # drops the other Approve rows on site
		frappe.clear_document_cache("Workflow", PO_WORKFLOW)
		changes = self.drift()[f"Workflow {PO_WORKFLOW}"]
		self.assertTrue(changes, "removing approver rows must be reported")
		self.assertTrue(all("removed row" in c and "action=Approve" in c for c in changes), changes)
