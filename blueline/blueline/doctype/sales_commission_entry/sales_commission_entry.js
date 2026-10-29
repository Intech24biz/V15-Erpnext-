frappe.ui.form.on("Sales Commission Entry", {
	setup(frm) {
		// Only payouts the server will accept (SalesCommissionEntry.validate_payout): submitted,
		// type Pay, same company. The "not more than it paid" total is checked on save.
		frm.set_query("payment_entry", () => ({
			filters: { docstatus: 1, payment_type: "Pay", company: frm.doc.company },
		}));
	},

	refresh(frm) {
		// Set by the server when a payment on the invoice was undone after this entry was
		// ticked or approved; see sales_commission.reopen_if_unsettled.
		if (frm.doc.unpaid_warning) {
			frm.set_intro(frappe.utils.escape_html(frm.doc.unpaid_warning), "red");
		} else if (frm.doc.status === "Approved" && frm.doc.entry_type !== "Deduction" && !frm.doc.payment_entry) {
			frm.set_intro(
				__("To mark this entry Paid: choose the Payment Entry that paid it out, click Update, then Actions → Mark as Paid."),
				"blue"
			);
		}
	},
});
