"""Management dashboard: sales performance, financial health and commission, per company or
for every company the user can see. Management roles only (also enforced here, not just on
the Page). Amounts are in company currency; sales are net of VAT (base_net_total)."""

import frappe
from frappe import _
from frappe.utils import add_months, add_years, flt, get_first_day, get_last_day, getdate, nowdate

from erpnext.accounts.utils import get_fiscal_year

# Reused, not duplicated: the VAT Dashboard's own figures and discrepancy check.
from blueline.blueline.page.vat_dashboard.vat_dashboard import get_vat_data

# Not ERPNext's Accounts Manager: on this site it is also held by sales staff.
MANAGEMENT_ROLES = {"System Manager", "GI Management", "Financial Manager"}

SALES_INVOICE_DT = "Sales Invoice"
SALES_INVOICE_ITEM_DT = "Sales Invoice Item"
PURCHASE_INVOICE_DT = "Purchase Invoice"
QUOTATION_DT = "Quotation"
PETTY_CASH_DT = "Petty Cash Voucher"
COMMISSION_ENTRY_DT = "Sales Commission Entry"

COMMISSION_TYPE = "Commission"
DEDUCTION_TYPE = "Deduction"
COMMISSION_STATUSES = ("Accrued", "Payment Received - Pending Approval", "Approved", "Paid")
# "Commission earned" reads as confirmed, not just accrued-and-unreviewed.
EARNED_STATUSES = ("Approved", "Paid")
PENDING_APPROVAL_STATUS = "Payment Received - Pending Approval"
SETTLED_DEDUCTION_STATUSES = ("Paid", "Cancelled")
CONVERTED_QUOTATION_STATUSES = ("Ordered", "Partially Ordered")

AGING_BUCKET_LABELS = ("Not Due", "0-30", "31-60", "61-90", "90+")


def check_management():
	if frappe.session.user == "Administrator" or MANAGEMENT_ROLES & set(frappe.get_roles()):
		return
	frappe.throw(_("The Business KPI Dashboard is for management roles only."), frappe.PermissionError)


def _readable(doctype):
	# Each figure also respects the user's own read access: a section they can't read comes
	# back as None (shown as "no access") instead of failing the whole tab.
	return frappe.has_permission(doctype, "read")


def _company_filter(company):
	return {"company": company} if company else {}


def _permitted_companies(company=None):
	# get_list, not get_all: every per-company figure is scoped to what the user can see
	# (Company User Permissions), same rule as the rest of this app.
	filters = {"name": company} if company else {}
	return frappe.get_list("Company", filters=filters, pluck="name")


def _fiscal_year_range(company, date=None):
	date = getdate(date or nowdate())
	try:
		_, start, end = get_fiscal_year(date, company=company, verbose=0)
		return getdate(start), getdate(end)
	except Exception:
		# Fiscal Year setup incomplete for this company: plain calendar year instead.
		return getdate(f"{date.year}-01-01"), getdate(f"{date.year}-12-31")


def _currency(company):
	if company:
		return frappe.get_cached_value("Company", company, "default_currency")
	return frappe.db.get_default("currency")


def _sum(doctype, field, filters):
	rows = frappe.get_list(doctype, filters=filters, fields=[f"sum({field}) as total"])
	return flt(rows[0].total if rows else 0, 2)


# ---------------------------------------------------------------------------
# Tab 1 — Sales Performance
# ---------------------------------------------------------------------------


def _net_sales(company, start, end):
	# Credit Notes (is_return) carry negative totals, so they net off here.
	return _sum(
		SALES_INVOICE_DT,
		"base_net_total",
		{"docstatus": 1, "posting_date": ["between", [start, end]], **_company_filter(company)},
	)


def _quotation_kpis(company, start, end):
	if not _readable(QUOTATION_DT):
		return None
	filters = {"docstatus": 1, "transaction_date": ["between", [start, end]], **_company_filter(company)}
	rows = frappe.get_list(
		QUOTATION_DT,
		filters=filters,
		fields=["status", "count(name) as count", "sum(base_net_total) as total"],
		group_by="status",
	)
	count = sum(r.count for r in rows)
	converted = sum(r.count for r in rows if r.status in CONVERTED_QUOTATION_STATUSES)
	return {
		"count": count,
		"value": flt(sum(flt(r.total) for r in rows), 2),
		"converted": converted,
		"conversion_rate": flt(converted * 100.0 / count, 1) if count else 0.0,
		"open_value": flt(sum(flt(r.total) for r in rows if r.status == "Open"), 2),
	}


