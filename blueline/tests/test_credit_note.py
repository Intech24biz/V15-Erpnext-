"""Item 3 — approved tax invoices are reversed by Credit Note, never cancelled."""

import frappe
import frappe.client
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
from frappe.utils import flt

from blueline.tests.utils import (
	GI_MANAGEMENT,
	GI_SALES,
	GI_SALES_2,
	GI_TECH,
	SELF_APPROVAL_MESSAGE,
	SYSTEM_MANAGER,
	BluelineTestCase,
	act,
	approved_invoice,
	as_user,
	commission_entries,
	make_sales_invoice,
	reload,
	workflow,
)

USE_CREDIT_NOTE = "Issue a Credit Note instead"


def series_counter(prefix):
	row = frappe.db.sql("select current from tabSeries where name = %s", prefix)
	return row[0][0] if row else 0


def make_credit_note(original, user=GI_SALES, **overrides):
	with as_user(user):
		credit_note = make_sales_return(original.name)
		credit_note.update(overrides)
		credit_note.insert()
		return credit_note


def approved_credit_note(original, creator=GI_SALES, approver=GI_MANAGEMENT, **overrides):
	credit_note = make_credit_note(original, creator, **overrides)
	workflow(credit_note, "Send for Approval", creator)
	workflow(credit_note, "Approve", approver)
	return reload(credit_note)


def receivable_balance(*vouchers):
	"""Net receivable (debit - credit) posted by these vouchers for the test customer."""
	rows = frappe.get_all(
		"GL Entry",
		filters={"voucher_no": ["in", vouchers], "is_cancelled": 0, "party_type": "Customer"},
		fields=["debit", "credit"],
	)
	return flt(sum(r.debit - r.credit for r in rows), 2)


class TestCancelReplacedByCreditNote(BluelineTestCase):
	def test_cancel_refused_on_approved_invoice_for_every_role(self):
		invoice = approved_invoice()
		self.assertTrue(invoice.custom_tax_invoice_serial)
		for user in (SYSTEM_MANAGER, "Administrator", GI_SALES):
			with self.subTest(user=user):
				self.assertRefused(lambda: act(user, reload(invoice).cancel), USE_CREDIT_NOTE)
				self.assertRefused(
					lambda: act(user, frappe.client.cancel, "Sales Invoice", invoice.name), USE_CREDIT_NOTE
				)
		invoice = reload(invoice)
		self.assertEqual((invoice.docstatus, invoice.workflow_state), (1, "Approved"))

	def test_cancel_message_names_the_serial_and_the_action(self):
		invoice = approved_invoice()
		with self.assertRaises(frappe.ValidationError) as ctx:
			act(SYSTEM_MANAGER, reload(invoice).cancel)
		self.assertIn(invoice.custom_tax_invoice_serial, str(ctx.exception))
		self.assertIn("Create > Return / Credit Note", str(ctx.exception))

	def test_draft_and_pending_invoices_can_still_be_deleted(self):
		draft = make_sales_invoice(GI_SALES)
		act(GI_SALES, frappe.delete_doc, "Sales Invoice", draft.name)
		self.assertFalse(frappe.db.exists("Sales Invoice", draft.name))

		pending = make_sales_invoice(GI_TECH)
		workflow(pending, "Send for Approval", GI_TECH)
		act(SYSTEM_MANAGER, frappe.delete_doc, "Sales Invoice", pending.name)
		self.assertFalse(frappe.db.exists("Sales Invoice", pending.name))


