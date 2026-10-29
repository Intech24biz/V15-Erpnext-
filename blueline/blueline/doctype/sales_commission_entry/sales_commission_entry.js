frappe.ui.form.on("Sales Commission Entry", {
	refresh(frm) {
		// Set by the server when a payment on the invoice was undone after this entry was
		// ticked or approved; see sales_commission.reopen_if_unsettled.
		if (frm.doc.unpaid_warning) {
			frm.set_intro(frappe.utils.escape_html(frm.doc.unpaid_warning), "red");
		}
	},
});
