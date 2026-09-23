import frappe
from frappe import _
from frappe.model.document import Document


class SalesCommissionRule(Document):
	def validate(self):
		if self.enabled:
			self.check_duplicate()

	def check_duplicate(self):
		# Same sales_person + customer + item_code + company (blank customer/item_code
		# included literally, since "" means "any" and is itself a specific combination).
		filters = {
			"sales_person": self.sales_person,
			"customer": self.customer or "",
			"item_code": self.item_code or "",
			"company": self.company,
			"enabled": 1,
			"name": ["!=", self.name or ""],
		}
		duplicate = frappe.get_list("Sales Commission Rule", filters=filters, limit=1, pluck="name")
		if duplicate:
			frappe.throw(
				_(
					"Another enabled Sales Commission Rule ({0}) already exists for this "
					"Sales Person, Customer, Item and Company combination."
				).format(duplicate[0])
			)
