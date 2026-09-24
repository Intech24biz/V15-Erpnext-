from . import __version__ as app_version

app_name = "blueline"
app_title = "Blueline"
app_publisher = "NovixCore — Sohail Zafar"
app_description = "ERPNext customisation for Blueline Enterprises & General Innovations (Sri Lanka)"
app_email = "novixcore@gmail.com"
app_license = "MIT"
app_version = app_version

required_apps = ["erpnext"]

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
    {"doctype": "Workflow", "filters": [["name", "like", "GI %"]]},
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
    {"doctype": "Notification", "filters": [["name", "like", "GI %"]]},
    {"doctype": "Workspace", "filters": [["name", "=", "Blueline Control Center"]]},
]

doc_events = {
    "Quotation": {
        "before_submit": "blueline.server_scripts.approval_enforcement.enforce_approval",
    },
    "Purchase Order": {
        "before_submit": "blueline.server_scripts.approval_enforcement.enforce_approval",
    },
    "Sales Invoice": {
        "before_submit": [
            "blueline.server_scripts.tax_invoice_serial.generate_serial_number",
            "blueline.server_scripts.approval_enforcement.enforce_approval",
        ],
        "on_submit": "blueline.server_scripts.sales_commission.create_commission_entries",
        "before_cancel": "blueline.server_scripts.sales_commission.guard_commission_entries_on_cancel",
    },
    "Payment Entry": {
        "before_submit": "blueline.server_scripts.approval_enforcement.enforce_approval",
        "on_submit": "blueline.server_scripts.sales_commission.release_commission_entries",
        # Payment Reconciliation can update an already-submitted Payment Entry's
        # references without re-firing on_submit; this catches that path too.
        "on_update_after_submit": "blueline.server_scripts.sales_commission.release_commission_entries",
    },
    "Customer": {
        "after_insert": "blueline.server_scripts.customer_master.save_customer_tin",
        "on_update": "blueline.server_scripts.customer_master.save_customer_tin",
    }
}

after_install = "blueline.setup.after_install"
after_migrate = "blueline.setup.after_migrate"
