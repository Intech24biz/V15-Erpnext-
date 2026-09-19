frappe.provide("blueline");

frappe.pages["coa-console"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("COA Configuration Console"),
		single_column: true,
	});

	wrapper.coa_console = new blueline.CoaConsole(page);
};

blueline.CoaConsole = class CoaConsole {
	constructor(page) {
		this.page = page;
		this.setup_actions();
		this.setup_body();
		this.refresh();
	}

	setup_actions() {
		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
	}

	setup_body() {
		if (!document.getElementById("coac-style")) {
			$(`<style id="coac-style">
				.coa-console { padding: 15px 0; }
				.coa-console .coac-panel-col { margin-bottom: 20px; }
				.coa-console .coac-panel {
					--coac-accent: #5e64ff;
					background: var(--card-bg, var(--fg-color));
					border: 1px solid var(--border-color);
					border-top: 4px solid var(--coac-accent);
					border-radius: var(--border-radius-md, 6px);
					height: 100%;
				}
				.coa-console .coac-panel-header {
					display: flex;
					align-items: center;
					justify-content: space-between;
					gap: 10px;
					padding: 12px 15px;
					background: color-mix(in srgb, var(--coac-accent) 10%, transparent);
					border-bottom: 1px solid var(--border-color);
				}
				.coa-console .coac-company-name {
					font-size: 16px;
					font-weight: 600;
					color: var(--text-color);
					word-break: break-word;
				}
				.coa-console .coac-badge {
					flex-shrink: 0;
					font-size: 11px;
					font-weight: 600;
					text-transform: uppercase;
					padding: 3px 8px;
					border-radius: 10px;
				}
				.coa-console .coac-badge-editable {
					background: var(--bg-green, #e4f5e9);
					color: var(--text-on-green, #2f7a4d);
				}
				.coa-console .coac-badge-readonly {
					background: var(--bg-gray, #f3f3f3);
					color: var(--text-on-gray, #6c7680);
				}
				.coa-console .coac-panel-body { padding: 5px 15px 10px; }
				.coa-console .coac-section { padding: 10px 0; }
				.coa-console .coac-section + .coac-section { border-top: 1px dashed var(--border-color); }
				.coa-console .coac-section-title {
					font-size: 12px;
					font-weight: 600;
					text-transform: uppercase;
					color: var(--coac-accent);
					margin-bottom: 6px;
				}
				.coa-console .coac-field {
					display: flex;
					justify-content: space-between;
					gap: 15px;
					padding: 3px 0;
				}
				.coa-console .coac-field-label {
					flex: 0 0 42%;
					color: var(--text-muted);
					font-size: 12px;
				}
				.coa-console .coac-field-value {
					flex: 1;
					text-align: right;
					color: var(--text-color);
					word-break: break-word;
				}
				.coa-console .coac-field-edit { align-items: center; padding: 4px 0; }
				.coa-console .coac-field-control { flex: 1; min-width: 0; }
				.coa-console .coac-field-control .frappe-control,
				.coa-console .coac-field-control .form-group {
					max-width: none;
					margin-bottom: 0;
				}
				.coa-console .coac-panel-footer {
					padding: 10px 15px;
					text-align: right;
					border-top: 1px solid var(--border-color);
				}
				.coa-console .coac-not-set { color: var(--text-muted); font-style: italic; }
				.coa-console .coac-empty {
					text-align: center;
					padding: 50px 15px;
					color: var(--text-muted);
				}
			</style>`).appendTo("head");
		}

		this.body = $(`
			<div class="coa-console">
				<div class="row coac-panels"></div>
			</div>
		`).appendTo(this.page.body);
	}

	refresh() {
		const me = this;
		frappe.call({
			method: "blueline.blueline.page.coa_console.coa_console.get_configurations",
			freeze: true,
			callback(r) {
				if (r.message) {
					me.render(r.message);
				}
			},
		});
	}

	render(data) {
		this.render_access_indicator(data.can_write_any);

		const configurations = data.configurations || [];
		const $panels = this.body.find(".coac-panels").empty();

		if (!configurations.length) {
			$panels.html(`
				<div class="col-md-12">
					<div class="coac-empty">${__("No COA configurations available to you")}</div>
				</div>
			`);
			return;
		}

		configurations.forEach((config, index) => {
			this.add_panel($panels, config, index);
		});
	}

	add_panel($container, config, index) {
		const $panel = $(this.get_panel_html(config, index).trim()).appendTo($container);
		if (config.can_write) {
			this.setup_edit_controls($panel, config, index);
		}
		return $panel;
	}

	replace_panel($panel, config, index) {
		const $new_panel = $(this.get_panel_html(config, index).trim());
		$panel.replaceWith($new_panel);
		if (config.can_write) {
			this.setup_edit_controls($new_panel, config, index);
		}
	}

	render_access_indicator(can_write_any) {
		this.page.set_indicator(
			can_write_any ? __("Edit access") : __("View only"),
			can_write_any ? "green" : "gray"
		);
	}

	get_panel_html(config, index) {
		const accents = blueline.CoaConsole.ACCENTS;
		const accent = accents[index % accents.length];
		const badge = config.can_write
			? `<span class="coac-badge coac-badge-editable">${__("Editable")}</span>`
			: `<span class="coac-badge coac-badge-readonly">${__("Read-only")}</span>`;

		const editable = Boolean(config.can_write);
		const sections = blueline.CoaConsole.SECTIONS.map(
			(section) => `
				<div class="coac-section">
					<div class="coac-section-title">${__(section.title)}</div>
					${section.fields
						.map((field) =>
							editable ? this.get_edit_field_html(field) : this.get_field_html(config, field)
						)
						.join("")}
				</div>
			`
		).join("");

		const footer = editable
			? `<div class="coac-panel-footer">
					<button type="button" class="btn btn-primary btn-sm coac-save-btn">${__("Save")}</button>
				</div>`
			: "";

		return `
			<div class="col-lg-6 col-md-12 coac-panel-col">
				<div class="coac-panel" style="--coac-accent: ${accent}">
					<div class="coac-panel-header">
						<div class="coac-company-name">${frappe.utils.escape_html(config.company || config.name)}</div>
						${badge}
					</div>
					<div class="coac-panel-body">${sections}</div>
					${footer}
				</div>
			</div>
		`;
	}

	get_edit_field_html(field) {
		return `
			<div class="coac-field coac-field-edit">
				<span class="coac-field-label">${__(field.label)}</span>
				<div class="coac-field-control" data-fieldname="${field.fieldname}"></div>
			</div>
		`;
	}

	get_control_df(field, company) {
		const df = {
			fieldname: field.fieldname,
			label: field.label,
			fieldtype: field.fieldtype,
			options: field.options,
		};

		if (field.fieldtype === "Link") {
			// Same filters as the doctype form's set_query: this company only, and leaf
			// accounts only. only_select hides the "Create a new ..." option in the picker.
			const filters = { company: company };
			if (field.options === "Account") {
				filters.is_group = 0;
			}
			df.only_select = 1;
			df.get_query = () => ({ filters: filters });
		}

		return df;
	}

	setup_edit_controls($panel, config, index) {
		const controls = {};

		blueline.CoaConsole.SECTIONS.forEach((section) => {
			section.fields.forEach((field) => {
				const $parent = $panel.find(`.coac-field-control[data-fieldname="${field.fieldname}"]`);
				const control = frappe.ui.form.make_control({
					df: this.get_control_df(field, config.company),
					parent: $parent,
					only_input: true,
					render_input: true,
				});
				control.set_input(config[field.fieldname] || "");
				controls[field.fieldname] = control;
			});
		});

		$panel.find(".coac-save-btn").on("click", () => this.save_panel($panel, config, index, controls));
	}

	save_panel($panel, config, index, controls) {
		const values = {};
		Object.keys(controls).forEach((fieldname) => {
			values[fieldname] = controls[fieldname].get_value() || "";
		});

		const $button = $panel.find(".coac-save-btn").prop("disabled", true);

		frappe.call({
			method: "blueline.blueline.page.coa_console.coa_console.save_configuration",
			type: "POST",
			args: { company: config.name, values: values },
			callback: (r) => {
				const result = r.message || {};
				if (result.ok) {
					frappe.show_alert({ message: result.message, indicator: "green" });
					this.replace_panel($panel, result.configuration, index);
				} else {
					frappe.show_alert(
						{
							message: frappe.utils.escape_html(result.message || __("Could not save")),
							indicator: "red",
						},
						10
					);
					$button.prop("disabled", false);
				}
			},
			error: () => $button.prop("disabled", false),
		});
	}

	get_field_html(config, field) {
		const raw = config[field.fieldname];
		let value = `<span class="coac-not-set">${__("Not set")}</span>`;

		if (raw) {
			const text = field.type === "date" ? frappe.datetime.str_to_user(raw) : raw;
			value = frappe.utils.escape_html(text);
		}

		return `
			<div class="coac-field">
				<span class="coac-field-label">${__(field.label)}</span>
				<span class="coac-field-value">${value}</span>
			</div>
		`;
	}
};

