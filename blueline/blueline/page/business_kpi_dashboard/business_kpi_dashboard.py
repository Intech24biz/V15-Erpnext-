import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, nowdate

from erpnext.accounts.utils import get_fiscal_year

# Reused, not duplicated, per the task: VAT Dashboard's own net-position query.
# get_vat_data is a plain function underneath @frappe.whitelist(), so calling it
# in-process here is safe — if its logic ever changes, this dashboard picks that
# up automatically instead of drifting out of sync with a copy.
from blueline.blueline.page.vat_dashboard.vat_dashboard import get_vat_data

SALES_INVOICE_DT = "Sales Invoice"
SALES_INVOICE_ITEM_DT = "Sales Invoice Item"
PETTY_CASH_DT = "Petty Cash Voucher"
COMMISSION_ENTRY_DT = "Sales Commission Entry"

COMMISSION_STATUSES = ("Accrued", "Payment Received - Pending Approval", "Approved", "Paid")
# "Commission earned" reads as confirmed, not just accrued-and-unreviewed.
EARNED_STATUSES = ("Approved", "Paid")
PENDING_APPROVAL_STATUS = "Payment Received - Pending Approval"

AGING_BUCKET_LABELS = ("Not Due", "0-30", "31-60", "61-90", "90+")


def _check_permission(doctype):
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not permitted to view {0}").format(_(doctype)), frappe.PermissionError)


def _company_filter(company):
	return {"company": company} if company else {}


def _permitted_companies(company=None):
	# get_list, not get_all: every per-company breakdown below is driven off this
	# list, so it has to already be scoped to what the current user can see —
	# same rule as the rest of this app (COA Configuration, Sales Commission Rule).
	filters = {"name": company} if company else {}
	return frappe.get_list("Company", filters=filters, pluck="name")


def _fiscal_year_range(company):
	try:
		_, start, end = get_fiscal_year(getdate(nowdate()), company=company, verbose=0)
		return getdate(start), getdate(end)
	except Exception:
		# Degrade gracefully rather than erroring the whole tab if Fiscal Year
		# setup is incomplete for a company — plain calendar year instead.
		today = getdate(nowdate())
		return getdate(f"{today.year}-01-01"), getdate(f"{today.year}-12-31")


# ---------------------------------------------------------------------------
# Tab 1 — Sales Performance
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_sales_performance(company=None):
	_check_permission(SALES_INVOICE_DT)

	trend_filters = {
		"docstatus": 1,
		"posting_date": [">=", add_months(nowdate(), -12)],
		**_company_filter(company),
	}
	trend = frappe.get_list(
		SALES_INVOICE_DT,
		filters=trend_filters,
		fields=["DATE_FORMAT(posting_date, '%Y-%m') as month", "sum(grand_total) as total"],
		group_by="month",
		order_by="month asc",
	)

	fy_start, fy_end = _fiscal_year_range(company)
	fy_filters = {
		"docstatus": 1,
		"posting_date": ["between", [fy_start, fy_end]],
		**_company_filter(company),
	}

	top_customers = frappe.get_list(
		SALES_INVOICE_DT,
		filters=fy_filters,
		fields=["customer", "customer_name", "sum(grand_total) as total"],
		group_by="customer",
		order_by="total desc",
		limit_page_length=10,
	)

	# Sales Invoice Item has no company/posting_date of its own, so the invoices
	# are resolved first (via the same permission-scoped filters as everything
	# else here) and the item query is then scoped to exactly that parent set —
	# the permission boundary is established by this first call, not the second.
	#
	# The second call uses get_all, not get_list: Sales Invoice Item's own
	# `permissions` list is empty (confirmed against this site's metadata), which
	# is normal for a child table — it's only ever meant to be read as part of its
	# parent, not queried standalone, so frappe.has_permission("Sales Invoice
	# Item", "read") is False for every role except Administrator. get_list would
	# therefore throw PermissionError for every real user. That's safe to bypass
	# here specifically because the parent filter is already an exact, vetted set
	# from the get_list call above — nothing beyond what that already permitted.
	invoice_names = frappe.get_list(SALES_INVOICE_DT, filters=fy_filters, pluck="name", limit_page_length=0)
	top_items = []
	if invoice_names:
		top_items = frappe.get_all(
			SALES_INVOICE_ITEM_DT,
			filters={"parent": ["in", invoice_names], "parenttype": SALES_INVOICE_DT, "docstatus": 1},
			fields=["item_code", "item_name", "sum(qty) as total_qty", "sum(amount) as total_amount"],
			group_by="item_code",
			order_by="total_amount desc",
			limit_page_length=10,
		)

	revenue_by_company = frappe.get_list(
		SALES_INVOICE_DT,
		filters=fy_filters,
		fields=["company", "sum(grand_total) as total"],
		group_by="company",
		order_by="total desc",
	)

	return {
		"trend": trend,
		"top_customers": top_customers,
		"top_items": top_items,
		"revenue_by_company": revenue_by_company,
		"fiscal_year_range": [str(fy_start), str(fy_end)],
	}


