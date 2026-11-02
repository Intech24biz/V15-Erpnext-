"""Document storage by fiscal year: folders per Fiscal Year / Company / category, and new
attachments filed into them by their document's company and date."""

import frappe
from frappe.utils import nowdate

from erpnext.accounts.utils import get_fiscal_year

from blueline.document_folders import CATEGORIES, ensure_all_folders, refile_existing_attachments
from blueline.tests.utils import (
	COMPANY,
	CUSTOMER,
	GI_TECH,
	BluelineTestCase,
	as_user,
	make_petty_cash_voucher,
	make_sales_invoice,
)


def current_fy():
	return get_fiscal_year(nowdate(), company=COMPANY, verbose=0)[0]


def company_folder():
	return f"Home/Fiscal Year {current_fy()}/{COMPANY}"


def attach(doctype, name, user=GI_TECH, folder=None):
	with as_user(user):
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "blueline-test.txt",
				"content": b"blueline test attachment",
				"attached_to_doctype": doctype,
				"attached_to_name": name,
				"is_private": 1,
				**({"folder": folder} if folder else {}),
			}
		)
		f.insert()
		return f


class TestFolders(BluelineTestCase):
	def test_every_category_folder_exists_for_the_current_fiscal_year(self):
		ensure_all_folders()
		for category in CATEGORIES:
			with self.subTest(category=category):
				self.assertTrue(frappe.db.get_value("File", f"{company_folder()}/{category}", "is_folder"))

	def test_running_it_again_creates_nothing_new(self):
		ensure_all_folders()
		count = frappe.db.count("File", {"is_folder": 1})
		ensure_all_folders()
		self.assertEqual(frappe.db.count("File", {"is_folder": 1}), count)


class TestAttachmentFiling(BluelineTestCase):
	def test_an_invoice_attachment_goes_to_its_fiscal_year_sales_folder(self):
		invoice = make_sales_invoice(GI_TECH)
		self.assertEqual(attach("Sales Invoice", invoice.name).folder, f"{company_folder()}/Sales")

	def test_a_petty_cash_attachment_goes_to_petty_cash(self):
		voucher = make_petty_cash_voucher(GI_TECH)
		self.assertEqual(attach("Petty Cash Voucher", voucher.name).folder, f"{company_folder()}/Petty Cash")

	def test_an_unmapped_document_keeps_the_default_attachments_folder(self):
		attachments = frappe.db.get_value("File", {"is_attachments_folder": 1})
		self.assertEqual(attach("Customer", CUSTOMER, user="Administrator").folder, attachments)

	def test_a_folder_chosen_by_the_uploader_is_kept(self):
		invoice = make_sales_invoice(GI_TECH)
		self.assertEqual(attach("Sales Invoice", invoice.name, folder="Home").folder, "Home")

	def test_the_attachment_still_belongs_to_its_document(self):
		invoice = make_sales_invoice(GI_TECH)
		f = attach("Sales Invoice", invoice.name)
		self.assertEqual((f.attached_to_doctype, f.attached_to_name), ("Sales Invoice", invoice.name))
		with as_user(GI_TECH):
			self.assertTrue(frappe.has_permission("File", "read", doc=frappe.get_doc("File", f.name)))

	def test_existing_attachments_can_be_refiled(self):
		invoice = make_sales_invoice(GI_TECH)
		f = attach("Sales Invoice", invoice.name)
		attachments = frappe.db.get_value("File", {"is_attachments_folder": 1})
		frappe.db.set_value("File", f.name, "folder", attachments)  # as filed before this change

		plan = refile_existing_attachments(dry_run=True)
		self.assertGreaterEqual(plan.get(f"{company_folder()}/Sales", 0), 1)
		self.assertEqual(frappe.db.get_value("File", f.name, "folder"), attachments, "a dry run moves nothing")
