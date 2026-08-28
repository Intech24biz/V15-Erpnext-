from collections import OrderedDict

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Avg, Count, Sum
from frappe.utils import flt, getdate

WON_STATUSES = ("Ordered", "Partially Ordered")
LOST_STATUSES = ("Lost", "Cancelled", "Expired")


def _check_permission():
	if not frappe.has_permission("Quotation History", "read"):
		frappe.throw(_("Not permitted to view Quotation History"), frappe.PermissionError)


def _apply_filters(query, qh, filters):
	if filters.get("company"):
		query = query.where(qh.company == filters["company"])
	if filters.get("from_date"):
		query = query.where(qh.transaction_date >= getdate(filters["from_date"]))
	if filters.get("to_date"):
		query = query.where(qh.transaction_date <= getdate(filters["to_date"]))
	if filters.get("status"):
		query = query.where(qh.status == filters["status"])
	return query


@frappe.whitelist()
def get_dashboard_data(company=None, from_date=None, to_date=None, status=None):
	_check_permission()

	filters = {
		"company": company,
		"from_date": from_date,
		"to_date": to_date,
		"status": status,
	}

	qh = frappe.qb.DocType("Quotation History")

	summary_row = _apply_filters(
		frappe.qb.from_(qh).select(
			Count(qh.name).as_("total_quotations"),
			Sum(qh.base_grand_total).as_("total_value"),
			Avg(qh.base_grand_total).as_("avg_value"),
		),
		qh,
		filters,
	).run(as_dict=True)[0]

	won_count = _apply_filters(
		frappe.qb.from_(qh).select(Count(qh.name).as_("won_count")).where(qh.status.isin(WON_STATUSES)),
		qh,
		filters,
	).run(as_dict=True)[0].won_count

	lost_count = _apply_filters(
		frappe.qb.from_(qh).select(Count(qh.name).as_("lost_count")).where(qh.status.isin(LOST_STATUSES)),
		qh,
		filters,
	).run(as_dict=True)[0].lost_count

	total_quotations = summary_row.total_quotations or 0
	conversion_rate = flt(won_count) / total_quotations * 100 if total_quotations else 0

	summary = {
		"total_quotations": total_quotations,
		"total_value": flt(summary_row.total_value),
		"avg_value": flt(summary_row.avg_value),
		"won_count": won_count or 0,
		"lost_count": lost_count or 0,
		"conversion_rate": flt(conversion_rate, 2),
	}

	status_breakdown = _apply_filters(
		frappe.qb.from_(qh)
		.select(qh.status, Count(qh.name).as_("count"), Sum(qh.base_grand_total).as_("value"))
		.groupby(qh.status)
		.orderby(Count(qh.name), order=Order.desc),
		qh,
		filters,
	).run(as_dict=True)

	company_breakdown = _apply_filters(
		frappe.qb.from_(qh)
		.select(qh.company, Count(qh.name).as_("count"), Sum(qh.base_grand_total).as_("value"))
		.groupby(qh.company)
		.orderby(Sum(qh.base_grand_total), order=Order.desc),
		qh,
		filters,
	).run(as_dict=True)

	top_customers = _apply_filters(
		frappe.qb.from_(qh)
		.select(qh.customer_name, Count(qh.name).as_("count"), Sum(qh.base_grand_total).as_("value"))
		.groupby(qh.customer_name)
		.orderby(Sum(qh.base_grand_total), order=Order.desc)
		.limit(10),
		qh,
		filters,
	).run(as_dict=True)

	trend_rows = _apply_filters(
		frappe.qb.from_(qh).select(qh.transaction_date, qh.base_grand_total),
		qh,
		filters,
	).run(as_dict=True)

	trend_map = OrderedDict()
	for row in sorted(trend_rows, key=lambda r: r.transaction_date or getdate()):
		key = row.transaction_date.strftime("%Y-%m") if row.transaction_date else _("Unknown")
		bucket = trend_map.setdefault(key, {"month": key, "count": 0, "value": 0.0})
		bucket["count"] += 1
		bucket["value"] += flt(row.base_grand_total)

	return {
		"summary": summary,
		"status_breakdown": status_breakdown,
		"company_breakdown": company_breakdown,
		"top_customers": top_customers,
		"monthly_trend": list(trend_map.values()),
	}