blueline.CoaConsole.ACCENTS = ["#5e64ff", "#28a745", "#ffa00a", "#ff5858", "#743ee2", "#00b0af", "#7cd6fd"];

blueline.CoaConsole.SECTIONS = [
	{
		title: "Financial & Balancing",
		fields: [
			{ fieldname: "default_cash_account", label: "Default Cash Account", fieldtype: "Link", options: "Account" },
			{ fieldname: "default_bank_account", label: "Default Bank Account", fieldtype: "Link", options: "Account" },
			{
				fieldname: "temporary_opening_account",
				label: "Temporary Opening Account",
				fieldtype: "Link",
				options: "Account",
			},
			{ fieldname: "default_cost_center", label: "Default Cost Center", fieldtype: "Link", options: "Cost Center" },
		],
	},
	{
		title: "Stock & Valuation",
		fields: [
			{
				fieldname: "stock_adjustment_account",
				label: "Stock Adjustment Account",
				fieldtype: "Link",
				options: "Account",
			},
			{
				fieldname: "stock_received_but_not_billed",
				label: "Stock Received But Not Billed",
				fieldtype: "Link",
				options: "Account",
			},
			{
				fieldname: "expenses_included_in_valuation",
				label: "Expenses Included In Valuation",
				fieldtype: "Link",
				options: "Account",
			},
			{
				fieldname: "default_valuation_method",
				label: "Default Valuation Method",
				fieldtype: "Select",
				options: "FIFO\nMoving Average",
			},
			{ fieldname: "default_warehouse", label: "Default Warehouse", fieldtype: "Link", options: "Warehouse" },
		],
	},
	{
		title: "Multi-Currency",
		fields: [
			{
				fieldname: "exchange_gain_loss_account",
				label: "Exchange Gain/Loss Account",
				fieldtype: "Link",
				options: "Account",
			},
			{
				fieldname: "foreign_currency_revaluation_account",
				label: "Foreign Currency Revaluation Account",
				fieldtype: "Link",
				options: "Account",
			},
			{
				fieldname: "inter_company_clearing_account",
				label: "Inter Company Clearing Account",
				fieldtype: "Link",
				options: "Account",
			},
		],
	},
	{
		title: "Guardrail",
		fields: [
			{
				fieldname: "earliest_allowed_posting_date",
				label: "Earliest Allowed Posting Date",
				type: "date",
				fieldtype: "Date",
			},
		],
	},
];
