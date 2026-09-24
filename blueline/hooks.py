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
            ]],
        ],
    },
    {"doctype": "Workflow", "filters": [["name", "like", "GI %"]]},
    {
        "doctype": "Workflow State",
        "filters": [["name", "in", ["Draft", "Pending Approval", "Approved"]]],
    },
    {
        "doctype": "Workflow Action Master",
        "filters": [["name", "in", ["Approve", "Submit", "Send for Approval"]]],
    },
    {"doctype": "Notification", "filters": [["name", "like", "GI %"]]},
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
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Payment Entry": {
        "before_submit": "blueline.server_scripts.approval_enforcement.enforce_approval",
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Customer": {
        "after_insert": "blueline.server_scripts.customer_master.save_customer_tin",
        "on_update": "blueline.server_scripts.customer_master.save_customer_tin",
    },
    # Doctypes below post directly to the general/stock ledger for a company (confirmed
    # against this site's actual metadata, not assumed) and so are gated by each
    # company's Company COA Configuration.earliest_allowed_posting_date. See
    # posting_date_guard.py for the enforcement logic and DATE_FIELD_OVERRIDES for the
    # one doctype (Period Closing Voucher) whose relevant date isn't posting_date.
    "Purchase Invoice": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Journal Entry": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Stock Entry": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Delivery Note": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Purchase Receipt": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "POS Invoice": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "POS Closing Entry": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Subcontracting Receipt": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Asset Capitalization": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Exchange Rate Revaluation": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Invoice Discounting": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Period Closing Voucher": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Landed Cost Voucher": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
    "Petty Cash Voucher": {
        "validate": "blueline.server_scripts.posting_date_guard.enforce_earliest_posting_date",
    },
}

after_install = "blueline.setup.after_install"
after_migrate = "blueline.setup.after_migrate"
