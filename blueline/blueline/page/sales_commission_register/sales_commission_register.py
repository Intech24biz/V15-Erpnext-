import frappe
from frappe import _
from frappe.utils import getdate

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
# Paid can't happen to a deduction today (Mark as Paid refuses it); listed so that netting,
# once built, closes a deduction by marking it Paid without changing this page.
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
	to be taken off a payout. A balance, so the status and date filters don't apply."""
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
		fields=["name", "commission_credited_to", "company", "commission_amount", "status", "credit_note"],
		order_by="commission_credited_to asc, name asc",
		limit_page_length=0,
	)
	by_person = {}
	for row in rows:
		person = by_person.setdefault(
			(row.commission_credited_to, row.company),
			{"commission_credited_to": row.commission_credited_to, "company": row.company, "amount": 0.0, "entries": []},
		)
		person["amount"] += row.commission_amount or 0.0
		person["entries"].append({"name": row.name, "status": row.status, "credit_note": row.credit_note})
	return list(by_person.values())
