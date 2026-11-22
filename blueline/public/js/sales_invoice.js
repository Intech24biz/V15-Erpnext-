// Cancel on a submitted Sales Invoice: Frappe first lists submitted documents linked to it and,
// if there are any, offers to cancel them all ("Cancel All Documents"). For a Sales Commission
// Entry that dialog only says the user may not cancel it, and the server's own answer ("Issue a
// Credit Note instead", tax_invoice_serial.block_cancel_of_tax_invoice) is never reached. Leaving
// commission entries out of that list sends the cancel straight to the server, exactly as on an
// invoice without one. The server still decides: an invoice with a Tax Invoice Serial is never
// cancelled, and commission entries are handled by sales_commission.guard_commission_entries_on_cancel.
const BLUELINE_KEEP_OUT_OF_CANCEL_ALL = "Sales Commission Entry";

frappe.ui.form.on("Sales Invoice", {
	setup(frm) {
		// ERPNext's Sales Invoice controller replaces this list when the form loads, and the
		// order of form handlers isn't fixed, so keep the entry in whatever list is assigned.
		let ignored = with_commission_entry(frm.ignore_doctypes_on_cancel_all);
		Object.defineProperty(frm, "ignore_doctypes_on_cancel_all", {
			configurable: true,
			get: () => ignored,
			set: (value) => {
				ignored = with_commission_entry(value);
			},
		});
	},
});

function with_commission_entry(list) {
	list = list || [];
	return list.includes(BLUELINE_KEEP_OUT_OF_CANCEL_ALL) ? list : [...list, BLUELINE_KEEP_OUT_OF_CANCEL_ALL];
}