class TestCreditNote(BluelineTestCase):
	def test_return_action_is_available_to_invoice_roles(self):
		"""ERPNext's Create > Return / Credit Note calls make_sales_return; every GI role that
		can raise a Sales Invoice (via Accounts User) can raise a Credit Note."""
		invoice = approved_invoice()
		for user in (GI_SALES, GI_TECH, GI_SALES_2, GI_MANAGEMENT, SYSTEM_MANAGER):
			with self.subTest(user=user):
				credit_note = make_credit_note(invoice, user)
				self.assertEqual((credit_note.is_return, credit_note.return_against), (1, invoice.name))
				self.assertEqual(credit_note.workflow_state, "Draft")
				frappe.delete_doc("Sales Invoice", credit_note.name, ignore_permissions=True)

	def test_credit_note_uses_its_own_series_and_never_touches_the_tax_sequence(self):
		invoice = approved_invoice()
		serial = invoice.custom_tax_invoice_serial
		tax_counter = series_counter("BTAX-")
		credit_counter = series_counter("BTAX-RET-")

		credit_note = approved_credit_note(invoice)

		self.assertTrue(credit_note.name.startswith("BTAX-RET-"), credit_note.name)
		self.assertEqual(credit_note.naming_series, "BTAX-RET-")
		self.assertEqual(series_counter("BTAX-RET-"), credit_counter + 1)
		self.assertEqual(series_counter("BTAX-"), tax_counter, "a Credit Note consumed a tax-invoice number")
		self.assertFalse(credit_note.custom_tax_invoice_serial, "a Credit Note must not carry a tax-invoice serial")
		self.assertEqual(reload(invoice).custom_tax_invoice_serial, serial)

		# The next real tax invoice takes the very next number: no gap, no reuse.
		next_invoice = approved_invoice()
		self.assertEqual(series_counter("BTAX-"), tax_counter + 1)
		self.assertNotEqual(next_invoice.custom_tax_invoice_serial, serial)
		self.assertTrue(next_invoice.custom_tax_invoice_serial.endswith(next_invoice.name.replace("TAX-", "")))

	def test_series_cannot_be_overridden_by_the_caller(self):
		invoice = approved_invoice()
		credit_note = make_credit_note(invoice, naming_series="BTAX-")
		self.assertTrue(credit_note.name.startswith("BTAX-RET-"), credit_note.name)

	def test_credit_note_series_is_reserved_for_credit_notes(self):
		si = reload(make_sales_invoice(GI_SALES))
		si.naming_series = "BTAX-RET-"
		self.assertRefused(lambda: act(GI_SALES, si.save), "reserved for Credit Notes")

	def test_credit_note_reverses_ledger_and_receivable(self):
		invoice = approved_invoice()
		credit_note = approved_credit_note(invoice)

		self.assertEqual(flt(credit_note.grand_total), -flt(invoice.grand_total))
		gl = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": credit_note.name, "is_cancelled": 0},
			fields=["account", "debit", "credit"],
		)
		income = frappe.db.get_value("Company", invoice.company, "default_income_account")
		receivable = invoice.debit_to
		self.assertEqual(sum(r.debit for r in gl if r.account == income), flt(invoice.net_total))
		self.assertEqual(sum(r.credit for r in gl if r.account == receivable), flt(invoice.grand_total))
		# Customer's receivable from the pair nets to zero.
		self.assertEqual(receivable_balance(invoice.name, credit_note.name), 0)

	def test_credit_note_applied_against_the_original_clears_its_outstanding(self):
		if not frappe.get_meta("Sales Invoice").get_field("update_outstanding_for_self"):
			# Production's ERPNext (15.6) has no such option: a Credit Note always stands on its
			# own and is applied with Payment Reconciliation (test_commission_release).
			self.skipTest("this ERPNext has no 'Update Outstanding for Self'")
		invoice = approved_invoice()
		approved_credit_note(invoice, update_outstanding_for_self=0)
		invoice = reload(invoice)
		self.assertEqual(flt(invoice.outstanding_amount), 0)
		self.assertEqual(invoice.status, "Credit Note Issued")

	def test_original_keeps_its_number_serial_and_approval(self):
		invoice = approved_invoice()
		before = (invoice.name, invoice.custom_tax_invoice_serial, invoice.docstatus, invoice.workflow_state)
		approved_credit_note(invoice)
		after = reload(invoice)
		self.assertEqual((after.name, after.custom_tax_invoice_serial, after.docstatus, after.workflow_state), before)

	def test_credit_note_goes_through_the_approval_workflow(self):
		invoice = approved_invoice()
		credit_note = make_credit_note(invoice, GI_SALES_2)
		self.assertEqual((credit_note.docstatus, credit_note.workflow_state), (0, "Draft"))

		# The creator can't submit it directly, and GI Sales Dept 2 can't bypass the workflow.
		self.assertRefused(lambda: act(GI_SALES_2, reload(credit_note).submit), SELF_APPROVAL_MESSAGE)

		workflow(credit_note, "Send for Approval", GI_SALES_2)
		self.assertEqual(reload(credit_note).workflow_state, "Pending Approval")
		workflow(credit_note, "Approve", GI_MANAGEMENT)
		credit_note = reload(credit_note)
		self.assertEqual((credit_note.docstatus, credit_note.workflow_state), (1, "Approved"))

	def test_credit_note_creator_or_sender_cannot_approve_it(self):
		invoice = approved_invoice()
		credit_note = make_credit_note(invoice, GI_MANAGEMENT)
		workflow(credit_note, "Send for Approval", GI_TECH)
		self.assertRefused(lambda: workflow(credit_note, "Approve", GI_MANAGEMENT), SELF_APPROVAL_MESSAGE)
		self.assertRefused(lambda: workflow(credit_note, "Approve", GI_TECH), SELF_APPROVAL_MESSAGE)
		workflow(credit_note, "Approve", SYSTEM_MANAGER)
		self.assertEqual(reload(credit_note).docstatus, 1)


