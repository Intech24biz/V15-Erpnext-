import frappe
from frappe.utils.fixtures import sync_fixtures

from blueline import workflow_sync

# Insert-only seed data (see the note on `fixtures` in hooks.py): created when missing,
# never updated, so approver roles changed on site survive every migrate. Seeded from the
# committed snapshot of the live site when there is one (see workflow_sync.py).


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
    # Report only: a difference here is a System Manager's change on site, which is kept.
    try:
        workflow_sync.check_drift()
    except Exception:
        frappe.log_error(title="Blueline workflow drift check failed", message=frappe.get_traceback())
    # Folders only; files are filed into them as they are attached (document_folders.py).
    from blueline.document_folders import ensure_all_folders

    ensure_all_folders()


def create_missing_seed_records():
    for fname in workflow_sync.SEED_FILES:
        for data in workflow_sync.seed_records(fname):
            if frappe.db.exists(data["doctype"], data["name"]):
                continue
            doc = frappe.get_doc(data)
            doc.flags.ignore_permissions = True
            doc.insert()
