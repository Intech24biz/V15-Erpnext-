frappe.provide("blueline");

frappe.pages["quotation-history-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Quotation History Dashboard"),
		single_column: true,
	});

	wrapper.dashboard = new blueline.QuotationHistoryDashboard(page);
};

blueline.QuotationHistoryDashboard = class QuotationHistoryDashboard {
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

		this.status_field = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: [
				"",
				"Draft",
				"Open",
				"Replied",
				"Partially Ordered",
				"Ordered",
				"Lost",
				"Cancelled",
				"Expired",
			].join("\n"),
			change: () => me.refresh(),
		});

		this.page.set_primary_action(__("Refresh"), () => me.refresh(), "refresh");
		this.page.set_secondary_action(__("View All Records"), () => me.open_list());
	}

	get_filter_values() {
		return {
			company: this.company_field.get_value(),
			from_date: this.from_date_field.get_value(),
			to_date: this.to_date_field.get_value(),
			status: this.status_field.get_value(),
		};
	}

	open_list() {
		frappe.set_route("List", "Quotation History", this.get_filter_values());
	}

	setup_body() {
		if (!document.getElementById("qhd-style")) {
			$(`<style id="qhd-style">
				.quotation-history-dashboard { padding: 15px 0; }
				.quotation-history-dashboard .qhd-cards { margin-bottom: 20px; }
				.quotation-history-dashboard .qhd-card { margin-bottom: 15px; }
				.quotation-history-dashboard .qhd-card-inner {
					background: var(--card-bg, var(--fg-color));
					border: 1px solid var(--border-color);
					border-radius: var(--border-radius-md, 6px);
					padding: 15px;
					text-align: center;
				}
				.quotation-history-dashboard .qhd-card-value {
					font-size: 22px;
					font-weight: 600;
					color: var(--text-color);
				}
				.quotation-history-dashboard .qhd-card-label {
					font-size: 12px;
					color: var(--text-muted);
					margin-top: 4px;
					text-transform: uppercase;
				}
				.quotation-history-dashboard .qhd-chart-title {
					font-weight: 600;
					margin-bottom: 10px;
					color: var(--text-color);
				}
				.quotation-history-dashboard .qhd-charts,
				.quotation-history-dashboard .qhd-tables { margin-bottom: 25px; }
			</style>`).appendTo("head");
		}

		this.body = $(`
			<div class="quotation-history-dashboard">
				<div class="row qhd-cards"></div>
				<div class="row qhd-charts">
					<div class="col-md-6">
						<div class="qhd-chart-title">${__("Status Breakdown")}</div>
						<div class="qhd-status-chart"></div>
					</div>
					<div class="col-md-6">
						<div class="qhd-chart-title">${__("Monthly Trend (Value)")}</div>
						<div class="qhd-trend-chart"></div>
					</div>
				</div>
				<div class="row qhd-tables">
					<div class="col-md-6">
						<div class="qhd-chart-title">${__("Top Customers")}</div>
						<div class="qhd-top-customers"></div>
					</div>
					<div class="col-md-6">
						<div class="qhd-chart-title">${__("By Company")}</div>
						<div class="qhd-company-breakdown"></div>
					</div>
				</div>
				<div class="row qhd-charts">
					<div class="col-md-6">
						<div class="qhd-chart-title">${__("Top Items Quoted")}</div>
						<div class="qhd-top-items-chart"></div>
					</div>
					<div class="col-md-6">
						<div class="qhd-chart-title">${__("Top Items Quoted (Detail)")}</div>
						<div class="qhd-top-items"></div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.body);
	}

	refresh() {
		const me = this;
		frappe.call({
			method: "blueline.blueline.page.quotation_history_dashboard.quotation_history_dashboard.get_dashboard_data",
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
		this.render_cards(data.summary);
		this.render_status_chart(data.status_breakdown);
		this.render_trend_chart(data.monthly_trend);
		this.render_top_customers(data.top_customers);
		this.render_company_breakdown(data.company_breakdown);
		this.render_top_items(data.top_items);
	}

	render_cards(summary) {
		const currency = frappe.defaults.get_default("currency");
		const cards = [
			{ label: __("Total Quotations"), value: summary.total_quotations },
			{ label: __("Total Value"), value: format_currency(summary.total_value, currency) },
			{ label: __("Average Value"), value: format_currency(summary.avg_value, currency) },
			{ label: __("Conversion Rate"), value: `${summary.conversion_rate}%` },
			{ label: __("Won"), value: summary.won_count },
			{ label: __("Lost"), value: summary.lost_count },
		];

		const $cards = this.body.find(".qhd-cards").empty();
		cards.forEach((card) => {
			$(`
				<div class="col-md-2 col-sm-4 qhd-card">
					<div class="qhd-card-inner">
						<div class="qhd-card-value">${card.value}</div>
						<div class="qhd-card-label">${card.label}</div>
					</div>
				</div>
			`).appendTo($cards);
		});
	}

	render_status_chart(rows) {
		const $el = this.body.find(".qhd-status-chart").empty();
		if (!rows || !rows.length) {
			$el.html(`<div class="text-muted">${__("No Data")}</div>`);
			return;
		}
		new frappe.Chart($el[0], {
			data: {
				labels: rows.map((d) => __(d.status || "Not Set")),
				datasets: [{ values: rows.map((d) => d.count) }],
			},
			type: "pie",
			height: 260,
			colors: ["#5e64ff", "#28a745", "#ffa00a", "#ff5858", "#743ee2", "#00b0af", "#7cd6fd"],
		});
	}

	render_trend_chart(rows) {
		const $el = this.body.find(".qhd-trend-chart").empty();
		if (!rows || !rows.length) {
			$el.html(`<div class="text-muted">${__("No Data")}</div>`);
			return;
		}
		new frappe.Chart($el[0], {
			data: {
				labels: rows.map((d) => d.month),
				datasets: [{ name: __("Value"), values: rows.map((d) => d.value) }],
			},
			type: "line",
			height: 260,
			lineOptions: { regionFill: 1 },
			colors: ["#5e64ff"],
			axisOptions: {
				shortenYAxisNumbers: 1,
				numberFormatter: frappe.utils.format_chart_axis_number,
			},
		});
	}

	render_top_customers(rows) {
		const currency = frappe.defaults.get_default("currency");
		const $el = this.body.find(".qhd-top-customers").empty();
		if (!rows || !rows.length) {
			$el.html(`<div class="text-muted">${__("No Data")}</div>`);
			return;
		}
		const table = $(`
			<table class="table table-bordered">
				<thead>
					<tr>
						<th>${__("Customer")}</th>
						<th class="text-right">${__("Quotations")}</th>
						<th class="text-right">${__("Value")}</th>
					</tr>
				</thead>
				<tbody></tbody>
			</table>
		`).appendTo($el);
		const $tbody = table.find("tbody");
		rows.forEach((row) => {
			$(`
				<tr>
					<td>${frappe.utils.escape_html(row.customer_name || "")}</td>
					<td class="text-right">${row.count}</td>
					<td class="text-right">${format_currency(row.value, currency)}</td>
				</tr>
			`).appendTo($tbody);
		});
	}

	truncate_label(label, max_length = 15) {
		label = label || "";
		return label.length > max_length ? `${label.slice(0, max_length - 1)}…` : label;
	}

	render_top_items(rows) {
		const currency = frappe.defaults.get_default("currency");
		const $chart = this.body.find(".qhd-top-items-chart").empty();
		const $el = this.body.find(".qhd-top-items").empty();
		if (!rows || !rows.length) {
			$chart.html(`<div class="text-muted">${__("No Data")}</div>`);
			$el.html(`<div class="text-muted">${__("No Data")}</div>`);
			return;
		}

		const full_name_by_label = {};
		const chart_labels = rows.map((d) => {
			const full_name = d.item_name || d.item_code || "";
			const short_label = this.truncate_label(full_name);
			full_name_by_label[short_label] = full_name;
			return short_label;
		});

		new frappe.Chart($chart[0], {
			data: {
				labels: chart_labels,
				datasets: [{ name: __("Value"), values: rows.map((d) => d.total_value) }],
			},
			type: "bar",
			height: 260,
			colors: ["#5e64ff"],
			axisOptions: {
				shortenYAxisNumbers: 1,
				numberFormatter: frappe.utils.format_chart_axis_number,
				seriesLabelSpaceRatio: 0.9,
			},
			tooltipOptions: {
				formatTooltipX: (label) => full_name_by_label[label] || label,
				formatTooltipY: (value) => format_currency(value, currency),
			},
		});

		const table = $(`
			<table class="table table-bordered">
				<thead>
					<tr>
						<th>${__("Item")}</th>
						<th class="text-right">${__("Qty")}</th>
						<th class="text-right">${__("Value")}</th>
						<th class="text-right">${__("Quotations")}</th>
					</tr>
				</thead>
				<tbody></tbody>
			</table>
		`).appendTo($el);
		const $tbody = table.find("tbody");
		rows.forEach((row) => {
			$(`
				<tr>
					<td>${frappe.utils.escape_html(row.item_name || row.item_code || "")}</td>
					<td class="text-right">${row.total_qty}</td>
					<td class="text-right">${format_currency(row.total_value, currency)}</td>
					<td class="text-right">${row.quotation_count}</td>
				</tr>
			`).appendTo($tbody);
		});
	}

	render_company_breakdown(rows) {
		const currency = frappe.defaults.get_default("currency");
		const $el = this.body.find(".qhd-company-breakdown").empty();
		if (!rows || !rows.length) {
			$el.html(`<div class="text-muted">${__("No Data")}</div>`);
			return;
		}
		const table = $(`
			<table class="table table-bordered">
				<thead>
					<tr>
						<th>${__("Company")}</th>
						<th class="text-right">${__("Quotations")}</th>
						<th class="text-right">${__("Value")}</th>
					</tr>
				</thead>
				<tbody></tbody>
			</table>
		`).appendTo($el);
		const $tbody = table.find("tbody");
		rows.forEach((row) => {
			$(`
				<tr>
					<td>${frappe.utils.escape_html(row.company || "")}</td>
					<td class="text-right">${row.count}</td>
					<td class="text-right">${format_currency(row.value, currency)}</td>
				</tr>
			`).appendTo($tbody);
		});
	}
};
