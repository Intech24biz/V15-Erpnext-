from . import __version__ as app_version

app_name = "blueline"
app_title = "Blueline"
app_publisher = "NovixCore — Sohail Zafar"
app_description = "ERPNext customisation for Blueline Enterprises & General Innovations (Sri Lanka)"
app_email = "novixcore@gmail.com"
app_license = "MIT"
app_version = app_version

required_apps = ["erpnext"]

# Workflows ("GI ...") and their pending-approval Notifications are deliberately NOT fixtures:
# Frappe re-imports fixtures with force=True on every bench migrate, which put back the
# shipped approver roles over any change a System Manager had made on site. They are
# seeded from blueline/setup_data/ by setup.after_migrate, insert-only. To change them on
# an existing site, use the Workflow / Notification screen (or a patch), not those files.
fixtures = [
    {"doctype": "Custom Field", "filters": [["module", "=", "Blueline"]]},
    {
        "doctype": "Role",
        "filters": [
            ["name", "in", [
                "GI Management",
                "GI Sales Dept",
                "GI Sales Dept 2",
                "GI Tech Dept",
                "Financial Manager",
                "Technical Approver",
            ]],
        ],
    },
    {
        "doctype": "Workflow State",
        "filters": [["name", "in", [
            "Draft",
            "Pending Approval",
            "Approved",
            "Accrued",
            "Payment Received - Pending Approval",
            "Paid",
        ]]],
    },
    {
        "doctype": "Workflow Action Master",
        "filters": [["name", "in", [
            "Approve",
            "Submit",
            "Send for Approval",
            "Payment Received",
            "Mark as Paid",
        ]]],
    },
    {"doctype": "Workspace", "filters": [["name", "=", "Blueline Control Center"]]},
]

doc_events = {
    "Workflow": {
        "validate": "blueline.server_scripts.workflow_guard.only_system_manager",
        "on_trash": "blueline.server_scripts.workflow_guard.only_system_manager",
    },
    "Quotation": {
        "validate": "blueline.server_scripts.self_approval.record_sender",
        "before_submit": [
            "blueline.server_scripts.self_approval.block_self_approval",
            "blueline.server_scripts.approval_enforcement.enforce_approval",
        ],
    },
    "Purchase Order": {
        "validate": "blueline.server_scripts.self_approval.record_sender",
        "before_submit": [
            "blueline.server_scripts.self_approval.block_self_approval",
            "blueline.server_scripts.approval_enforcement.enforce_approval",
        ],
    },
    "Sales Invoice": {
        "before_insert": "blueline.server_scripts.tax_invoice_serial.set_credit_note_series",
        "validate": [
            "blueline.server_scripts.self_approval.record_sender",
            "blueline.server_scripts.tax_invoice_serial.validate_serial_and_series",
        ],
        "before_submit": [
            "blueline.server_scripts.self_approval.block_self_approval",
            "blueline.server_scripts.tax_invoice_serial.generate_serial_number",
            "blueline.server_scripts.approval_enforcement.enforce_approval",
            # Last: nothing the Credit Note's submission writes may come before it.
            "blueline.server_scripts.sales_commission.mark_credit_note_savepoint",
        ],
        # On a Credit Note this adjusts the original invoice's commission instead of accruing.
        "on_submit": "blueline.server_scripts.sales_commission.create_commission_entries",
        "on_cancel": "blueline.server_scripts.sales_commission.reverse_credit_note",
        "before_cancel": [
            # Approved tax invoices are reversed by Credit Note, never cancelled; the
            # commission guard still covers invoices that never received a serial.
            "blueline.server_scripts.tax_invoice_serial.block_cancel_of_tax_invoice",
            "blueline.server_scripts.sales_commission.guard_commission_entries_on_cancel",
        ],
    },
    "Petty Cash Voucher": {
        "validate": "blueline.server_scripts.self_approval.record_sender",
        "before_submit": "blueline.server_scripts.self_approval.block_self_approval",
    },
    "Payment Entry": {
        "validate": "blueline.server_scripts.self_approval.record_sender",
        "before_submit": [
            "blueline.server_scripts.self_approval.block_self_approval",
            "blueline.server_scripts.approval_enforcement.enforce_approval",
        ],
        "on_submit": "blueline.server_scripts.sales_commission.release_commission_entries",
        # Payment Reconciliation can update an already-submitted Payment Entry's
        # references without re-firing on_submit; this catches that path too.
        "on_update_after_submit": "blueline.server_scripts.sales_commission.release_commission_entries",
        # An undone payment can leave the invoice unpaid again (see reopen_if_unsettled).
        "on_cancel": "blueline.server_scripts.sales_commission.reopen_on_payment_cancel",
    },
    # Commission is released when an invoice's outstanding reaches zero by any route.
    "Journal Entry": {
        "on_submit": "blueline.server_scripts.sales_commission.release_on_journal_entry",
        "on_cancel": "blueline.server_scripts.sales_commission.reopen_on_journal_cancel",
    },
    "Unreconcile Payment": {
        "on_submit": "blueline.server_scripts.sales_commission.reopen_on_unreconcile",
    },
    "Payment Ledger Entry": {
        "on_update": "blueline.server_scripts.sales_commission.release_on_ledger_update",
    },
    "Customer": {
        "after_insert": "blueline.server_scripts.customer_master.save_customer_tin",
        "on_update": "blueline.server_scripts.customer_master.save_customer_tin",
    }
}

after_install = "blueline.setup.after_install"
after_migrate = "blueline.setup.after_migrate"
