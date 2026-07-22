from . import __version__ as app_version

app_name = "blueline"
app_title = "Blueline"
app_publisher = "NovixCore — Sohail Zafar"
app_description = "ERPNext customisation for Blueline Enterprises & General Innovations (Sri Lanka)"
app_email = "novixcore@gmail.com"
app_license = "MIT"
app_version = app_version

# Required Apps
required_apps = ["erpnext"]

# Includes in <head>
# ------------------
# include js, css files in header of desk.html
# app_include_css = "/assets/blueline/css/blueline.css"
# app_include_js = "/assets/blueline/js/blueline.js"

# Fixtures — export these doctypes when running bench export-fixtures
fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [["module", "=", "Blueline"]]
    },
    {
        "doctype": "Print Format",
        "filters": [["module", "=", "Blueline"]]
    },
    {
        "doctype": "Server Script",
        "filters": [["module", "=", "Blueline"]]
    },
]

# Document Events
# ---------------
doc_events = {
    "Sales Invoice": {
        "before_submit": "blueline.blueline.server_scripts.tax_invoice_serial.generate_serial_number",
    },
    "Customer": {
        "after_insert": "blueline.blueline.server_scripts.customer_master.save_customer_tin",
        "on_update": "blueline.blueline.server_scripts.customer_master.save_customer_tin",
    }
}

# Scheduled Tasks
# ---------------
# scheduler_events = {
#     "daily": [
#         "blueline.tasks.daily"
#     ],
# }

# Testing
# -------
# before_tests = "blueline.install.before_tests"

# Installation
# ------------
after_install = "blueline.setup.after_install"
after_migrate = "blueline.setup.after_migrate"
