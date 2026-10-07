import frappe
from frappe import _
from frappe.model.document import Document


class SalesCommissionRule(Document):
	def validate(self):
		if self.enabled:
			self.check_duplicate()

	def check_duplicate(self):
		# Same customer + item_code + company, across ALL sales persons: commission is
		# matched on item/customer alone, so two enabled rules here would make the
		# accrual hook unable to tell who made the sale. Blank customer/item_code is
		# included literally, since "" means "any" and is itself a specific combination.
		filters = {
			"customer": self.customer or "",
			"item_code": self.item_code or "",
			"company": self.company,
			"enabled": 1,
			"name": ["!=", self.name or ""],
		}
		duplicate = frappe.get_list(
			"Sales Commission Rule", filters=filters, fields=["name", "sales_person"], limit=1
		)
		if duplicate:
			frappe.throw(
				_(
					"Another enabled Sales Commission Rule ({0}, Sales Person {1}) already exists "
					"for this Customer, Item and Company combination. Only one Sales Person can "
					"be matched per combination."
				).format(duplicate[0].name, duplicate[0].sales_person)
			)
