frappe.provide("blueline");

frappe.pages["sales-commission-register"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Sales Commission Register"),
		single_column: true,
	});

	wrapper.commission_register = new blueline.SalesCommissionRegister(page);
};

blueline.SalesCommissionRegister = class SalesCommissionRegister {
	constructor(page) {
		this.page = page;
		this.setup_filters();
		this.setup_body();
		this.refresh();
	}

	setup_filters() {
		const me = this;

		this.status_field = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: [
				"",
				"Accrued",
				"Payment Received - Pending Approval",
				"Approved",
				"Paid",
				"Cancelled",
			].join("\n"),
			change: () => me.refresh(),
		});

		this.sales_person_field = this.page.add_field({
			fieldname: "sales_person",
			label: __("Sales Person"),
			fieldtype: "Link",
			options: "Sales Person",
			change: () => me.refresh(),
		});

		this.company_field = this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("company"),
			change: () => me.refresh(),
		});

		this.from_date_field = this.page.add_field({
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			change: () => me.refresh(),
		});

		this.to_date_field = this.page.add_field({
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			change: () => me.refresh(),
		});

		this.page.set_primary_action(__("Refresh"), () => me.refresh(), "refresh");
	}

	get_filter_values() {
		return {
			status: this.status_field.get_value(),
			sales_person: this.sales_person_field.get_value(),
			company: this.company_field.get_value(),
			from_date: this.from_date_field.get_value(),
			to_date: this.to_date_field.get_value(),
		};
	}

	setup_body() {
		if (!document.getElementById("scr-style")) {
			$(`<style id="scr-style">
				.sales-commission-register { padding: 15px 0; }
				.sales-commission-register .scr-summary { margin-bottom: 20px; }
				.sales-commission-register .scr-summary-card {
					background: var(--card-bg, var(--fg-color));
					border: 1px solid var(--border-color);
					border-radius: var(--border-radius-md, 6px);
					padding: 12px 15px;
					margin-bottom: 15px;
				}
				.sales-commission-register .scr-summary-count {
					font-size: 20px;
					font-weight: 600;
					color: var(--text-color);
				}
				.sales-commission-register .scr-summary-amount {
					font-size: 13px;
					color: var(--text-muted);
				}
				.sales-commission-register .scr-summary-label {
					font-size: 11px;
					font-weight: 600;
					text-transform: uppercase;
					color: var(--text-muted);
					margin-bottom: 4px;
				}
				.sales-commission-register .scr-table-wrapper { overflow-x: auto; }
				.sales-commission-register .scr-badge {
					font-size: 11px;
					font-weight: 600;
					padding: 2px 8px;
					border-radius: 10px;
					white-space: nowrap;
				}
				.sales-commission-register .scr-badge-accrued { background: var(--bg-gray, #f3f3f3); color: var(--text-on-gray, #6c7680); }
				.sales-commission-register .scr-badge-pending { background: var(--bg-yellow, #fff6e0); color: var(--text-on-yellow, #8a6d00); }
				.sales-commission-register .scr-badge-approved { background: var(--bg-blue, #e3f0ff); color: var(--text-on-blue, #2563a8); }
				.sales-commission-register .scr-badge-paid { background: var(--bg-green, #e4f5e9); color: var(--text-on-green, #2f7a4d); }
				.sales-commission-register .scr-badge-cancelled { background: var(--bg-red, #fde7e7); color: var(--text-on-red, #b8362f); }
				.sales-commission-register .scr-empty { text-align: center; padding: 50px 15px; color: var(--text-muted); }
			</style>`).appendTo("head");
		}

		this.body = $(`
			<div class="sales-commission-register">
				<div class="row scr-summary"></div>
				<div class="scr-table-wrapper"></div>
			</div>
		`).appendTo(this.page.body);
	}

	refresh() {
		const me = this;
		frappe.call({
			method:
				"blueline.blueline.page.sales_commission_register.sales_commission_register.get_entries",
			args: this.get_filter_values(),
			freeze: true,
			callback(r) {
				if (r.message) {
					me.render(r.message);
				}
			},
		});
	}

	render(data) {
		this.render_summary(data.summary, data.status_options);
		this.render_table(data.entries);
	}

	render_summary(summary, status_options) {
		const currency = frappe.defaults.get_default("currency");
		const $summary = this.body.find(".scr-summary").empty();

		status_options.forEach((status) => {
			const bucket = summary[status] || { count: 0, commission_amount: 0 };
			$(`
				<div class="col-md-2 col-sm-4">
					<div class="scr-summary-card">
						<div class="scr-summary-label">${__(status)}</div>
						<div class="scr-summary-count">${bucket.count}</div>
						<div class="scr-summary-amount">${format_currency(bucket.commission_amount, currency)}</div>
					</div>
				</div>
			`).appendTo($summary);
		});
	}

	status_badge(status) {
		const classes = {
			Accrued: "scr-badge-accrued",
			"Payment Received - Pending Approval": "scr-badge-pending",
			Approved: "scr-badge-approved",
			Paid: "scr-badge-paid",
			Cancelled: "scr-badge-cancelled",
		};
		const cls = classes[status] || "scr-badge-accrued";
		return `<span class="scr-badge ${cls}">${frappe.utils.escape_html(__(status))}</span>`;
	}

	render_table(rows) {
		const currency = frappe.defaults.get_default("currency");
		const $el = this.body.find(".scr-table-wrapper").empty();

		if (!rows || !rows.length) {
			$el.html(`<div class="scr-empty">${__("No commission entries found")}</div>`);
			return;
		}

		const table = $(`
			<table class="table table-bordered">
				<thead>
					<tr>
						<th>${__("Entry")}</th>
						<th>${__("Sales Invoice")}</th>
						<th>${__("Posting Date")}</th>
						<th>${__("Sales Person")}</th>
						<th>${__("Customer")}</th>
						<th>${__("Item")}</th>
						<th>${__("Company")}</th>
						<th class="text-right">${__("Qty")}</th>
						<th class="text-right">${__("Line Amount")}</th>
						<th class="text-right">${__("Commission")}</th>
						<th>${__("Status")}</th>
						<th>${__("Payment Entry")}</th>
					</tr>
				</thead>
				<tbody></tbody>
			</table>
		`).appendTo($el);
		const $tbody = table.find("tbody");

		rows.forEach((row) => {
			$(`
				<tr>
					<td><a href="/app/sales-commission-entry/${encodeURIComponent(row.name)}">${frappe.utils.escape_html(row.name)}</a></td>
					<td><a href="/app/sales-invoice/${encodeURIComponent(row.sales_invoice)}">${frappe.utils.escape_html(row.sales_invoice || "")}</a></td>
					<td>${row.posting_date ? frappe.datetime.str_to_user(row.posting_date) : ""}</td>
					<td>${frappe.utils.escape_html(row.sales_person || "")}</td>
					<td>${frappe.utils.escape_html(row.customer || "")}</td>
					<td>${frappe.utils.escape_html(row.item_code || "")}</td>
					<td>${frappe.utils.escape_html(row.company || "")}</td>
					<td class="text-right">${row.qty}</td>
					<td class="text-right">${format_currency(row.amount, currency)}</td>
					<td class="text-right">${format_currency(row.commission_amount, currency)}</td>
					<td>${this.status_badge(row.status)}</td>
					<td>${row.payment_entry ? frappe.utils.escape_html(row.payment_entry) : ""}</td>
				</tr>
			`).appendTo($tbody);
		});
	}
};
