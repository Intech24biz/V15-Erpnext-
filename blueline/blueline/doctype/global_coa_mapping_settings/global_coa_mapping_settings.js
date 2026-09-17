frappe.provide("blueline");

const ACCOUNT_FIELDS = [
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

const COST_CENTER_FIELDS = ["default_cost_center"];
const WAREHOUSE_FIELDS = ["default_warehouse"];

frappe.ui.form.on("Global COA Mapping Settings", {
	refresh(frm) {
		blueline.set_company_coa_mapping_queries(frm);
	},
});

blueline.set_company_coa_mapping_queries = function (frm) {
	// Each callback reads the row's current `company` at query time (via cdt/cdn), so
	// registering these once on refresh is enough — no separate on-change handler is
	// needed per row, and newly added rows pick up the same filters automatically.
	ACCOUNT_FIELDS.forEach((fieldname) => {
		frm.set_query(fieldname, "company_mappings", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				filters: {
					company: row.company,
					is_group: 0,
				},
			};
		});
	});

	COST_CENTER_FIELDS.forEach((fieldname) => {
		frm.set_query(fieldname, "company_mappings", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return { filters: { company: row.company } };
		});
	});

	WAREHOUSE_FIELDS.forEach((fieldname) => {
		frm.set_query(fieldname, "company_mappings", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return { filters: { company: row.company } };
		});
	});
};
