import frappe
from frappe import _
from frappe.utils import flt, getdate

OUTPUT_ROOT_TYPE = "Liability"
INPUT_ROOT_TYPE = "Asset"
SVAT_ROOT_TYPE = "Income"

# Terms that disqualify an account even though its name contains "VAT" —
# these catch intercompany payables and non-VAT tax accounts that share the substring.
VAT_NAME_EXCLUDE_TERMS = ("NBT", "INCOME", "DUE", "BLUELINE", "INNOVATION")


def _check_permission():
	if not frappe.has_permission("GL Entry", "read"):
		frappe.throw(_("Not permitted to view GL Entry"), frappe.PermissionError)


def _get_vat_accounts(company):
	conditions = ["company = %(company)s", "is_group = 0", "upper(name) like %(vat_like)s"]
	params = {"company": company, "vat_like": "%VAT%"}

	for i, term in enumerate(VAT_NAME_EXCLUDE_TERMS):
		key = f"exclude_{i}"
		conditions.append(f"upper(name) not like %({key})s")
		params[key] = f"%{term}%"

	return frappe.db.sql(
		f"""
		select name, root_type
		from `tabAccount`
		where {" and ".join(conditions)}
		""",
		params,
		as_dict=True,
	)


def _classify(root_type):
	if root_type == OUTPUT_ROOT_TYPE:
		return "output"
	if root_type == INPUT_ROOT_TYPE:
		return "input"
	if root_type == SVAT_ROOT_TYPE:
		return "svat"
	return "other"


def _get_gl_entries(company, accounts, from_date, to_date):
	conditions = ["company = %(company)s", "is_cancelled = 0", "account in %(accounts)s"]
	params = {"company": company, "accounts": accounts}

	if from_date:
		conditions.append("posting_date >= %(from_date)s")
		params["from_date"] = getdate(from_date)
	if to_date:
		conditions.append("posting_date <= %(to_date)s")
		params["to_date"] = getdate(to_date)

	return frappe.db.sql(
		f"""
		select account, posting_date, debit, credit
		from `tabGL Entry`
		where {" and ".join(conditions)}
		""",
		params,
		as_dict=True,
	)


@frappe.whitelist()
def get_vat_data(company, from_date=None, to_date=None):
	_check_permission()

	if not company:
		frappe.throw(_("Company is required"))

	accounts = _get_vat_accounts(company)
	empty_result = {
		"summary": {"total_output": 0.0, "total_input": 0.0, "total_svat": 0.0, "net_vat": 0.0},
		"monthly": [],
		"account_detail": [],
	}
	if not accounts:
		return empty_result

	account_meta = {row.name: row.root_type for row in accounts}
	gl_rows = _get_gl_entries(company, list(account_meta.keys()), from_date, to_date)
	if not gl_rows:
		return empty_result

	monthly_map = {}
	account_totals = {}

	for row in gl_rows:
		root_type = account_meta.get(row.account)
		classification = _classify(root_type)
		net_movement = flt(row.debit) - flt(row.credit)

		acc_bucket = account_totals.setdefault(
			row.account,
			{
				"account": row.account,
				"root_type": root_type,
				"classification": classification,
				"amount": 0.0,
			},
		)

		if classification == "output":
			# Net credit balance = VAT charged on sales, owed to the department.
			# Reported as-is (not forced positive) — a negative here is a genuine
			# net-recoverable position on that account (e.g. an opening debit balance).
			amount = flt(row.credit) - flt(row.debit)
		elif classification == "input":
			# Net debit balance = VAT paid on purchases, recoverable
			amount = flt(row.debit) - flt(row.credit)
		elif classification == "svat":
			# GI's SVAT 18% sits under an Income root_type — kept out of the
			# output/input net calc and reported as its own labelled total.
			amount = flt(row.credit) - flt(row.debit)
		else:
			amount = net_movement

		acc_bucket["amount"] += amount

		if classification in ("output", "input"):
			month = row.posting_date.strftime("%Y-%m") if row.posting_date else _("Unknown")
			bucket = monthly_map.setdefault(month, {"month": month, "output": 0.0, "input": 0.0})
			bucket[classification] += amount

	# The monthly table/chart keeps showing raw output vs input per period exactly as
	# posted — the debit-balance reclassification below is a summary-only presentation.
	monthly = []
	for month in sorted(monthly_map.keys()):
		row = monthly_map[month]
		output = flt(row["output"], 2)
		input_ = flt(row["input"], 2)
		monthly.append({"month": month, "output": output, "input": input_, "net": flt(output - input_, 2)})

	account_detail = sorted(account_totals.values(), key=lambda r: (r["classification"], r["account"]))
	for row in account_detail:
		row["amount"] = flt(row["amount"], 2)

	# Summary cards: reclassify per account, not per transaction. An OUTPUT (Liability)
	# account whose net movement for the period is a debit balance isn't payable VAT —
	# it's a recoverable credit, so its absolute value rolls into total_input instead.
	# This keeps total_output honest (never negative) without touching account_detail,
	# which still shows each account's real, unadjusted net movement.
	total_output = 0.0
	total_input = 0.0
	for row in account_detail:
		if row["classification"] == "output":
			if row["amount"] >= 0:
				total_output += row["amount"]
			else:
				total_input += abs(row["amount"])
		elif row["classification"] == "input":
			total_input += row["amount"]

	total_svat = flt(
		sum(row["amount"] for row in account_detail if row["classification"] == "svat"), 2
	)

	summary = {
		"total_output": flt(total_output, 2),
		"total_input": flt(total_input, 2),
		# SVAT (Income root_type) is reported separately and is NOT folded into net_vat.
		"total_svat": total_svat,
		"net_vat": flt(total_output - total_input, 2),
	}

	return {
		"summary": summary,
		"monthly": monthly,
		"account_detail": account_detail,
	}
