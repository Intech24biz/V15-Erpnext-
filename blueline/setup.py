import json

import frappe
from frappe.utils.fixtures import sync_fixtures

# Insert-only seed data (see the note on `fixtures` in hooks.py): created when missing,
# never updated, so approver roles changed on site survive every migrate.
SEED_FILES = ("workflow.json", "notification.json")


def after_install():
    """Run after app installation"""
    # install-app runs after_install *before* it syncs fixtures; the seeded workflows link
    # to the Roles, Workflow States and Workflow Actions those fixtures create.
    sync_fixtures("blueline")
    create_missing_seed_records()
    frappe.msgprint(
        "Blueline app installed successfully. Custom fields and print formats are ready.",
        title="Blueline App Installed"
    )


def after_migrate():
    """Run after bench migrate"""
    create_missing_seed_records()


def create_missing_seed_records():
    for fname in SEED_FILES:
        with open(frappe.get_app_path("blueline", "setup_data", fname)) as f:
            records = json.load(f)
        for data in records:
            if frappe.db.exists(data["doctype"], data["name"]):
                continue
            doc = frappe.get_doc(data)
            doc.flags.ignore_permissions = True
            doc.insert()
