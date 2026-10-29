"""Item 5 — facts about commission matching, kept as regression tests (no code was changed).

5a: one invoice line can never yield two entries for the same Matched Sales Person, but it can
    yield several entries credited to the same group (one per rep under that group).
5b: Commission Credited To is resolved once, at accrual, and stored; later changes to the
    Sales Person tree never alter an existing entry.
"""

import frappe

from blueline.server_scripts.sales_commission import resolve_commission_leader
from blueline.tests.utils import (
	COMMISSION_ITEM,
	CUSTOMER,
	FINANCIAL_MANAGER,
	GI_MANAGEMENT,
	BluelineTestCase,
	approved_invoice,
	approved_payment_for,
	commission_entries,
	update_entry,
)

# The three enabled rules for CUSTOMER + COMMISSION_ITEM in Blueline Enterprises.
GROUP = "W Chaminda Priyalal"
REPS_UNDER_GROUP = ("M.Madusha Darshani", "W.B.Prasanna")
OTHER_PAYEE = "M M M M PARIS"


class TestMatchedSalesPersonIsUnique(BluelineTestCase):
	def test_one_entry_per_matched_person_per_line(self):
		invoice = approved_invoice()
		entries = commission_entries(invoice.name)
		people = [e.matched_sales_person for e in entries]
		self.assertEqual(sorted(people), sorted([*REPS_UNDER_GROUP, OTHER_PAYEE]))
		self.assertEqual(len(people), len(set(people)))

	def test_duplicate_rule_for_same_person_is_refused(self):
		rule = frappe.get_doc(
			{
				"doctype": "Sales Commission Rule",
				"sales_person": "W.B.Prasanna",
				"customer": CUSTOMER,
				"item_code": COMMISSION_ITEM,
				"company": "Blueline Enterprises Pvt Ltd",
				"commission_type": "Fixed Amount Per Unit",
				"rate": 999,
				"enabled": 1,
			}
		)
		self.assertRefused(rule.insert, "already exists for this Sales Person, Customer, Item and Company")

	def test_forced_duplicate_rule_still_gives_at_most_one_entry(self):
		"""Even if a duplicate rule got past validation (e.g. written directly to the DB), the
		accrual skips that person and logs it rather than creating two entries."""
		rule = frappe.get_doc(
			{
				"doctype": "Sales Commission Rule",
				"sales_person": "W.B.Prasanna",
				"customer": CUSTOMER,
				"item_code": COMMISSION_ITEM,
				"company": "Blueline Enterprises Pvt Ltd",
				"commission_type": "Fixed Amount Per Unit",
				"rate": 999,
				"enabled": 1,
			}
		)
		rule.flags.ignore_validate = True
		rule.insert()

		invoice = approved_invoice()
		people = [e.matched_sales_person for e in commission_entries(invoice.name)]
		self.assertEqual(len(people), len(set(people)))
		self.assertNotIn("W.B.Prasanna", people)
		self.assertTrue(
			frappe.db.exists("Error Log", {"method": ["like", f"%duplicate rules for W.B.Prasanna ({invoice.name}%"]})
		)

	def test_same_item_on_two_rows_gives_entries_per_row(self):
		invoice = approved_invoice(lines=[(COMMISSION_ITEM, 1, 100), (COMMISSION_ITEM, 1, 100)])
		rows = frappe.get_all(
			"Sales Commission Entry",
			filters={"sales_invoice": invoice.name},
			fields=["sales_invoice_item", "matched_sales_person"],
		)
		self.assertEqual(len(rows), 6)
		self.assertEqual(len({(r.sales_invoice_item, r.matched_sales_person) for r in rows}), 6)


class TestCreditedToMayRepeat(BluelineTestCase):
	def test_two_reps_under_one_group_credit_that_group_twice(self):
		invoice = approved_invoice()
		credited = [e.commission_credited_to for e in commission_entries(invoice.name)]
		self.assertEqual(credited.count(GROUP), 2)


class TestCreditedToIsStored(BluelineTestCase):
	def test_reparenting_the_rep_never_changes_an_existing_entry(self):
		invoice = approved_invoice()
		entry = next(e for e in commission_entries(invoice.name) if e.matched_sales_person == "W.B.Prasanna")
		self.assertEqual(entry.commission_credited_to, GROUP)

		rep = frappe.get_doc("Sales Person", "W.B.Prasanna")
		rep.parent_sales_person = "K P THANUSHA"
		rep.save()
		self.assertEqual(resolve_commission_leader("W.B.Prasanna"), "K P THANUSHA")

		def credited_to():
			return frappe.db.get_value("Sales Commission Entry", entry.name, "commission_credited_to")

		self.assertEqual(credited_to(), GROUP, "changed on view/reload")

		from blueline.blueline.page.sales_commission_register.sales_commission_register import get_entries

		shown = next(r for r in get_entries()["entries"] if r.name == entry.name)
		self.assertEqual(shown.commission_credited_to, GROUP, "changed in the register")

		payment = approved_payment_for(invoice)
		self.assertEqual(credited_to(), GROUP, "changed on payment release")

		update_entry(entry.name, FINANCIAL_MANAGER, approved_by_management=1)
		update_entry(entry.name, GI_MANAGEMENT, approved_by_technical=1)
		self.assertEqual(credited_to(), GROUP, "changed on approval")

		from blueline.server_scripts.sales_commission import mark_commission_entry_paid

		from blueline.tests.utils import approved_payout

		payout = approved_payout(entry.commission_amount)
		frappe.set_user(FINANCIAL_MANAGER)
		mark_commission_entry_paid(entry.name, payout.name)
		frappe.set_user("Administrator")
		self.assertEqual(credited_to(), GROUP, "changed on pay")

		# New sales after the move are credited under the new tree.
		later = approved_invoice()
		later_entry = next(e for e in commission_entries(later.name) if e.matched_sales_person == "W.B.Prasanna")
		self.assertEqual(later_entry.commission_credited_to, "K P THANUSHA")
