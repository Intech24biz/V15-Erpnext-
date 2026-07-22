import frappe


def save_customer_tin(doc, method=None):
    """
    Auto-populate customer TIN details from Customer master
    to ensure they are available on Sales Invoice print format.
    Called via hooks: Customer after_insert / on_update
    """
    pass  # Placeholder — TIN is fetched directly in print format via doc fields
