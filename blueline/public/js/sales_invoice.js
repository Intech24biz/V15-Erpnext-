// Cancel on a submitted Sales Invoice: Frappe first lists submitted documents linked to it and,
// if there are any, offers to cancel them all ("Cancel All Documents"). For a Sales Commission
// Entry that dialog only says the user may not cancel it, and the server's own answer ("Issue a
// Credit Note instead", tax_invoice_serial.block_cancel_of_tax_invoice) is never reached. Leaving
// commission entries out of that list sends the cancel straight to the server, exactly as on an
// invoice without one. The server still decides: an invoice with a Tax Invoice Serial is never
// cancelled, and commission entries are handled by sales_commission.guard_commission_entries_on_cancel.
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		// ERPNext sets this list in the Sales Invoice controller's onload, which runs first.
		const ignored = frm.ignore_doctypes_on_cancel_all || [];
		if (!ignored.includes("Sales Commission Entry")) {
			frm.ignore_doctypes_on_cancel_all = [...ignored, "Sales Commission Entry"];
		}
	},
});
