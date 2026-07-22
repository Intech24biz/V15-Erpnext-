import frappe


def after_install():
    """Run after app installation"""
    frappe.msgprint(
        "Blueline app installed successfully. Custom fields and print formats are ready.",
        title="Blueline App Installed"
    )


def after_migrate():
    """Run after bench migrate"""
    pass
