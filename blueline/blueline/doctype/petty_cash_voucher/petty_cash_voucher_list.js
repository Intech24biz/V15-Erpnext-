// The Amount column is in the voucher's company currency (field option
// "Company:company:default_currency"). The list only shows the right currency when each row
// carries its company, which Frappe does not fetch on its own for such options.
frappe.listview_settings["Petty Cash Voucher"] = {
	add_fields: ["company"],
};
