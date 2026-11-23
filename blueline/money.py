"""Company currency for every amount Blueline shows.

An amount is always shown in the currency of its own company, with that currency's symbol and
number format; never the site's global default currency. Amounts of companies with different
currencies are never added together: a view that covers several companies is split into one
section per currency (see currency_sections), and per-company rows carry their own currency.
"""

import frappe
from frappe.utils import fmt_money


def company_currency(company):
	"""The company's Default Currency (the site default only if the company has none)."""
	currency = frappe.get_cached_value("Company", company, "default_currency") if company else None
	return currency or frappe.db.get_default("currency")


def currency_groups(companies):
	"""[(currency, [companies])], sorted by currency: companies that can be summed together."""
	groups = {}
	for company in companies:
		groups.setdefault(company_currency(company), []).append(company)
	return sorted(groups.items())


def currency_sections(companies, build):
	"""Run `build(scope)` once per currency group and return the response for a page.

	`scope` is the list of companies of one currency. The response always has `sections`
	(each with `currency` and `companies`); when there is a single section its keys are also
	returned at the top level, so a page or caller that works with one company is unchanged.
	"""
	sections = []
	# No visible company: one empty section, so the page still gets its usual keys (in the
	# currency of the user's default company).
	empty = [(company_currency(frappe.defaults.get_user_default("company")), [])]
	for currency, scope in currency_groups(companies) or empty:
		section = build(scope)
		section.update(currency=currency, companies=scope)
		sections.append(section)
	response = dict(sections[0]) if len(sections) == 1 else {"currency": None}
	response["sections"] = sections
	return response


def format_money(amount, currency):
	"""Amount with the currency's symbol and its own number format."""
	number_format = frappe.get_cached_value("Currency", currency, "number_format") if currency else None
	return fmt_money(amount, currency=currency, format=number_format or None)


def format_company_money(amount, company):
	return format_money(amount, company_currency(company))


def amounts_by_currency(rows, amount_key="amount", company_key="company"):
	"""Add up rows per company currency: [{"currency": ..., "amount": ...}], sorted by currency."""
	totals = {}
	for row in rows:
		currency = company_currency(row.get(company_key))
		totals[currency] = totals.get(currency, 0.0) + (row.get(amount_key) or 0.0)
	return [{"currency": currency, "amount": totals[currency]} for currency in sorted(totals)]
