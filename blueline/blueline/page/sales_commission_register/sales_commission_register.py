import frappe
from frappe import _
from frappe.utils import flt, getdate

from blueline.blueline.doctype.sales_commission_entry.sales_commission_entry import APPROVED_STATUS, fit_deductions

DOCTYPE = "Sales Commission Entry"

FIELDS = [
	"name",
	"sales_invoice",
	"posting_date",
	"matched_sales_person",
	"commission_credited_to",
	"customer",
	"item_code",
	"company",
	"qty",
	"amount",
	"commission_type",
	"entry_type",
	"commission_amount",
	"original_commission_amount",
	"credit_note",
	"against_commission_entry",
	"status",
	"approved_by_management",
	"approved_by_technical",
	"payment_entry",
]

STATUS_OPTIONS = [
	"Accrued",
	"Payment Received - Pending Approval",
	"Approved",
	"Paid",
	"Cancelled",
]

DEDUCTION_TYPE = "Deduction"
# A deduction becomes Paid when it is taken off a payout with the payee's commission
# (SalesCommissionEntry.settle_deductions); it then leaves the outstanding list.
SETTLED_DEDUCTION_STATUSES = ["Paid", "Cancelled"]


def _check_permission():
	if not frappe.has_permission(DOCTYPE, "read"):
		frappe.throw(_("Not permitted to view {0}").format(_(DOCTYPE)), frappe.PermissionError)


@frappe.whitelist()
def get_entries(
	status=None,
	matched_sales_person=None,
	commission_credited_to=None,
	company=None,
	from_date=None,
	to_date=None,
):
	_check_permission()

	filters = {}
	if status:
		filters["status"] = status
	if matched_sales_person:
		filters["matched_sales_person"] = matched_sales_person
	if commission_credited_to:
		filters["commission_credited_to"] = commission_credited_to
	if company:
		filters["company"] = company
	if from_date and to_date:
		filters["posting_date"] = ["between", [getdate(from_date), getdate(to_date)]]
	elif from_date:
		filters["posting_date"] = [">=", getdate(from_date)]
	elif to_date:
		filters["posting_date"] = ["<=", getdate(to_date)]

	# get_list (not get_all): applies role permissions and Company User Permissions, same
	# rule as the COA console — a company-restricted user only sees their own entries.
	entries = frappe.get_list(
		DOCTYPE,
		filters=filters,
		fields=FIELDS,
		order_by="posting_date desc, name desc",
		limit_page_length=0,
	)

	# Deductions are money owed back, not commission earned: they're kept out of the status
	# totals (which would otherwise net them silently) and shown as their own balance.
	summary = {s: {"count": 0, "commission_amount": 0.0} for s in STATUS_OPTIONS}
	for entry in entries:
		if entry.entry_type == DEDUCTION_TYPE:
			continue
		bucket = summary.setdefault(entry.status, {"count": 0, "commission_amount": 0.0})
		bucket["count"] += 1
		bucket["commission_amount"] += entry.commission_amount or 0.0

	return {
		"entries": entries,
		"summary": summary,
		"status_options": STATUS_OPTIONS,
		"deductions": get_outstanding_deductions(matched_sales_person, commission_credited_to, company),
	}


def get_outstanding_deductions(matched_sales_person=None, commission_credited_to=None, company=None):
	"""Per person (Commission Credited To — who receives the payout): Deduction entries still
	to be taken off a payout. A balance, so the status and date filters don't apply.

	Each person's deductions are split three ways (`bucket` on each entry):
	- awaiting_approval: not Approved yet, so nothing takes them off;
	- next_payout: Approved, and they fit into the person's Approved commission that is
	  waiting to be paid, if it is all paid out on one payout;
	- too_large: Approved, but they don't fit into that commission yet and wait for more.
	The split uses the same rule as Mark as Paid (fit_deductions: oldest first, whole ones
	only, never below zero, one that doesn't fit is skipped)."""
	filters = {
		"entry_type": DEDUCTION_TYPE,
		"deduct_from_next_payout": 1,
		"docstatus": 1,
		"status": ["not in", SETTLED_DEDUCTION_STATUSES],
	}
	if matched_sales_person:
		filters["matched_sales_person"] = matched_sales_person
	if commission_credited_to:
		filters["commission_credited_to"] = commission_credited_to
	if company:
		filters["company"] = company

	rows = frappe.get_list(
		DOCTYPE,
		filters=filters,
		fields=["name", "commission_credited_to", "company", "commission_amount", "status", "credit_note", "posting_date"],
		order_by="commission_credited_to asc, posting_date asc, name asc",
		limit_page_length=0,
	)
	by_person = {}
	for row in rows:
		person = by_person.setdefault(
			(row.commission_credited_to, row.company),
			{
				"commission_credited_to": row.commission_credited_to,
				"company": row.company,
				"amount": 0.0,
				"awaiting_approval_amount": 0.0,
				"next_payout_amount": 0.0,
				"too_large_amount": 0.0,
				"approved_commission": 0.0,
				"entries": [],
				"rows": [],
			},
		)
		person["amount"] += row.commission_amount or 0.0
		person["rows"].append(row)

	precision = frappe.get_precision(DOCTYPE, "commission_amount")
	for (payee, payee_company), person in by_person.items():
		person["approved_commission"] = waiting_commission(payee, payee_company)
		approved = [r for r in person["rows"] if r.status == APPROVED_STATUS]
		taken = {d.name for d in fit_deductions(person["approved_commission"], approved, precision)}
		for row in person.pop("rows"):
			if row.status != APPROVED_STATUS:
				bucket = "awaiting_approval"
			elif row.name in taken:
				bucket = "next_payout"
			else:
				bucket = "too_large"
			person[f"{bucket}_amount"] += row.commission_amount or 0.0
			person["entries"].append(
				{"name": row.name, "status": row.status, "credit_note": row.credit_note, "bucket": bucket}
			)
	return list(by_person.values())


def waiting_commission(commission_credited_to, company):
	"""The person's Approved commission not yet paid out: what their next payout covers."""
	rows = frappe.get_list(
		DOCTYPE,
		filters={
			"entry_type": ["!=", DEDUCTION_TYPE],
			"docstatus": 1,
			"status": APPROVED_STATUS,
			"commission_credited_to": commission_credited_to,
			"company": company,
		},
		fields=["commission_amount"],
		limit_page_length=0,
	)
	return sum(flt(r.commission_amount) for r in rows)
