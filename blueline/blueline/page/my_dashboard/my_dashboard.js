frappe.provide("blueline");

frappe.pages["my-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("My Dashboard"),
		single_column: true,
	});

	wrapper.my_dashboard = new blueline.MyDashboard(page);
};

frappe.pages["my-dashboard"].on_page_show = function (wrapper) {
	// Approvals change all day; reload whenever the page is opened again.
	if (wrapper.my_dashboard) {
		wrapper.my_dashboard.refresh();
	}
};

blueline.MyDashboard = class MyDashboard {
	constructor(page) {
		this.page = page;
		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.setup_body();
	}

	setup_body() {
		if (!document.getElementById("mydash-style")) {
			$(`<style id="mydash-style">
				.mydash { padding: 15px 0; }
				.mydash .mydash-section { margin-bottom: 25px; }
				.mydash .mydash-section-title { font-weight: 600; margin-bottom: 10px; color: var(--text-color); }
				.mydash .mydash-card {
					background: var(--card-bg, var(--fg-color));
					border: 1px solid var(--border-color);
					border-radius: var(--border-radius-md, 6px);
					padding: 15px;
					text-align: center;
					margin-bottom: 15px;
				}
				.mydash .mydash-card.mydash-alert { border-top: 4px solid var(--red-500, #ff5858); }
				.mydash .mydash-card-value { font-size: 22px; font-weight: 600; color: var(--text-color); }
				.mydash .mydash-card-label {
					font-size: 12px;
					color: var(--text-muted);
					margin-top: 4px;
					text-transform: uppercase;
				}
				.mydash .mydash-empty { color: var(--text-muted); padding: 10px 0; }
				.mydash .mydash-note { font-size: 12px; color: var(--text-muted); }
				.mydash .mydash-table-wrapper { overflow-x: auto; }
			</style>`).appendTo("head");
		}
		this.body = $(`<div class="mydash"></div>`).appendTo(this.page.body);
	}

	refresh() {
		frappe.call({
			method: "blueline.blueline.page.my_dashboard.my_dashboard.get_my_dashboard",
			callback: (r) => r.message && this.render(r.message),
		});
	}

	render(data) {
		const currency = data.currency;
		this.body.empty();

		const draft_total = data.drafts.reduce((sum, d) => sum + d.count, 0);
		this.cards([
			{ label: __("Waiting for My Approval"), value: data.waiting_for_me.length, alert: data.waiting_for_me.length > 0 },
			{ label: __("Sent by Me, Still Waiting"), value: data.sent_by_me.length },
			{ label: __("My Drafts"), value: draft_total },
		]);

		this.section(__("Waiting for my approval"), () =>
			this.doc_table(data.waiting_for_me, currency, __("Nothing is waiting for your approval."), true)
		);
		this.section(__("Sent by me, waiting for approval"), () =>
			this.doc_table(data.sent_by_me, currency, __("Nothing you sent is waiting."))
		);
		if (data.drafts.length) {
			this.section(__("My drafts"), () =>
				this.table(
					data.drafts,
					[
						{
							label: __("Document Type"),
							html: (r) =>
								`<a href="/app/${frappe.router.slug(r.doctype)}?owner=${encodeURIComponent(
									data.user
								)}&docstatus=0">${__(r.doctype)}</a>`,
						},
						{ label: __("Drafts"), html: (r) => `${r.count}`, right: true },
					]
				)
			);
		}

		if (data.quotations) {
			this.section(__("My quotations"), () =>
				this.cards_html([
					{
						label: __("Submitted This Month"),
						value: `${data.quotations.this_month.count} · ${format_currency(data.quotations.this_month.value, currency)}`,
					},
					{
						label: __("Open (Not Yet Ordered)"),
						value: `${data.quotations.open.count} · ${format_currency(data.quotations.open.value, currency)}`,
					},
				])
			);
		}

		this.section(__("My sales and commission"), () => {
			if (!data.sales_persons.length) {
				return `<div class="mydash-note">${__(
					"Your user isn't linked to a Sales Person. Ask an administrator to set your User ID on your Employee record and that Employee on your Sales Person."
				)}</div>`;
			}
			const sales = this.cards_html([
				{ label: __("My Net Sales This Month"), value: format_currency(data.sales.this_month, currency) },
				{ label: __("My Net Sales Fiscal Year to Date"), value: format_currency(data.sales.fy_to_date, currency) },
			]);
			const commission = this.table(data.commission, [
				{ label: __("Commission (This Fiscal Year)"), html: (r) => __(r.status) },
				{ label: __("Amount"), html: (r) => format_currency(r.amount, currency), right: true },
			]);
			return `${sales}<div class="mydash-note">${__("Sales Person: {0}", [
				data.sales_persons.map((p) => frappe.utils.escape_html(p)).join(", "),
			])}</div>${commission}`;
		});
	}

	section(title, content_fn) {
		$(`
			<div class="mydash-section">
				<div class="mydash-section-title">${title}</div>
				${content_fn()}
			</div>
		`).appendTo(this.body);
	}

	cards(cards) {
		$(this.cards_html(cards)).appendTo(this.body);
	}

	cards_html(cards) {
		const width = Math.max(3, Math.floor(12 / cards.length));
		return `<div class="row">${cards
			.map(
				(c) => `
				<div class="col-md-${width} col-sm-6">
					<div class="mydash-card ${c.alert ? "mydash-alert" : ""}">
						<div class="mydash-card-value">${c.value}</div>
						<div class="mydash-card-label">${c.label}</div>
					</div>
				</div>`
			)
			.join("")}</div>`;
	}

	doc_table(rows, currency, empty_label, show_sender) {
		if (!rows.length) {
			return `<div class="mydash-empty">${empty_label}</div>`;
		}
		const columns = [
			{ label: __("Type"), html: (r) => __(r.doctype) },
			{
				label: __("Document"),
				html: (r) =>
					`<a href="/app/${frappe.router.slug(r.doctype)}/${encodeURIComponent(r.name)}">${frappe.utils.escape_html(
						r.name
					)}</a>`,
			},
			{ label: __("Party / Purpose"), html: (r) => frappe.utils.escape_html(r.party || "") },
			{ label: __("Company"), html: (r) => frappe.utils.escape_html(r.company || "") },
		];
		if (show_sender) {
			columns.push({ label: __("Sent By"), html: (r) => frappe.utils.escape_html(r.sent_by || r.owner || "") });
		}
		columns.push(
			{ label: __("Waiting Since"), html: (r) => frappe.datetime.comment_when(r.modified) },
			{ label: __("Amount"), html: (r) => format_currency(r.amount, currency), right: true }
		);
		return this.table(rows, columns);
	}

	table(rows, columns) {
		return `
			<div class="mydash-table-wrapper">
				<table class="table table-bordered">
					<thead><tr>${columns
						.map((c) => `<th class="${c.right ? "text-right" : ""}">${c.label}</th>`)
						.join("")}</tr></thead>
					<tbody>${rows
						.map(
							(r) =>
								`<tr>${columns
									.map((c) => `<td class="${c.right ? "text-right" : ""}">${c.html(r)}</td>`)
									.join("")}</tr>`
						)
						.join("")}</tbody>
				</table>
			</div>`;
	}
};
