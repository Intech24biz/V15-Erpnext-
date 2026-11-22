# Blueline — ERPNext Custom App

Custom Frappe/ERPNext application for:
- **General Innovations (Pvt) Ltd** (GIIN)
- **Blueline Enterprises (Pvt) Ltd** (BLIN)

## Features
- Sri Lanka Gazette Tax Invoice print formats (EOG 03-0219, effective July 2026)
- Custom fields for TIN, SVAT, branch code, bank details
- Auto-generating invoice serial numbers (YYMMM_QQQQ_XXXXX)
- Approval workflows with self-approval blocking; approved invoices corrected with a Credit Note
- Sales commission: accrual, two-person approval, payout, Credit Note deductions and netting
- Earliest Allowed Posting Date per company, Petty Cash Vouchers, VAT and KPI dashboards
- Attachments filed by fiscal year, company and category

## Documentation
- [docs/BLUELINE_TECHNICAL_HANDOVER.pdf](docs/BLUELINE_TECHNICAL_HANDOVER.pdf) — Technical Handover Document: architecture, configuration, install, backup and restore, deploy and rollback, release history.
- [docs/BLUELINE_USER_MANUAL.pdf](docs/BLUELINE_USER_MANUAL.pdf) — User Manual.
- [docs/RELEASE_HISTORY.md](docs/RELEASE_HISTORY.md) — releases, commits and rollback points.

## Versions
Production runs, and this app is used on:

| Component | Version |
|---|---|
| Frappe | 15.5.0 |
| ERPNext | 15.6.1 |

## Installation
From the bench folder, as the bench user, on a bench with Frappe 15 and ERPNext installed on the target site:

```bash
bench get-app https://github.com/Intech24biz/V15-Erpnext-.git --branch main
bench --site <site> install-app blueline
bench --site <site> migrate
bench --site <site> clear-cache
bench restart        # or, on a supervisor setup: sudo supervisorctl restart all
```

## After installing
1. Open the desk and check that the **Blueline Control Center** workspace lists its shortcuts.
2. Install has created the roles, workflows and notifications (insert-only, from `blueline/setup_data/`) and imported the fixtures.
3. In the accounts: add the Payable account for Blueline Enterprises, and make sure each company has a **Default Cost Center** (Petty Cash Vouchers post to it) and a **Receivable** account for invoicing.
4. In the COA Console, fill in each company's Company COA Configuration (default accounts and, if wanted, the Earliest Allowed Posting Date).
5. Assign the approver roles (GI Management, GI Sales Dept, GI Sales Dept 2, GI Tech Dept, Financial Manager, Technical Approver) together with the standard ERPNext roles each user needs.

Changing workflows on an existing site: see [docs/WORKFLOW_CHANGES.md](docs/WORKFLOW_CHANGES.md).

The repository's test suites (`blueline/tests`) need a fresh test site set up for them; they do not run against production defaults.

## Developer
**Sohail Zafar — NovixCore**

## License
MIT