@frappe.whitelist()
def get_sales_performance(company=None):
	check_management()
	frappe.has_permission(SALES_INVOICE_DT, "read", throw=True)

	today = getdate(nowdate())
	fy_start, fy_end = _fiscal_year_range(company)

	kpis = {
		"this_month": _net_sales(company, get_first_day(today), today),
		"last_month": _net_sales(
			company, get_first_day(add_months(today, -1)), get_last_day(add_months(today, -1))
		),
		"fy_to_date": _net_sales(company, fy_start, today),
		"last_fy_to_date": _net_sales(company, add_years(fy_start, -1), add_years(today, -1)),
		"quotations": _quotation_kpis(company, fy_start, today),
	}

	trend = frappe.get_list(
		SALES_INVOICE_DT,
		filters={
			"docstatus": 1,
			"posting_date": [">=", get_first_day(add_months(today, -11))],
			**_company_filter(company),
		},
		fields=["DATE_FORMAT(posting_date, '%Y-%m') as month", "sum(base_net_total) as total"],
		group_by="month",
		order_by="month asc",
	)

	fy_filters = {"docstatus": 1, "posting_date": ["between", [fy_start, fy_end]], **_company_filter(company)}
	top_customers = frappe.get_list(
		SALES_INVOICE_DT,
		filters=fy_filters,
		fields=["customer", "customer_name", "sum(base_net_total) as total"],
		group_by="customer",
		order_by="total desc",
		limit_page_length=10,
	)

	# Sales Invoice Item has no permissions of its own (a child table is read through its
	# parent), so get_list on it fails for every real user. The parent set comes from a
	# permission-checked get_list first; the item query is limited to exactly that set.
	invoice_names = frappe.get_list(SALES_INVOICE_DT, filters=fy_filters, pluck="name", limit_page_length=0)
	top_items = []
	if invoice_names:
		top_items = frappe.get_all(
			SALES_INVOICE_ITEM_DT,
			filters={"parent": ["in", invoice_names], "parenttype": SALES_INVOICE_DT, "docstatus": 1},
			fields=["item_code", "item_name", "sum(qty) as total_qty", "sum(base_net_amount) as total_amount"],
			group_by="item_code",
			order_by="total_amount desc",
			limit_page_length=10,
		)

	revenue_by_company = frappe.get_list(
		SALES_INVOICE_DT,
		filters=fy_filters,
		fields=["company", "sum(base_net_total) as total"],
		group_by="company",
		order_by="total desc",
	)

	return {
		"kpis": kpis,
		"trend": trend,
		"top_customers": top_customers,
		"top_items": top_items,
		"revenue_by_company": revenue_by_company,
		"fiscal_year_range": [str(fy_start), str(fy_end)],
		"currency": _currency(company),
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


def _outstanding(doctype, company):
	if not _readable(doctype):
		return None
	rows = frappe.get_list(
		doctype,
		filters={"docstatus": 1, "outstanding_amount": [">", 0], **_company_filter(company)},
		fields=["due_date", "outstanding_amount", "conversion_rate"],
		limit_page_length=0,
	)
	today = getdate(nowdate())
	aging = {label: 0.0 for label in AGING_BUCKET_LABELS}
	for row in rows:
		# outstanding_amount is in the invoice currency; convert to company currency.
		aging[_aging_bucket(row.due_date, today)] += flt(row.outstanding_amount) * flt(row.conversion_rate or 1)
	total = sum(aging.values())
	return {
		"total": flt(total, 2),
		"overdue": flt(total - aging["Not Due"], 2),
		"count": len(rows),
		"aging": [{"bucket": label, "amount": flt(aging[label], 2)} for label in AGING_BUCKET_LABELS],
	}


def _cash_and_bank(companies):
	if not companies or not _readable("Account"):
		return []
	# Only the Cash / Bank accounts the user may see; balances read from the GL.
	accounts = frappe.get_list(
		"Account",
		filters={"company": ["in", companies], "account_type": ["in", ["Cash", "Bank"]], "is_group": 0},
		pluck="name",
		limit_page_length=0,
	)
	if not accounts:
		return []
	return frappe.db.sql(
		"""select company, account, sum(debit) - sum(credit) as balance
		from `tabGL Entry`
		where is_cancelled = 0 and account in %(accounts)s
		group by company, account
		having abs(balance) > 0.005
		order by company, balance desc""",
		{"accounts": accounts},
		as_dict=True,
	)


def _vat_position(companies):
	position = []
	for company in companies:
		fy_start, fy_end = _fiscal_year_range(company)
		try:
			data = get_vat_data(company, fy_start, fy_end)
			position.append(
				{
					"company": company,
					"net_vat": data["summary"]["net_vat"],
					"discrepancies": len(data.get("discrepancies") or []),
				}
			)
		except Exception:
			# A company with no VAT accounts configured shouldn't blank the whole tab.
			frappe.log_error(
				title=f"KPI dashboard: VAT position unavailable for {company}", message=frappe.get_traceback()
			)
			position.append({"company": company, "net_vat": None, "discrepancies": 0})
	return position


def _petty_cash(company):
	if not _readable(PETTY_CASH_DT):
		return None
	today = getdate(nowdate())
	return frappe.get_list(
		PETTY_CASH_DT,
		filters={
			"docstatus": 1,
			"posting_date": ["between", [get_first_day(today), get_last_day(today)]],
			**_company_filter(company),
		},
		fields=["company", "sum(amount) as total", "count(name) as count"],
		group_by="company",
		order_by="total desc",
	)


@frappe.whitelist()
def get_financial_health(company=None):
	check_management()
	frappe.has_permission("GL Entry", "read", throw=True)

	companies = _permitted_companies(company)
	return {
		"receivables": _outstanding(SALES_INVOICE_DT, company),
		"payables": _outstanding(PURCHASE_INVOICE_DT, company),
		"cash_and_bank": _cash_and_bank(companies),
		"vat_position": _vat_position(companies),
		"petty_cash": _petty_cash(company),
		"currency": _currency(company),
	}


# ---------------------------------------------------------------------------
# Tab 3 — Commission
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_commission_payroll(company=None):
	check_management()
	frappe.has_permission(COMMISSION_ENTRY_DT, "read", throw=True)

	today = getdate(nowdate())
	commission = {"entry_type": COMMISSION_TYPE, "docstatus": 1, **_company_filter(company)}

	status_by_company = frappe.get_list(
		COMMISSION_ENTRY_DT,
		filters={
			**commission,
			"posting_date": ["between", [get_first_day(today), get_last_day(today)]],
			"status": ["in", COMMISSION_STATUSES],
		},
		fields=["company", "status", "sum(commission_amount) as total"],
		group_by="company, status",
	)

	fy_start, fy_end = _fiscal_year_range(company)
	top_salespeople = frappe.get_list(
		COMMISSION_ENTRY_DT,
		filters={**commission, "posting_date": ["between", [fy_start, fy_end]], "status": ["in", EARNED_STATUSES]},
		fields=["commission_credited_to", "sum(commission_amount) as total"],
		group_by="commission_credited_to",
		order_by="total desc",
		limit_page_length=5,
	)

	pending_by_company = frappe.get_list(
		COMMISSION_ENTRY_DT,
		filters={"status": PENDING_APPROVAL_STATUS, "docstatus": 1, **_company_filter(company)},
		fields=["company", "count(name) as count"],
		group_by="company",
	)

	return {
		"status_by_company": status_by_company,
		"top_salespeople": top_salespeople,
		"pending_by_company": pending_by_company,
		"pending_total": sum(row.count for row in pending_by_company),
		"approved_unpaid": _sum(COMMISSION_ENTRY_DT, "commission_amount", {**commission, "status": "Approved"}),
		"outstanding_deductions": _sum(
			COMMISSION_ENTRY_DT,
			"commission_amount",
			{
				"entry_type": DEDUCTION_TYPE,
				"docstatus": 1,
				"status": ["not in", SETTLED_DEDUCTION_STATUSES],
				**_company_filter(company),
			},
		),
		"fiscal_year_range": [str(fy_start), str(fy_end)],
		"currency": _currency(company),
	}