class TestTaxInvoiceSerialIsServerSide(BluelineTestCase):
	def test_duplicate_does_not_copy_the_serial(self):
		invoice = approved_invoice()
		with as_user(GI_TECH):
			# The form's Duplicate honours no_copy...
			self.assertFalse(frappe.copy_doc(reload(invoice), ignore_no_copy=False).custom_tax_invoice_serial)
			# ...and a server-side copy that does carry it has it dropped on save.
			duplicate = frappe.copy_doc(reload(invoice))
			self.assertEqual(duplicate.custom_tax_invoice_serial, invoice.custom_tax_invoice_serial)
			duplicate.workflow_state = None  # also copied by the server-side copy; not under test
			duplicate.insert()
			self.assertFalse(reload(duplicate).custom_tax_invoice_serial)
		workflow(duplicate, "Send for Approval", GI_TECH)
		workflow(duplicate, "Approve", GI_MANAGEMENT)
		duplicate = reload(duplicate)
		self.assertTrue(duplicate.custom_tax_invoice_serial)
		self.assertNotEqual(duplicate.custom_tax_invoice_serial, invoice.custom_tax_invoice_serial)

	def test_client_cannot_inject_a_serial(self):
		draft = make_sales_invoice(GI_TECH)
		with as_user(GI_TECH):
			draft = reload(draft)
			draft.custom_tax_invoice_serial = "26OCT_BLIN_FORGED"
			draft.save()
		self.assertFalse(reload(draft).custom_tax_invoice_serial)

		workflow(draft, "Send for Approval", GI_TECH)
		with as_user(GI_MANAGEMENT):
			pending = reload(draft)
			pending.custom_tax_invoice_serial = "26OCT_BLIN_FORGED"
			pending.submit()
		self.assertNotEqual(reload(draft).custom_tax_invoice_serial, "26OCT_BLIN_FORGED")
		self.assertIn(draft.name.replace("BTAX-", "B"), reload(draft).custom_tax_invoice_serial)


class TestCreditNoteCommission(BluelineTestCase):
	"""The rule the client agreed replaced the old behaviour (negative Accrued entries on the
	Credit Note). Full cover is in test_credit_note_commission."""

	def test_credit_note_adjusts_the_original_entries_instead_of_accruing_negatives(self):
		invoice = approved_invoice()
		original = commission_entries(invoice.name)
		self.assertEqual(len(original), 3)

		credit_note = approved_credit_note(invoice)

		self.assertEqual(commission_entries(credit_note.name), [])
		after = commission_entries(invoice.name)
		self.assertEqual([e.name for e in after], [e.name for e in original])
		self.assertTrue(all((e.status, e.commission_amount) == ("Cancelled", 0) for e in after))
