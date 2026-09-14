frappe.provide("blueline");

frappe.pages["vat-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("VAT Dashboard"),
		single_column: true,
	});

	wrapper.dashboard = new blueline.VatDashboard(page);
};

blueline.VatDashboard = class VatDashboard {
	constructor(page) {
		this.page = page;
		this.setup_filters();
		this.setup_body();
		this.refresh();
	}

	setup_filters() {
		const me = this;

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
		this.page.add_inner_button(__("Export to Excel"), () => me.export_to_excel());
	}

	get_filter_values() {
		return {
			company: this.company_field.get_value(),
			from_date: this.from_date_field.get_value(),
			to_date: this.to_date_field.get_value(),
		};
	}

	setup_body() {
		if (!document.getElementById("vatd-style")) {
			$(`<style id="vatd-style">
				.vat-dashboard { padding: 15px 0; }
				.vat-dashboard .vatd-cards { margin-bottom: 20px; }
				.vat-dashboard .vatd-card { margin-bottom: 15px; }
				.vat-dashboard .vatd-card-inner {
					background: var(--card-bg, var(--fg-color));
					border: 1px solid var(--border-color);
					border-radius: var(--border-radius-md, 6px);
					padding: 15px;
					text-align: center;
				}
				.vat-dashboard .vatd-card-value {
					font-size: 22px;
					font-weight: 600;
					color: var(--text-color);
				}
				.vat-dashboard .vatd-card-value.vatd-refund {
					color: var(--red-500, #ff5858);
				}
				.vat-dashboard .vatd-card-label {
					font-size: 12px;
					color: var(--text-muted);
					margin-top: 4px;
					text-transform: uppercase;
				}
				.vat-dashboard .vatd-chart-title {
					font-weight: 600;
					margin-bottom: 10px;
					color: var(--text-color);
				}
				.vat-dashboard .vatd-charts,
				.vat-dashboard .vatd-tables { margin-bottom: 25px; }
				.vat-dashboard .vatd-totals-row { font-weight: 600; }
			</style>`).appendTo("head");
		}

		this.body = $(`
			<div class="vat-dashboard">
				<div class="row vatd-cards"></div>
				<div class="row vatd-charts">
					<div class="col-md-12">
						<div class="vatd-chart-title">${__("Monthly Output vs Input vs Net VAT")}</div>
						<div class="vatd-monthly-chart"></div>
					</div>
				</div>
				<div class="row vatd-tables">
					<div class="col-md-12">
						<div class="vatd-chart-title">${__("Monthly VAT Summary")}</div>
						<div class="vatd-monthly-table"></div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.body);
	}

	refresh() {
		const me = this;
		const filters = this.get_filter_values();
		if (!filters.company) {
			return;
		}
		frappe.call({
			method: "blueline.blueline.page.vat_dashboard.vat_dashboard.get_vat_data",
			args: filters,
			freeze: true,
			callback(r) {
				if (r.message) {
					me.data = r.message;
					me.render(r.message);
				}
			},
		});
	}

	render(data) {
		this.render_cards(data.summary);
		this.render_monthly_chart(data.monthly);
		this.render_monthly_table(data.monthly);
	}

	render_cards(summary) {
		const currency = frappe.defaults.get_default("currency");
		const net_is_refund = summary.net_vat < 0;
		const net_label = net_is_refund ? __("Net VAT Refund") : __("Net VAT Payable");
		const net_value = net_is_refund
			? `(${format_currency(Math.abs(summary.net_vat), currency)})`
			: format_currency(summary.net_vat, currency);

		const cards = [
			{ label: __("Total Output VAT"), value: format_currency(summary.total_output, currency) },
			{ label: __("Total Input VAT (Recoverable)"), value: format_currency(summary.total_input, currency) },
			{ label: net_label, value: net_value, refund: net_is_refund },
		];

		const $cards = this.body.find(".vatd-cards").empty();
		cards.forEach((card) => {
			$(`
				<div class="col-md-4 col-sm-4 vatd-card">
					<div class="vatd-card-inner">
						<div class="vatd-card-value ${card.refund ? "vatd-refund" : ""}">${card.value}</div>
						<div class="vatd-card-label">${card.label}</div>
					</div>
				</div>
			`).appendTo($cards);
		});
	}

	render_monthly_chart(rows) {
		const $el = this.body.find(".vatd-monthly-chart").empty();
		if (!rows || !rows.length) {
			$el.html(`<div class="text-muted">${__("No Data")}</div>`);
			return;
		}
		new frappe.Chart($el[0], {
			data: {
				labels: rows.map((d) => d.month),
				datasets: [
					{ name: __("Output VAT"), values: rows.map((d) => d.output) },
					{ name: __("Input VAT"), values: rows.map((d) => d.input) },
					{ name: __("Net VAT"), values: rows.map((d) => d.net) },
				],
			},
			type: "bar",
			height: 280,
			colors: ["#ff5858", "#28a745", "#5e64ff"],
			axisOptions: {
				shortenYAxisNumbers: 1,
				numberFormatter: frappe.utils.format_chart_axis_number,
			},
		});
	}

	render_monthly_table(rows) {
		const currency = frappe.defaults.get_default("currency");
		const $el = this.body.find(".vatd-monthly-table").empty();
		if (!rows || !rows.length) {
			$el.html(`<div class="text-muted">${__("No Data")}</div>`);
			return;
		}

		const table = $(`
			<table class="table table-bordered">
				<thead>
					<tr>
						<th>${__("Month")}</th>
						<th class="text-right">${__("Output VAT")}</th>
						<th class="text-right">${__("Input VAT")}</th>
						<th class="text-right">${__("Net")}</th>
					</tr>
				</thead>
				<tbody></tbody>
			</table>
		`).appendTo($el);
		const $tbody = table.find("tbody");

		let total_output = 0;
		let total_input = 0;
		let total_net = 0;

		rows.forEach((row) => {
			total_output += row.output;
			total_input += row.input;
			total_net += row.net;
			$(`
				<tr>
					<td>${frappe.utils.escape_html(row.month || "")}</td>
					<td class="text-right">${format_currency(row.output, currency)}</td>
					<td class="text-right">${format_currency(row.input, currency)}</td>
					<td class="text-right">${format_currency(row.net, currency)}</td>
				</tr>
			`).appendTo($tbody);
		});

		$(`
			<tr class="vatd-totals-row">
				<td>${__("Total")}</td>
				<td class="text-right">${format_currency(total_output, currency)}</td>
				<td class="text-right">${format_currency(total_input, currency)}</td>
				<td class="text-right">${format_currency(total_net, currency)}</td>
			</tr>
		`).appendTo($tbody);
	}

	export_to_excel() {
		const rows = (this.data && this.data.monthly) || [];
		if (!rows.length) {
			frappe.msgprint(__("No data to export"));
			return;
		}

		const header = [__("Month"), __("Output VAT"), __("Input VAT"), __("Net VAT")];
		const csv_rows = [header];

		let total_output = 0;
		let total_input = 0;
		let total_net = 0;

		rows.forEach((row) => {
			total_output += row.output;
			total_input += row.input;
			total_net += row.net;
			csv_rows.push([row.month, row.output, row.input, row.net]);
		});
		csv_rows.push([__("Total"), total_output, total_input, total_net]);

		const csv_content = csv_rows
			.map((row) =>
				row
					.map((cell) => {
						const value = cell === null || cell === undefined ? "" : String(cell);
						return `"${value.replace(/"/g, '""')}"`;
					})
					.join(",")
			)
			.join("\r\n");

		const filters = this.get_filter_values();
		const filename = `VAT-Dashboard-${filters.company || "All"}.csv`;

		const blob = new Blob(["﻿" + csv_content], { type: "text/csv;charset=utf-8;" });
		const link = document.createElement("a");
		link.href = URL.createObjectURL(blob);
		link.download = filename;
		document.body.appendChild(link);
		link.click();
		document.body.removeChild(link);
		URL.revokeObjectURL(link.href);
	}
};
