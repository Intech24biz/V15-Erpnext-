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
        "filters": [["name", "in", ["Pending Approval", "Approved"]]],
    },
    {
        "doctype": "Workflow Action Master",
        "filters": [["name", "in", ["Approve", "Send for Approval"]]],
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
    },
    "Payment Entry": {
        "before_submit": "blueline.server_scripts.approval_enforcement.enforce_approval",
    },
    "Customer": {
        "after_insert": "blueline.server_scripts.customer_master.save_customer_tin",
        "on_update": "blueline.server_scripts.customer_master.save_customer_tin",
    }
}

after_install = "blueline.setup.after_install"
after_migrate = "blueline.setup.after_migrate"
