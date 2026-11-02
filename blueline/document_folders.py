"""Online document storage segmented by fiscal year.

Folders (in the File manager, /app/file):

	Home/Fiscal Year <FY>/<Company>/<Category>

are created for every Fiscal Year and company (after every migrate and when a Fiscal Year is
created). A file attached to a business document is filed into the folder for that
document's company, fiscal year (from its posting / transaction date) and category, instead
of the shared Home/Attachments. Files stay attached to their document, so who can open them
does not change.
"""

import frappe
from frappe.utils import getdate

from erpnext.accounts.utils import get_fiscal_year

HOME = "Home"
ATTACHMENTS = "Home/Attachments"

SALES = "Sales"
PURCHASES = "Purchases"
BANK = "Bank & Payments"
PETTY_CASH = "Petty Cash"
SHIPPING = "Shipping & CusDec"
GENERAL = "General"
CATEGORIES = (SALES, PURCHASES, BANK, PETTY_CASH, SHIPPING, GENERAL)

# Document type -> category folder. Landed Cost Vouchers carry the import costs, so their
# CusDec and shipping papers go with them.
CATEGORY_BY_DOCTYPE = {
	"Quotation": SALES,
	"Sales Order": SALES,
	"Delivery Note": SALES,
	"Sales Invoice": SALES,
	"Purchase Order": PURCHASES,
	"Purchase Receipt": PURCHASES,
	"Purchase Invoice": PURCHASES,
	"Payment Entry": BANK,
	"Journal Entry": BANK,
	"Bank Transaction": BANK,
	"Petty Cash Voucher": PETTY_CASH,
	"Landed Cost Voucher": SHIPPING,
}
DATE_FIELDS = ("posting_date", "transaction_date", "date")


def fiscal_year_folder(fiscal_year):
	return f"{HOME}/Fiscal Year {fiscal_year}"


def _ensure_folder(name, parent):
	path = f"{parent}/{name}"
	if not frappe.db.exists("File", path):
		folder = frappe.get_doc({"doctype": "File", "file_name": name, "is_folder": 1, "folder": parent})
		folder.flags.ignore_permissions = True
		folder.insert()
	return path


def _fiscal_year_companies(fiscal_year):
	companies = frappe.get_all("Fiscal Year Company", filters={"parent": fiscal_year}, pluck="company")
	# A Fiscal Year with no companies listed applies to every company.
	return companies or frappe.get_all("Company", pluck="name")


def ensure_fiscal_year_folders(fiscal_year):
	fy_folder = _ensure_folder(f"Fiscal Year {fiscal_year}", HOME)
	for company in _fiscal_year_companies(fiscal_year):
		company_folder = _ensure_folder(company, fy_folder)
		for category in CATEGORIES:
			_ensure_folder(category, company_folder)


def ensure_all_folders():
	"""after_migrate: folders for every Fiscal Year that isn't disabled. Only creates."""
	for fiscal_year in frappe.get_all("Fiscal Year", filters={"disabled": 0}, pluck="name"):
		ensure_fiscal_year_folders(fiscal_year)


def on_fiscal_year_insert(doc, method=None):
	"""Fiscal Year `after_insert`."""
	ensure_fiscal_year_folders(doc.name)


def target_folder(doctype, docname):
	"""The folder a file attached to this document belongs in, or None to leave it where
	Frappe puts it (unmapped type, no company or date, or no fiscal year for the date)."""
	category = CATEGORY_BY_DOCTYPE.get(doctype)
	if not category or not docname or not frappe.db.exists(doctype, docname):
		return None
	meta = frappe.get_meta(doctype)
	date_field = next((f for f in DATE_FIELDS if meta.has_field(f)), None)
	if not date_field or not meta.has_field("company"):
		return None
	company, date = frappe.db.get_value(doctype, docname, ["company", date_field])
	if not company or not date:
		return None
	try:
		fiscal_year = get_fiscal_year(getdate(date), company=company, verbose=0)[0]
	except Exception:
		return None

	company_folder = _ensure_folder(company, _ensure_folder(f"Fiscal Year {fiscal_year}", HOME))
	return _ensure_folder(category, company_folder)


def refile_existing_attachments(dry_run=True):
	"""One-off, run by hand: move attachments already in Home/Attachments into their fiscal
	year folders. Only the File's folder changes; the file itself and what it is attached
	to stay the same. Dry run by default:

		bench --site <site> execute blueline.document_folders.refile_existing_attachments
		bench --site <site> execute blueline.document_folders.refile_existing_attachments --kwargs "{'dry_run': False}"
	"""
	attachments = frappe.db.get_value("File", {"is_attachments_folder": 1}) or ATTACHMENTS
	files = frappe.get_all(
		"File",
		filters={"folder": attachments, "is_folder": 0, "attached_to_doctype": ["in", list(CATEGORY_BY_DOCTYPE)]},
		fields=["name", "attached_to_doctype", "attached_to_name"],
	)
	moved = {}
	for f in files:
		folder = target_folder(f.attached_to_doctype, f.attached_to_name)
		if not folder:
			continue
		moved[folder] = moved.get(folder, 0) + 1
		if not dry_run:
			frappe.db.set_value("File", f.name, "folder", folder, update_modified=False)
	if not dry_run:
		frappe.db.commit()
	for folder, count in sorted(moved.items()):
		print(f"{'would move' if dry_run else 'moved'} {count:>5}  -> {folder}")
	return moved


def file_attachment(doc, method=None):
	"""File `before_insert`: an attachment that would land in Home/Attachments (Frappe's
	default for attached files) is filed by fiscal year, company and category instead. A
	folder chosen explicitly by the uploader is kept."""
	if doc.is_folder or not doc.attached_to_doctype:
		return
	# File.before_insert (which runs before this hook) has already set the folder to the
	# Attachments folder unless the uploader picked one.
	attachments = frappe.db.get_value("File", {"is_attachments_folder": 1}) or ATTACHMENTS
	if doc.folder and doc.folder != attachments:
		return
	try:
		folder = target_folder(doc.attached_to_doctype, doc.attached_to_name)
	except Exception:
		# Filing is a convenience; it must never stop an upload.
		frappe.log_error(title="Blueline: could not file attachment by fiscal year", message=frappe.get_traceback())
		return
	if folder:
		doc.folder = folder
