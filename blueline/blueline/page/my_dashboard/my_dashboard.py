"""Staff dashboard: the logged-in user's own work. What is waiting for their approval (by the
same rules the approval itself enforces, so nothing they created or sent is listed), what
they sent that is still waiting, their drafts and quotations, and — when their user is linked
to a Sales Person through an Employee record — their sales and commission."""

import frappe
from frappe import _
from frappe.model.workflow import get_workflow_name
from frappe.utils import flt, get_first_day, getdate, nowdate

from blueline.blueline.page.business_kpi_dashboard.business_kpi_dashboard import _fiscal_year_range
from blueline.server_scripts.self_approval import APPROVAL_DOCTYPES, PENDING_APPROVAL_STATE, SENT_BY_FIELD

APPROVE_ACTION = "Approve"
LIST_LIMIT = 50

# The amount shown for each document, in company currency.
AMOUNT_FIELDS = {
	"Quotation": "base_grand_total",
	"Purchase Order": "base_grand_total",
	"Sales Invoice": "base_grand_total",
	"Payment Entry": "base_paid_amount",
	"Petty Cash Voucher": "amount",
}
PARTY_FIELDS = {
	"Quotation": "customer_name",
	"Purchase Order": "supplier_name",
	"Sales Invoice": "customer_name",
	"Payment Entry": "party_name",
	"Petty Cash Voucher": "purpose",
}

COMMISSION_STATUSES = ("Accrued", "Payment Received - Pending Approval", "Approved", "Paid")


def _readable(doctype):
	return frappe.has_permission(doctype, "read")


def _workflow(doctype):
	name = get_workflow_name(doctype)
	return frappe.get_cached_doc("Workflow", name) if name else None


def _rows(doctype, filters):
	fields = ["name", "owner", "company", "modified", f"{AMOUNT_FIELDS[doctype]} as amount", f"{PARTY_FIELDS[doctype]} as party"]
	if frappe.get_meta(doctype).has_field(SENT_BY_FIELD):
		fields.append(f"{SENT_BY_FIELD} as sent_by")
	rows = frappe.get_list(doctype, filters=filters, fields=fields, order_by="modified asc", limit_page_length=LIST_LIMIT)
	for row in rows:
		row.doctype = doctype
	return rows


def waiting_for_my_approval(user):
	roles = set(frappe.get_roles(user))
	waiting = []
	for doctype in APPROVAL_DOCTYPES:
		wf = _workflow(doctype)
		if not wf or not _readable(doctype):
			continue
		approvers = {
			t.allowed for t in wf.transitions if t.state == PENDING_APPROVAL_STATE and t.action == APPROVE_ACTION
		}
		if not approvers & roles:
			continue
		rows = _rows(
			doctype,
			{wf.workflow_state_field: PENDING_APPROVAL_STATE, "docstatus": 0, "owner": ["!=", user]},
		)
		# Same rule as self_approval.block_self_approval: never the creator or the sender.
		waiting += [r for r in rows if r.get("sent_by") != user]
	return waiting


def sent_by_me(user):
	sent = []
	for doctype in APPROVAL_DOCTYPES:
		wf = _workflow(doctype)
		if not wf or not _readable(doctype) or not frappe.get_meta(doctype).has_field(SENT_BY_FIELD):
			continue
		sent += _rows(
			doctype,
			{wf.workflow_state_field: PENDING_APPROVAL_STATE, "docstatus": 0, SENT_BY_FIELD: user},
		)
	return sent


def my_drafts(user):
	drafts = []
	for doctype in APPROVAL_DOCTYPES:
		wf = _workflow(doctype)
		if not wf or not _readable(doctype):
			continue
		# All the user's unsubmitted documents less those already sent for approval (a "!="
		# filter would also drop drafts whose workflow state is still empty).
		count = frappe.db.count(doctype, {"owner": user, "docstatus": 0}) - frappe.db.count(
			doctype, {"owner": user, "docstatus": 0, wf.workflow_state_field: PENDING_APPROVAL_STATE}
		)
		if count:
			drafts.append({"doctype": doctype, "count": count})
	return drafts


def my_quotations(user):
	if not _readable("Quotation"):
		return None
	month_start = get_first_day(nowdate())

	def total(filters):
		row = frappe.get_list(
			"Quotation", filters=filters, fields=["count(name) as count", "sum(base_net_total) as total"]
		)[0]
		return {"count": row.count or 0, "value": flt(row.total, 2)}

	return {
		"this_month": total({"owner": user, "docstatus": 1, "transaction_date": [">=", month_start]}),
		"open": total({"owner": user, "docstatus": 1, "status": "Open"}),
	}


def my_sales_persons(user):
	employees = frappe.get_all("Employee", filters={"user_id": user}, pluck="name")
	if not employees:
		return []
	return frappe.get_all("Sales Person", filters={"employee": ["in", employees], "enabled": 1}, pluck="name")


def my_sales(sales_persons):
	"""Net sales allocated to the user's Sales Person(s) on submitted invoices (Sales Team)."""
	today = getdate(nowdate())
	fy_start, _fy_end = _fiscal_year_range(None)

	def allocated(start):
		return flt(
			frappe.db.sql(
				"""select sum(st.allocated_amount * si.conversion_rate)
				from `tabSales Team` st join `tabSales Invoice` si on si.name = st.parent
				where st.parenttype = 'Sales Invoice' and si.docstatus = 1
					and st.sales_person in %(persons)s and si.posting_date between %(start)s and %(end)s""",
				{"persons": sales_persons, "start": start, "end": today},
			)[0][0],
			2,
		)

	return {"this_month": allocated(get_first_day(today)), "fy_to_date": allocated(fy_start)}


def my_commission(sales_persons):
	# Read as the system: a sales person sees their own commission even without access to
	# Sales Commission Entry. Only their own rows are summed.
	fy_start, fy_end = _fiscal_year_range(None)
	rows = frappe.get_all(
		"Sales Commission Entry",
		filters={
			"docstatus": 1,
			"entry_type": "Commission",
			"matched_sales_person": ["in", sales_persons],
			"posting_date": ["between", [fy_start, fy_end]],
			"status": ["in", COMMISSION_STATUSES],
		},
		fields=["status", "sum(commission_amount) as total"],
		group_by="status",
	)
	by_status = {r.status: flt(r.total, 2) for r in rows}
	return [{"status": s, "amount": by_status.get(s, 0.0)} for s in COMMISSION_STATUSES]


@frappe.whitelist()
def get_my_dashboard():
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	sales_persons = my_sales_persons(user)
	return {
		"user": user,
		"waiting_for_me": waiting_for_my_approval(user),
		"sent_by_me": sent_by_me(user),
		"drafts": my_drafts(user),
		"quotations": my_quotations(user),
		"sales_persons": sales_persons,
		"sales": my_sales(sales_persons) if sales_persons else None,
		"commission": my_commission(sales_persons) if sales_persons else None,
		"currency": frappe.db.get_default("currency"),
	}
