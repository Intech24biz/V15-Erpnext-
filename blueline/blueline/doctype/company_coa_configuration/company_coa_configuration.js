const COA_ACCOUNT_FIELDS = [
	"default_cash_account",
	"default_bank_account",
	"temporary_opening_account",
	"stock_adjustment_account",
	"stock_received_but_not_billed",
	"expenses_included_in_valuation",
	"exchange_gain_loss_account",
	"foreign_currency_revaluation_account",
	"inter_company_clearing_account",
];

const COA_COST_CENTER_FIELDS = ["default_cost_center"];
const COA_WAREHOUSE_FIELDS = ["default_warehouse"];
const COA_COMPANY_LINKED_FIELDS = [
	...COA_ACCOUNT_FIELDS,
	...COA_COST_CENTER_FIELDS,
	...COA_WAREHOUSE_FIELDS,
];

frappe.ui.form.on("Company COA Configuration", {
	setup(frm) {
		// Callbacks run each time a picker opens, so they always read the current company.
		COA_ACCOUNT_FIELDS.forEach((fieldname) => {
			frm.set_query(fieldname, () => ({
				filters: { company: frm.doc.company, is_group: 0 },
			}));
		});

		[...COA_COST_CENTER_FIELDS, ...COA_WAREHOUSE_FIELDS].forEach((fieldname) => {
			frm.set_query(fieldname, () => ({
				filters: { company: frm.doc.company },
			}));
		});
	},

	refresh(frm) {
		frm.trigger("toggle_company_linked_fields");
	},

	company(frm) {
		// Values picked for a previous company are invalid for the new one.
		COA_COMPANY_LINKED_FIELDS.forEach((fieldname) => frm.set_value(fieldname, ""));
		frm.trigger("toggle_company_linked_fields");
	},

	toggle_company_linked_fields(frm) {
		// With no company, the filters above would drop the company condition and list
		// every company's accounts, so the pickers stay disabled until a company is set.
		frm.toggle_enable(COA_COMPANY_LINKED_FIELDS, !!frm.doc.company);
	},
});