# ---------------------------------------------------------------------------
# Tab 2 — Financial Health
# ---------------------------------------------------------------------------


def _aging_bucket(due_date, today):
	if not due_date:
		return "Not Due"
	days_overdue = (today - getdate(due_date)).days
	if days_overdue <= 0:
		return "Not Due"
	if days_overdue <= 30:
		return "0-30"
	if days_overdue <= 60:
		return "31-60"
	if days_overdue <= 90:
		return "61-90"
	return "90+"


def _get_receivables(company):
	rows = frappe.get_list(
		SALES_INVOICE_DT,
		filters={"docstatus": 1, "outstanding_amount": [">", 0], **_company_filter(company)},
		fields=["name", "due_date", "outstanding_amount"],
		limit_page_length=0,
	)

	today = getdate(nowdate())
	aging = {label: 0.0 for label in AGING_BUCKET_LABELS}
	total = 0.0
	for row in rows:
		bucket = _aging_bucket(row.due_date, today)
		amount = flt(row.outstanding_amount)
		aging[bucket] += amount
		total += amount

	return {
		"total": flt(total, 2),
		"aging": [{"bucket": label, "amount": flt(aging[label], 2)} for label in AGING_BUCKET_LABELS],
	}


def _get_vat_position(companies):
	position = []
	for company in companies:
		try:
			data = get_vat_data(company)
			position.append({"company": company, "net_vat": data["summary"]["net_vat"]})
		except Exception:
			# A company with no VAT accounts configured shouldn't blank the whole
			# tab — surface it as unavailable for that one company instead.
			frappe.log_error(
				title=f"KPI dashboard: VAT position unavailable for {company}",
				message=frappe.get_traceback(),
			)
			position.append({"company": company, "net_vat": None})
	return position


def _get_petty_cash(company):
	month_start = get_first_day(nowdate())
	month_end = get_last_day(nowdate())
	return frappe.get_list(
		PETTY_CASH_DT,
		filters={
			"docstatus": 1,
			"posting_date": ["between", [month_start, month_end]],
			**_company_filter(company),
		},
		fields=["company", "sum(amount) as total"],
		group_by="company",
		order_by="total desc",
	)


@frappe.whitelist()
def get_financial_health(company=None):
	_check_permission(SALES_INVOICE_DT)

	companies = _permitted_companies(company)

	return {
		"receivables": _get_receivables(company),
		"vat_position": _get_vat_position(companies),
		"petty_cash": _get_petty_cash(company),
	}


# ---------------------------------------------------------------------------
# Tab 3 — Commission & Payroll
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_commission_payroll(company=None):
	_check_permission(COMMISSION_ENTRY_DT)

	month_start = get_first_day(nowdate())
	month_end = get_last_day(nowdate())

	status_by_company = frappe.get_list(
		COMMISSION_ENTRY_DT,
		filters={
			"posting_date": ["between", [month_start, month_end]],
			"status": ["in", COMMISSION_STATUSES],
			**_company_filter(company),
		},
		fields=["company", "status", "sum(commission_amount) as total"],
		group_by="company, status",
	)

	fy_start, fy_end = _fiscal_year_range(company)
	top_salespeople = frappe.get_list(
		COMMISSION_ENTRY_DT,
		filters={
			"posting_date": ["between", [fy_start, fy_end]],
			"status": ["in", EARNED_STATUSES],
			**_company_filter(company),
		},
		fields=["sales_person", "sum(commission_amount) as total"],
		group_by="sales_person",
		order_by="total desc",
		limit_page_length=5,
	)

	pending_by_company = frappe.get_list(
		COMMISSION_ENTRY_DT,
		filters={"status": PENDING_APPROVAL_STATUS, **_company_filter(company)},
		fields=["company", "count(name) as count"],
		group_by="company",
	)
	pending_total = sum(row.count for row in pending_by_company)

	return {
		"status_by_company": status_by_company,
		"top_salespeople": top_salespeople,
		"pending_by_company": pending_by_company,
		"pending_total": pending_total,
		"fiscal_year_range": [str(fy_start), str(fy_end)],
	}
