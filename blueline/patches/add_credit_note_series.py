import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from blueline.server_scripts.tax_invoice_serial import CREDIT_NOTE_SERIES


def execute():
	# Credit Notes are named from these series (see set_credit_note_series). Add each one to
	# the Sales Invoice series list next to the tax-invoice series it pairs with, keeping
	# the site's existing options and their order untouched.
	options = (frappe.get_meta("Sales Invoice").get_field("naming_series").options or "").split("\n")
	missing = [
		credit_note_series
		for invoice_series, credit_note_series in CREDIT_NOTE_SERIES.items()
		if invoice_series in options and credit_note_series not in options
	]
	if not missing:
		return

	make_property_setter(
		"Sales Invoice",
		"naming_series",
		"options",
		"\n".join(options + missing),
		"Text",
		validate_fields_for_doctype=False,
	)
	frappe.clear_cache(doctype="Sales Invoice")
