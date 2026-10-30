frappe.provide("blueline");

frappe.pages["business-kpi-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Business KPI Dashboard"),
		single_column: true,
	});

	wrapper.kpi_dashboard = new blueline.BusinessKpiDashboard(page);
};

blueline.BusinessKpiDashboard = class BusinessKpiDashboard {
	constructor(page) {
		this.page = page;
		this.active_tab = "sales";
		this.cache = {};
		this.setup_filters();
		this.setup_body();
		this.load_active_tab();
	}

	setup_filters() {
		const me = this;

		this.company_field = this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			change: () => me.refresh(),
		});

		this.page.set_primary_action(__("Refresh"), () => me.refresh(), "refresh");
	}

	get_company() {
		return this.company_field.get_value();
	}

	refresh() {
		this.cache = {};
		this.load_active_tab();
	}

	setup_body() {
		if (!document.getElementById("bkpi-style")) {
			$(`<style id="bkpi-style">
				.bkpi { padding: 15px 0; }
				.bkpi .bkpi-tabs {
					display: flex;
					gap: 4px;
					border-bottom: 1px solid var(--border-color);
					margin-bottom: 20px;
				}
				.bkpi .bkpi-tab-btn {
					background: none;
					border: none;
					border-bottom: 2px solid transparent;
					padding: 10px 16px;
					font-weight: 600;
					color: var(--text-muted);
					cursor: pointer;
				}
				.bkpi .bkpi-tab-btn.active {
					color: var(--text-color);
					border-bottom-color: var(--primary, #5e64ff);
				}
				.bkpi .bkpi-tab-panel[hidden] { display: none; }
				.bkpi .bkpi-section { margin-bottom: 25px; }
				.bkpi .bkpi-section-title {
					font-weight: 600;
					margin-bottom: 10px;
					color: var(--text-color);
				}
				.bkpi .bkpi-cards { margin-bottom: 5px; }
				.bkpi .bkpi-card {
					background: var(--card-bg, var(--fg-color));
					border: 1px solid var(--border-color);
					border-radius: var(--border-radius-md, 6px);
					padding: 15px;
					text-align: center;
					margin-bottom: 15px;
				}
				.bkpi .bkpi-card-value {
					font-size: 22px;
					font-weight: 600;
					color: var(--text-color);
				}
				.bkpi .bkpi-card-label {
					font-size: 12px;
					color: var(--text-muted);
					margin-top: 4px;
					text-transform: uppercase;
				}
				.bkpi .bkpi-card.bkpi-highlight {
					border-top: 4px solid var(--red-500, #ff5858);
				}
				.bkpi .bkpi-card.bkpi-highlight .bkpi-card-value {
					font-size: 32px;
					color: var(--red-500, #ff5858);
				}
				.bkpi .bkpi-card.bkpi-alert { border-top: 4px solid var(--red-500, #ff5858); }
				.bkpi .bkpi-card-sub { font-size: 12px; color: var(--text-muted); margin-top: 6px; }
				.bkpi .bkpi-card-alert { font-size: 12px; margin-top: 6px; }
				.bkpi .bkpi-card-alert a { color: var(--red-600, #e24c4c); }
				.bkpi .bkpi-section-note { font-size: 12px; color: var(--text-muted); margin-bottom: 10px; }
				.bkpi .bkpi-table-wrapper { overflow-x: auto; }
				.bkpi .bkpi-empty {
					text-align: center;
					padding: 30px 15px;
					color: var(--text-muted);
				}
			</style>`).appendTo("head");
		}

		this.body = $(`
			<div class="bkpi">
				<div class="bkpi-tabs">
					<button type="button" class="bkpi-tab-btn active" data-tab="sales">${__(
						"Sales Performance"
					)}</button>
					<button type="button" class="bkpi-tab-btn" data-tab="financial">${__(
						"Financial Health"
					)}</button>
					<button type="button" class="bkpi-tab-btn" data-tab="commission">${__(
						"Commission & Payroll"
					)}</button>
				</div>
				<div class="bkpi-tab-panel" data-panel="sales"></div>
				<div class="bkpi-tab-panel" data-panel="financial" hidden></div>
				<div class="bkpi-tab-panel" data-panel="commission" hidden></div>
			</div>
		`).appendTo(this.page.body);

		this.body.find(".bkpi-tab-btn").on("click", (e) => {
			const tab = $(e.currentTarget).data("tab");
			this.switch_tab(tab);
		});
	}

	switch_tab(tab) {
		this.active_tab = tab;
		this.body.find(".bkpi-tab-btn").removeClass("active");
		this.body.find(`.bkpi-tab-btn[data-tab="${tab}"]`).addClass("active");
		this.body.find(".bkpi-tab-panel").prop("hidden", true);
		this.body.find(`.bkpi-tab-panel[data-panel="${tab}"]`).prop("hidden", false);
		this.load_active_tab();
	}

	load_active_tab() {
		const loaders = {
			sales: () => this.load_sales_performance(),
			financial: () => this.load_financial_health(),
			commission: () => this.load_commission_payroll(),
		};
		loaders[this.active_tab]();
	}

	call(method, panel_selector, render_fn) {
		const me = this;
		const company = this.get_company();
		const cache_key = `${method}:${company || ""}`;

		if (this.cache[cache_key]) {
			this.response_currency = this.cache[cache_key].currency;
			render_fn(this.cache[cache_key]);
			return;
		}

		frappe.call({
			method: `blueline.blueline.page.business_kpi_dashboard.business_kpi_dashboard.${method}`,
			args: { company },
			freeze: true,
			callback(r) {
				if (r.message) {
					me.cache[cache_key] = r.message;
					me.response_currency = r.message.currency;
					render_fn(r.message);
				}
			},
		});
	}

	empty(label) {
		return `<div class="bkpi-empty">${__(label || "No data")}</div>`;
	}

	// ------------------------------------------------------------------
	// Tab 1 — Sales Performance
	// ------------------------------------------------------------------

	load_sales_performance() {
		const $panel = this.body.find('[data-panel="sales"]');
		if (!$panel.find(".bkpi-initialized").length) {
			$panel.html(`
				<div class="bkpi-initialized"></div>
				<div class="bkpi-section-note">${__("Net sales: excluding VAT, in company currency, Credit Notes deducted.")}</div>
				<div class="row bkpi-cards bkpi-sales-kpis"></div>
				<div class="bkpi-section">
					<div class="bkpi-section-title">${__("Net Sales Trend (Last 12 Months)")}</div>
					<div class="bkpi-trend-chart"></div>
				</div>
				<div class="row">
					<div class="col-md-6 bkpi-section">
						<div class="bkpi-section-title">${__("Top 10 Customers (This Fiscal Year)")}</div>
						<div class="bkpi-top-customers"></div>
					</div>
					<div class="col-md-6 bkpi-section">
						<div class="bkpi-section-title">${__("Top 10 Items (This Fiscal Year)")}</div>
						<div class="bkpi-top-items"></div>
					</div>
				</div>
				<div class="bkpi-section">
					<div class="bkpi-section-title">${__("Revenue by Company (This Fiscal Year)")}</div>
					<div class="bkpi-revenue-by-company"></div>
				</div>
			`);
		}

		this.call("get_sales_performance", $panel, (data) => this.render_sales_performance($panel, data));
	}

	render_sales_performance($panel, data) {
		const currency = this.currency();
		const k = data.kpis;
		// Sections the user can't read come back as null (see _readable on the server).
		const q = k.quotations || { count: "—", value: 0, open_value: 0, converted: "—", conversion_rate: "—" };
		const no_quotations = !k.quotations;
		this.render_cards($panel.find(".bkpi-sales-kpis"), [
			{
				label: __("Net Sales This Month"),
				value: format_currency(k.this_month, currency),
				sub: __("Last month: {0}", [format_currency(k.last_month, currency)]),
			},
			{
				label: __("Net Sales Fiscal Year to Date"),
				value: format_currency(k.fy_to_date, currency),
				sub: __("Same period last year: {0}", [format_currency(k.last_fy_to_date, currency)]),
			},
			{
				label: __("Quotations This Fiscal Year"),
				value: `${q.count}`,
				sub: no_quotations
					? __("No access to Quotations")
					: __("Value {0}; open {1}", [format_currency(q.value, currency), format_currency(q.open_value, currency)]),
			},
			{
				label: __("Quotation Conversion"),
				value: no_quotations ? "—" : `${q.conversion_rate}%`,
				sub: no_quotations ? __("No access to Quotations") : __("{0} of {1} ordered", [q.converted, q.count]),
			},
		]);

		const $chart = $panel.find(".bkpi-trend-chart").empty();
		if (data.trend && data.trend.length) {
			new frappe.Chart($chart[0], {
				data: {
					labels: data.trend.map((d) => d.month),
					datasets: [{ name: __("Net Sales"), values: data.trend.map((d) => d.total) }],
				},
				type: "line",
				height: 240,
				lineOptions: { regionFill: 1 },
				colors: ["#5e64ff"],
				axisOptions: {
					shortenYAxisNumbers: 1,
					numberFormatter: frappe.utils.format_chart_axis_number,
				},
			});
		} else {
			$chart.html(this.empty());
		}

		this.render_simple_table(
			$panel.find(".bkpi-top-customers").empty(),
			data.top_customers,
			[
				{ label: __("Customer"), value: (r) => r.customer_name || r.customer },
				{ label: __("Revenue"), value: (r) => format_currency(r.total, currency), right: true },
			]
		);

		this.render_simple_table(
			$panel.find(".bkpi-top-items").empty(),
			data.top_items,
			[
				{ label: __("Item"), value: (r) => r.item_name || r.item_code },
				{ label: __("Qty"), value: (r) => r.total_qty, right: true },
				{ label: __("Revenue"), value: (r) => format_currency(r.total_amount, currency), right: true },
			]
		);

		this.render_simple_table(
			$panel.find(".bkpi-revenue-by-company").empty(),
			data.revenue_by_company,
			[
				{ label: __("Company"), value: (r) => r.company },
				{ label: __("Revenue"), value: (r) => format_currency(r.total, currency), right: true },
			]
		);
	}

	// ------------------------------------------------------------------
	// Tab 2 — Financial Health
	// ------------------------------------------------------------------

	load_financial_health() {
		const $panel = this.body.find('[data-panel="financial"]');
		if (!$panel.find(".bkpi-initialized").length) {
			$panel.html(`
				<div class="bkpi-initialized"></div>
				<div class="row bkpi-cards bkpi-health-kpis"></div>
				<div class="row">
					<div class="col-md-6 bkpi-section">
						<div class="bkpi-section-title">${__("Receivables Aging")}</div>
						<div class="bkpi-receivables-aging"></div>
					</div>
					<div class="col-md-6 bkpi-section">
						<div class="bkpi-section-title">${__("Payables Aging")}</div>
						<div class="bkpi-payables-aging"></div>
					</div>
				</div>
				<div class="bkpi-section">
					<div class="bkpi-section-title">${__("Cash & Bank Balances")}</div>
					<div class="bkpi-cash-bank"></div>
				</div>
				<div class="bkpi-section">
					<div class="bkpi-section-title">${__("VAT Position (This Fiscal Year)")}</div>
					<div class="row bkpi-cards bkpi-vat-position"></div>
				</div>
				<div class="bkpi-section">
					<div class="bkpi-section-title">${__("Petty Cash Approved This Month")}</div>
					<div class="bkpi-petty-cash"></div>
				</div>
			`);
		}

		this.call("get_financial_health", $panel, (data) => this.render_financial_health($panel, data));
	}

	render_financial_health($panel, data) {
		const currency = this.currency();
		const cash_total = (data.cash_and_bank || []).reduce((sum, r) => sum + r.balance, 0);
		const outstanding_card = (label, block) =>
			block
				? {
						label,
						value: format_currency(block.total, currency),
						sub: __("Overdue: {0}", [format_currency(block.overdue, currency)]),
						alert: block.overdue > 0,
				  }
				: { label, value: "—", sub: __("No access") };

		this.render_cards($panel.find(".bkpi-health-kpis"), [
			outstanding_card(__("Receivables Outstanding"), data.receivables),
			outstanding_card(__("Payables Outstanding"), data.payables),
			{ label: __("Cash & Bank"), value: format_currency(cash_total, currency) },
		]);

		[
			[".bkpi-receivables-aging", data.receivables, __("No outstanding receivables")],
			[".bkpi-payables-aging", data.payables, __("No outstanding payables")],
		].forEach(([selector, block, empty_label]) => {
			const $aging = $panel.find(selector).empty();
			if (!block) {
				$aging.html(this.empty(__("No access")));
			} else if (block.aging.some((b) => b.amount)) {
				this.render_simple_table($aging, block.aging, [
					{ label: __("Days Overdue"), value: (r) => r.bucket },
					{ label: __("Amount"), value: (r) => format_currency(r.amount, currency), right: true },
				]);
			} else {
				$aging.html(this.empty(empty_label));
			}
		});

		this.render_simple_table($panel.find(".bkpi-cash-bank").empty(), data.cash_and_bank, [
			{ label: __("Company"), value: (r) => r.company },
			{ label: __("Account"), value: (r) => r.account },
			{ label: __("Balance"), value: (r) => format_currency(r.balance, currency), right: true },
		]);

		const $vat = $panel.find(".bkpi-vat-position").empty();
		if (data.vat_position && data.vat_position.length) {
			data.vat_position.forEach((row) => {
				let value = __("Unavailable");
				if (row.net_vat !== null) {
					value =
						row.net_vat < 0
							? `${__("Refund")} ${format_currency(Math.abs(row.net_vat), currency)}`
							: `${__("Payable")} ${format_currency(row.net_vat, currency)}`;
				}
				const warning = row.discrepancies
					? `<div class="bkpi-card-alert"><a href="/app/vat-dashboard">${__(
							"{0} ledger discrepancy(ies) — open VAT Dashboard",
							[row.discrepancies]
					  )}</a></div>`
					: "";
				$(`
					<div class="col-md-4">
						<div class="bkpi-card ${row.discrepancies ? "bkpi-alert" : ""}">
							<div class="bkpi-card-value">${value}</div>
							<div class="bkpi-card-label">${frappe.utils.escape_html(row.company)}</div>
							${warning}
						</div>
					</div>
				`).appendTo($vat);
			});
		} else {
			$vat.html(this.empty());
		}

		const $petty = $panel.find(".bkpi-petty-cash").empty();
		this.render_simple_table(
			$petty,
			data.petty_cash,
			[
				{ label: __("Company"), value: (r) => r.company },
				{ label: __("Approved This Month"), value: (r) => format_currency(r.total, currency), right: true },
			]
		);
	}

	// ------------------------------------------------------------------
	// Tab 3 — Commission & Payroll
	// ------------------------------------------------------------------

	load_commission_payroll() {
		const $panel = this.body.find('[data-panel="commission"]');
		if (!$panel.find(".bkpi-initialized").length) {
			$panel.html(`
				<div class="bkpi-initialized"></div>
				<div class="bkpi-section">
					<div class="row bkpi-cards bkpi-pending-count"></div>
				</div>
				<div class="bkpi-section">
					<div class="bkpi-section-title">${__("Commission This Month, by Company")}</div>
					<div class="bkpi-status-by-company"></div>
				</div>
				<div class="bkpi-section">
					<div class="bkpi-section-title">${__("Top 5 Salespeople (This Fiscal Year)")}</div>
					<div class="bkpi-top-salespeople"></div>
				</div>
			`);
		}

		this.call("get_commission_payroll", $panel, (data) => this.render_commission_payroll($panel, data));
	}

	render_commission_payroll($panel, data) {
		const currency = this.currency();

		this.render_cards($panel.find(".bkpi-pending-count"), [
			{
				label: __("Commission Entries Pending Approval"),
				value: `${data.pending_total}`,
				alert: data.pending_total > 0,
			},
			{ label: __("Approved, Not Yet Paid"), value: format_currency(data.approved_unpaid, currency) },
			{
				label: __("Outstanding Deductions"),
				value: format_currency(data.outstanding_deductions, currency),
				sub: __("Taken off the next payout"),
			},
		]);

		const $status = $panel.find(".bkpi-status-by-company").empty();
		if (data.status_by_company && data.status_by_company.length) {
			const by_company = {};
			data.status_by_company.forEach((row) => {
				by_company[row.company] = by_company[row.company] || {};
				by_company[row.company][row.status] = row.total;
			});
			const companies = Object.keys(by_company);
			const table = $(`
				<table class="table table-bordered">
					<thead>
						<tr>
							<th>${__("Company")}</th>
							<th class="text-right">${__("Accrued")}</th>
							<th class="text-right">${__("Approved")}</th>
							<th class="text-right">${__("Paid")}</th>
						</tr>
					</thead>
					<tbody></tbody>
				</table>
			`).appendTo($status);
			const $tbody = table.find("tbody");
			companies.forEach((company) => {
				const row = by_company[company];
				$(`
					<tr>
						<td>${frappe.utils.escape_html(company)}</td>
						<td class="text-right">${format_currency(row["Accrued"] || 0, currency)}</td>
						<td class="text-right">${format_currency(row["Approved"] || 0, currency)}</td>
						<td class="text-right">${format_currency(row["Paid"] || 0, currency)}</td>
					</tr>
				`).appendTo($tbody);
			});
		} else {
			$status.html(this.empty());
		}

		this.render_simple_table(
			$panel.find(".bkpi-top-salespeople").empty(),
			data.top_salespeople,
			[
				{ label: __("Commission Credited To"), value: (r) => r.commission_credited_to },
				{ label: __("Commission Earned"), value: (r) => format_currency(r.total, currency), right: true },
			]
		);
	}

	// ------------------------------------------------------------------
	// Shared helpers
	// ------------------------------------------------------------------

	// Each response carries the company's currency (or the system default for all companies).
	currency() {
		return this.response_currency || frappe.defaults.get_default("currency");
	}

	render_cards($el, cards) {
		$el.empty();
		const width = Math.max(3, Math.floor(12 / cards.length));
		cards.forEach((card) => {
			$(`
				<div class="col-md-${width} col-sm-6">
					<div class="bkpi-card ${card.alert ? "bkpi-alert" : ""}">
						<div class="bkpi-card-value">${card.value}</div>
						<div class="bkpi-card-label">${card.label}</div>
						${card.sub ? `<div class="bkpi-card-sub">${card.sub}</div>` : ""}
					</div>
				</div>
			`).appendTo($el);
		});
	}

	render_simple_table($el, rows, columns) {
		if (!rows || !rows.length) {
			$el.html(this.empty());
			return;
		}

		const table = $(`
			<div class="bkpi-table-wrapper">
				<table class="table table-bordered">
					<thead>
						<tr>
							${columns.map((c) => `<th class="${c.right ? "text-right" : ""}">${c.label}</th>`).join("")}
						</tr>
					</thead>
					<tbody></tbody>
				</table>
			</div>
		`).appendTo($el);
		const $tbody = table.find("tbody");

		rows.forEach((row) => {
			const $tr = $("<tr></tr>").appendTo($tbody);
			columns.forEach((c) => {
				const raw = c.value(row);
				const cell = c.right ? raw : frappe.utils.escape_html(raw == null ? "" : String(raw));
				$(`<td class="${c.right ? "text-right" : ""}">${cell}</td>`).appendTo($tr);
			});
		});
	}
};
