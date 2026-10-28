import frappe


def execute():
	# Entries accrued before Original Commission Amount existed: nothing has adjusted them yet
	# (Credit Note adjustment ships together with the field), so the original is today's amount.
	frappe.db.sql(
		"""
		update `tabSales Commission Entry`
		set original_commission_amount = commission_amount
		where ifnull(original_commission_amount, 0) = 0
			and ifnull(entry_type, 'Commission') = 'Commission'
		"""
	)
