"""Item 1 — nobody may approve a document they created or sent for approval."""

import frappe
import frappe.client

from blueline.server_scripts.self_approval import SENT_BY_FIELD
from blueline.tests.utils import (
	FACTORIES,
	GI_MANAGEMENT,
	GI_SALES,
	GI_SALES_2,
	GI_TECH,
	SELF_APPROVAL_MESSAGE,
	SYSTEM_MANAGER,
	BluelineTestCase,
	act,
	as_user,
	make_petty_cash_voucher,
	reload,
	workflow,
)

# Send for Approval is open to GI Management/Sales/Tech/Sales Dept 2 on these four; on
# Petty Cash Voucher only GI Sales Dept 2 may send.
WORKFLOW_DOCTYPES = ("Quotation", "Purchase Order", "Sales Invoice", "Payment Entry")
ALL_DOCTYPES = (*WORKFLOW_DOCTYPES, "Petty Cash Voucher")


def sender_for(doctype, preferred):
	return GI_SALES_2 if doctype == "Petty Cash Voucher" else preferred


class TestSelfApproval(BluelineTestCase):
	def test_creator_cannot_approve(self):
		for doctype in ALL_DOCTYPES:
			with self.subTest(doctype=doctype):
				doc = FACTORIES[doctype](GI_MANAGEMENT)
				workflow(doc, "Send for Approval", sender_for(doctype, GI_MANAGEMENT))
				self.assertRefused(lambda: workflow(doc, "Approve", GI_MANAGEMENT), SELF_APPROVAL_MESSAGE)
				self.assertEqual(reload(doc).docstatus, 0)
				self.assertEqual(reload(doc).workflow_state, "Pending Approval")
				self.tearDown()

	def test_different_user_with_allowed_role_can_approve(self):
		for doctype in ALL_DOCTYPES:
			with self.subTest(doctype=doctype):
				doc = FACTORIES[doctype](GI_TECH)
				workflow(doc, "Send for Approval", sender_for(doctype, GI_TECH))
				workflow(doc, "Approve", GI_MANAGEMENT)
				doc = reload(doc)
				self.assertEqual((doc.docstatus, doc.workflow_state), (1, "Approved"))
				self.tearDown()

	def test_system_manager_creator_is_blocked(self):
		for doctype in ALL_DOCTYPES:
			with self.subTest(doctype=doctype):
				doc = FACTORIES[doctype](SYSTEM_MANAGER)
				workflow(doc, "Send for Approval", sender_for(doctype, SYSTEM_MANAGER))
				self.assertRefused(lambda: workflow(doc, "Approve", SYSTEM_MANAGER), SELF_APPROVAL_MESSAGE)
				self.assertEqual(reload(doc).docstatus, 0)
				self.tearDown()

	def test_administrator_creator_is_blocked(self):
		for doctype in ALL_DOCTYPES:
			with self.subTest(doctype=doctype):
				doc = FACTORIES[doctype]("Administrator")
				self.assertRefused(lambda: act("Administrator", reload(doc).submit), SELF_APPROVAL_MESSAGE)
				self.tearDown()

	def test_user_who_sent_for_approval_cannot_approve(self):
		for doctype in WORKFLOW_DOCTYPES:
			with self.subTest(doctype=doctype):
				doc = FACTORIES[doctype](GI_SALES_2)
				workflow(doc, "Send for Approval", GI_MANAGEMENT)
				self.assertEqual(reload(doc).get(SENT_BY_FIELD), GI_MANAGEMENT)
				self.assertRefused(lambda: workflow(doc, "Approve", GI_MANAGEMENT), SELF_APPROVAL_MESSAGE)
				# ...while a third user may approve it.
				workflow(doc, "Approve", SYSTEM_MANAGER)
				self.assertEqual(reload(doc).docstatus, 1)
				self.tearDown()

	def test_direct_api_submit_by_creator_is_blocked(self):
		"""A raw submit (form Submit / frappe.client.submit / doc.submit()) skips the workflow
		action entirely; the block must still hold, from Draft and from Pending Approval."""
		for doctype in ALL_DOCTYPES:
			with self.subTest(doctype=doctype, path="frappe.client.submit from Draft"):
				doc = FACTORIES[doctype](GI_MANAGEMENT)
				self.assertRefused(
					lambda: act(GI_MANAGEMENT, frappe.client.submit, reload(doc).as_dict()), SELF_APPROVAL_MESSAGE
				)
				self.tearDown()
			with self.subTest(doctype=doctype, path="doc.submit() from Pending Approval"):
				doc = FACTORIES[doctype](SYSTEM_MANAGER)
				workflow(doc, "Send for Approval", sender_for(doctype, SYSTEM_MANAGER))
				self.assertRefused(lambda: act(SYSTEM_MANAGER, reload(doc).submit), SELF_APPROVAL_MESSAGE)
				self.tearDown()

	def test_insert_already_submitted_is_blocked(self):
		"""Inserting with docstatus=1 in one call makes the caller both owner and approver."""
		doc = FACTORIES["Sales Invoice"](GI_MANAGEMENT)
		payload = reload(doc).as_dict()
		for key in ("name", "owner", "creation", "modified", "workflow_state", "custom_tax_invoice_serial"):
			payload.pop(key, None)
		for row in payload["items"]:
			row.pop("name", None)
			row.pop("parent", None)
		payload["docstatus"] = 1
		self.assertRefused(lambda: act(GI_MANAGEMENT, frappe.client.insert, payload), SELF_APPROVAL_MESSAGE)

	def test_sent_by_cannot_be_set_or_altered_by_the_client(self):
		doc = FACTORIES["Sales Invoice"](GI_TECH)
		with as_user(GI_TECH):
			draft = reload(doc)
			draft.set(SENT_BY_FIELD, SYSTEM_MANAGER)
			draft.save()
		self.assertIsNone(reload(doc).get(SENT_BY_FIELD))

		workflow(doc, "Send for Approval", GI_TECH)
		with as_user(GI_MANAGEMENT):
			pending = reload(doc)
			pending.set(SENT_BY_FIELD, GI_SALES)
			pending.save()
		self.assertEqual(reload(doc).get(SENT_BY_FIELD), GI_TECH)
		# the forged value can't be used to slip GI_TECH past the sender check either
		self.assertRefused(lambda: workflow(doc, "Approve", GI_TECH), SELF_APPROVAL_MESSAGE)

	def test_owner_cannot_be_rewritten_to_dodge_the_check(self):
		doc = FACTORIES["Sales Invoice"](GI_MANAGEMENT)
		workflow(doc, "Send for Approval", GI_TECH)
		with as_user(GI_MANAGEMENT):
			pending = reload(doc)
			pending.owner = GI_SALES
			self.assertRefused(pending.submit, SELF_APPROVAL_MESSAGE)

	def test_petty_cash_submit_shortcut_respects_the_block(self):
		"""Petty Cash Voucher keeps a Draft -> Approved "Submit" action (known issue K5).
		The creator can no longer use it on their own voucher; another approver still can."""
		own = make_petty_cash_voucher(GI_MANAGEMENT)
		self.assertRefused(lambda: workflow(own, "Submit", GI_MANAGEMENT), SELF_APPROVAL_MESSAGE)

		someone_elses = make_petty_cash_voucher(GI_TECH)
		workflow(someone_elses, "Submit", GI_MANAGEMENT)
		self.assertEqual(reload(someone_elses).docstatus, 1)
		self.assertTrue(reload(someone_elses).journal_entry)

	def test_credit_note_follows_the_same_rule(self):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		original = FACTORIES["Sales Invoice"](GI_TECH)
		workflow(original, "Send for Approval", GI_TECH)
		workflow(original, "Approve", GI_MANAGEMENT)

		with as_user(GI_SALES):
			credit_note = make_sales_return(original.name)
			credit_note.insert()
		workflow(credit_note, "Send for Approval", GI_SALES)
		self.assertRefused(lambda: workflow(credit_note, "Approve", GI_SALES), SELF_APPROVAL_MESSAGE)
		workflow(credit_note, "Approve", GI_MANAGEMENT)
		self.assertEqual(reload(credit_note).docstatus, 1)
