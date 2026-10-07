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
	"commission_amount",
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

	summary = {s: {"count": 0, "commission_amount": 0.0} for s in STATUS_OPTIONS}
	for entry in entries:
		bucket = summary.setdefault(entry.status, {"count": 0, "commission_amount": 0.0})
		bucket["count"] += 1
		bucket["commission_amount"] += entry.commission_amount or 0.0

	return {
		"entries": entries,
		"summary": summary,
		"status_options": STATUS_OPTIONS,
	}
