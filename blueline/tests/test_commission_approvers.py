"""Item 2 — the two commission approvals must come from two different users, and are locked
once the entry is Approved or Paid. The existing "both boxes required" and wrong-role rules
must keep working alongside."""

import frappe

from blueline.server_scripts.sales_commission import mark_commission_entry_paid
from blueline.tests.utils import (
	FINANCIAL_MANAGER,
	GI_MANAGEMENT,
	SYSTEM_MANAGER,
	BluelineTestCase,
	approved_payout,
	as_user,
	pending_commission_entry,
	update_entry,
	workflow,
)

SCE = "Sales Commission Entry"
SAME_USER = "must be given by two different users"
LOCKED = "cannot be changed once the entry is"
# office@ holds Technical Approver (permlevel 2) but not permlevel 1;
# the Financial Manager holds permlevel 1 but only read on permlevel 2.
TECHNICAL_APPROVER = GI_MANAGEMENT


def entry(name):
	return frappe.get_doc(SCE, name)


class TestCommissionApprovers(BluelineTestCase):
	def test_one_user_ticking_both_in_one_save_is_refused(self):
		name, *_ = pending_commission_entry()
		self.assertRefused(
			lambda: update_entry(name, SYSTEM_MANAGER, approved_by_management=1, approved_by_technical=1), SAME_USER
		)
		e = entry(name)
		self.assertEqual((e.approved_by_management, e.approved_by_technical), (0, 0))
		self.assertEqual(e.status, "Payment Received - Pending Approval")

	def test_one_user_ticking_the_second_box_later_is_refused(self):
		name, *_ = pending_commission_entry()
		update_entry(name, SYSTEM_MANAGER, approved_by_management=1)
		self.assertEqual(entry(name).management_approved_by, SYSTEM_MANAGER)
		self.assertRefused(lambda: update_entry(name, SYSTEM_MANAGER, approved_by_technical=1), SAME_USER)
		self.assertEqual(entry(name).approved_by_technical, 0)

	def test_system_manager_cannot_approve_alone(self):
		"""System Manager can write both permlevels, so only this rule stops them."""
		name, *_ = pending_commission_entry()
		update_entry(name, SYSTEM_MANAGER, approved_by_technical=1)
		self.assertRefused(lambda: update_entry(name, SYSTEM_MANAGER, approved_by_management=1), SAME_USER)
		self.assertRefused(lambda: workflow(entry(name), "Approve", SYSTEM_MANAGER), "Both approvals are required")
		self.assertNotEqual(entry(name).status, "Approved")

	def test_administrator_cannot_approve_alone(self):
		name, *_ = pending_commission_entry()
		self.assertRefused(
			lambda: update_entry(name, "Administrator", approved_by_management=1, approved_by_technical=1), SAME_USER
		)

	def test_two_different_users_succeed(self):
		name, *_ = pending_commission_entry()
		update_entry(name, FINANCIAL_MANAGER, approved_by_management=1)
		update_entry(name, TECHNICAL_APPROVER, approved_by_technical=1)
		e = entry(name)
		self.assertEqual(e.status, "Approved")
		self.assertEqual((e.management_approved_by, e.technical_approved_by), (FINANCIAL_MANAGER, TECHNICAL_APPROVER))

	def test_two_different_users_succeed_in_either_order(self):
		name, *_ = pending_commission_entry()
		update_entry(name, TECHNICAL_APPROVER, approved_by_technical=1)
		update_entry(name, SYSTEM_MANAGER, approved_by_management=1)
		e = entry(name)
		self.assertEqual(e.status, "Approved")
		self.assertEqual((e.management_approved_by, e.technical_approved_by), (SYSTEM_MANAGER, TECHNICAL_APPROVER))

	def test_approver_fields_cannot_be_set_by_the_client(self):
		name, *_ = pending_commission_entry()
		update_entry(name, FINANCIAL_MANAGER, approved_by_management=1, technical_approved_by=SYSTEM_MANAGER)
		e = entry(name)
		self.assertEqual(e.management_approved_by, FINANCIAL_MANAGER)
		self.assertIsNone(e.technical_approved_by)

		# Rewriting who gave the first tick, to make the second tick look like someone else's.
		update_entry(name, FINANCIAL_MANAGER, management_approved_by=TECHNICAL_APPROVER)
		self.assertEqual(entry(name).management_approved_by, FINANCIAL_MANAGER)

	def test_unticking_while_pending_clears_the_approver(self):
		name, *_ = pending_commission_entry()
		update_entry(name, SYSTEM_MANAGER, approved_by_management=1)
		update_entry(name, SYSTEM_MANAGER, approved_by_management=0)
		self.assertIsNone(entry(name).management_approved_by)
		# The System Manager may now give the *other* approval instead.
		update_entry(name, SYSTEM_MANAGER, approved_by_technical=1)
		update_entry(name, FINANCIAL_MANAGER, approved_by_management=1)
		self.assertEqual(entry(name).status, "Approved")

	def test_ticks_are_locked_once_approved(self):
		name, *_ = pending_commission_entry()
		update_entry(name, FINANCIAL_MANAGER, approved_by_management=1)
		update_entry(name, TECHNICAL_APPROVER, approved_by_technical=1)
		self.assertEqual(entry(name).status, "Approved")

		self.assertRefused(lambda: update_entry(name, FINANCIAL_MANAGER, approved_by_management=0), LOCKED)
		self.assertRefused(lambda: update_entry(name, TECHNICAL_APPROVER, approved_by_technical=0), LOCKED)
		self.assertRefused(lambda: update_entry(name, SYSTEM_MANAGER, approved_by_management=0), LOCKED)
		self.assertRefused(lambda: update_entry(name, "Administrator", approved_by_technical=0), LOCKED)

		with as_user("Administrator"):
			e = entry(name)
			e.approved_by_management = 0
			e.flags.ignore_permissions = True
			self.assertRefused(e.save, LOCKED)

	def test_ticks_are_locked_once_paid(self):
		name, invoice, payment = pending_commission_entry()
		update_entry(name, FINANCIAL_MANAGER, approved_by_management=1)
		update_entry(name, TECHNICAL_APPROVER, approved_by_technical=1)
		payout = approved_payout(entry(name).commission_amount)
		with as_user(FINANCIAL_MANAGER):
			mark_commission_entry_paid(name, payout.name)
		self.assertEqual(entry(name).status, "Paid")

		self.assertRefused(lambda: update_entry(name, SYSTEM_MANAGER, approved_by_technical=0), LOCKED)
		self.assertRefused(lambda: update_entry(name, FINANCIAL_MANAGER, approved_by_management=0), LOCKED)
		e = entry(name)
		self.assertEqual((e.management_approved_by, e.technical_approved_by), (FINANCIAL_MANAGER, TECHNICAL_APPROVER))

	# --- existing rules that must keep working -------------------------------------------

	def test_both_boxes_still_required(self):
		name, *_ = pending_commission_entry()
		update_entry(name, FINANCIAL_MANAGER, approved_by_management=1)
		self.assertRefused(lambda: workflow(entry(name), "Approve", FINANCIAL_MANAGER), "Both approvals are required")
		self.assertEqual(entry(name).status, "Payment Received - Pending Approval")

	def test_wrong_role_ticks_still_refused(self):
		name, *_ = pending_commission_entry()
		self.assertRefused(
			lambda: update_entry(name, TECHNICAL_APPROVER, approved_by_management=1),
			"You don't have permission to change",
		)
		self.assertRefused(
			lambda: update_entry(name, FINANCIAL_MANAGER, approved_by_technical=1),
			"You don't have permission to change",
		)

	def test_legacy_ticks_without_recorded_approvers_cannot_approve(self):
		"""Entries ticked before this change whose tickers couldn't be recovered by the patch."""
		name, *_ = pending_commission_entry()
		frappe.db.set_value(SCE, name, {"approved_by_management": 1, "approved_by_technical": 1})
		self.assertRefused(
			lambda: workflow(entry(name), "Approve", FINANCIAL_MANAGER), "before the approving users were recorded"
		)

	def test_backfill_patch_recovers_approvers_from_versions(self):
		from blueline.patches.backfill_commission_approvers import execute

		name, *_ = pending_commission_entry()
		update_entry(name, FINANCIAL_MANAGER, approved_by_management=1)
		update_entry(name, TECHNICAL_APPROVER, approved_by_technical=1)
		frappe.db.set_value(SCE, name, {"management_approved_by": None, "technical_approved_by": None})
		execute()
		e = entry(name)
		self.assertEqual((e.management_approved_by, e.technical_approved_by), (FINANCIAL_MANAGER, TECHNICAL_APPROVER))
