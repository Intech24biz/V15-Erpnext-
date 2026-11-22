# Blueline: technical handover

**For:** the technical team who will run, deploy and maintain the Blueline app.

## 1. What it is

`blueline` is a Frappe app installed on top of ERPNext. It holds the customisations for Blueline Enterprises (Pvt) Ltd and General Innovations (Pvt) Ltd. All business data lives in ERPNext; the app adds the following.

- **Approvals.** The GI approval workflows (Draft → Pending Approval → Approved) on Quotation, Purchase Order, Sales Invoice, Payment Entry and Petty Cash Voucher. Nobody may approve a document they created or sent for approval, and only a System Manager may change a workflow.
- **Tax invoices.** A Tax Invoice serial is issued at approval. An approved Sales Invoice can never be cancelled; it is corrected with a Credit Note, which has its own number series.
- **Sales commission.** A commission entry is accrued when the invoice is approved. It is released for approval when the invoice is fully paid and needs a two-person approval. Mark as Paid links it to the payout's Payment Entry. A Credit Note adjusts it or creates a deduction, and deductions are netted from the next payout.
- **Posting-date guard.** Each company can set an *Earliest Allowed Posting Date*. Earlier postings are refused on 18 ledger document types, unless a System Manager saves them, and that override is recorded.
- **Petty Cash Voucher.** A voucher posts a Journal Entry when it is approved.
- **Pages.**
  - VAT Dashboard
  - Business KPI Dashboard
  - My Dashboard
  - COA Configuration Console
  - Sales Commission Register
  - Quotation History Dashboard
- **Document storage by fiscal year.** Attachments are filed in File Manager under `Home/Fiscal Year <FY>/<Company>/<Category>`.

The user-facing behaviour is described in the User Manual. Text changes per release are in [USER_MANUAL_UPDATES.md](USER_MANUAL_UPDATES.md).

## 2. Code and versions

- Repository: https://github.com/Intech24biz/V15-Erpnext-.git. `main` is what production runs; each release is a tag on `main` (see [RELEASE_HISTORY.md](RELEASE_HISTORY.md)).
- Production runs **Frappe v15.5.0, ERPNext v15.6.1, Python 3.11**. Try changes on a copy running these versions before deploying.
- Install on a new site:

  ```bash
  bench get-app blueline https://github.com/Intech24biz/V15-Erpnext-.git
  bench --site <site> install-app blueline
  bench --site <site> migrate
  ```

## 3. Where things are in the code

| Path | What |
|---|---|
| `blueline/hooks.py` | Document events (which functions run on which documents), form scripts, fixtures, install and migrate hooks. No scheduled jobs. |
| `blueline/server_scripts/` | Approval rules (`self_approval`, `approval_enforcement`, `workflow_guard`), tax invoice serial and cancel rule, sales commission, posting-date guard, customer TIN. |
| `blueline/blueline/doctype/` | Petty Cash Voucher, Sales Commission Entry / Rule / Adjustment, Company COA Configuration, Quotation History. |
| `blueline/blueline/page/` | The dashboard and console pages. |
| `blueline/public/js/` | Form scripts (`sales_invoice.js`: Cancel on an invoice with commission goes straight to the server's Credit Note message). |
| `blueline/document_folders.py` | Fiscal-year folders and filing of attachments. |
| `blueline/fixtures/` | Custom Fields, Roles, Workflow States and Actions, Workspace (re-imported on every migrate). |
| `blueline/setup_data/` | The GI workflows and their notifications, seeded insert-only (see [WORKFLOW_CHANGES.md](WORKFLOW_CHANGES.md)). |
| `blueline/patches.txt`, `blueline/patches/` | One-off data and permission changes, run once per site by `bench migrate`. |

Roles added by the app: GI Management, GI Sales Dept, GI Sales Dept 2, GI Tech Dept, Financial Manager, Technical Approver. The GI roles drive the workflows only. Users also need the standard ERPNext roles (Sales User, Purchase User, Accounts User and so on) for the documents they work on.

## 4. Production

- Site **erpnext.intech24.biz**. The bench is at `/home/administrator/frappe-bench`; run bench as the `administrator` user (`sudo -u administrator -H bench …`).
- The app checkout is `apps/blueline`. Its `main` tracks `main` on GitHub, and deploys use a fast-forward pull.
- Production keeps only its last 4 scheduled backup sets, so copy each deploy backup somewhere that is kept (previous ones are in `/root/blueline-release-<release>-backup/`).

## 5. Deploying a release

1. Check the server checkout is clean and on the expected release:

   ```bash
   cd /home/administrator/frappe-bench/apps/blueline
   git status --porcelain
   git describe --tags
   ```

2. Take a backup and copy it to a kept folder. Record its path in [RELEASE_HISTORY.md](RELEASE_HISTORY.md) as the rollback backup.

   ```bash
   bench --site erpnext.intech24.biz backup --with-files
   ```

3. Check the workflows before the change; note any difference it reports:

   ```bash
   bench --site erpnext.intech24.biz execute blueline.workflow_sync.check_drift
   ```

4. Pull, migrate and restart:

   ```bash
   git pull --ff-only
   bench --site erpnext.intech24.biz migrate
   bench restart
   ```

5. Run the workflow check again. It must report the same as in step 3.
6. Tag the release on `main` and push the tag.

## 6. Rollback

1. Put the code back to the previous release's commit (its *rollback point* in [RELEASE_HISTORY.md](RELEASE_HISTORY.md)):

   ```bash
   cd /home/administrator/frappe-bench/apps/blueline
   git checkout <rollback commit>
   bench --site erpnext.intech24.biz migrate
   bench restart
   ```

2. Restore the database only if the release changed data that the older code cannot use. A restore loses everything entered since the backup.

   ```bash
   bench --site erpnext.intech24.biz restore <database backup> --with-private-files <private files backup> --with-public-files <public files backup>
   ```

For the release after release-2026-11-02, rolling back the code to `c55b9a9` is enough. Its one data change is the Financial Manager *Select* permission on Sales Person, which the older code ignores. It can be removed in Role Permission Manager if wanted.

## 7. Configuration to know about

- **Default company and currency.** The site's default company is Global Intech Pte Ltd and its default currency is USD. Pages that start from the user's default company therefore open on Global Intech: the VAT Dashboard, the Sales Commission Register and others. Amounts show with a `$` sign even for the LKR companies. Each user can set their own default company under *Session Defaults*.
- **Default Cost Center on each company.** A Petty Cash Voucher posts to its company's Default Cost Center. A company without one cannot have vouchers approved.
- **Receivable accounts.** ERPNext invoices a customer against a *Receivable*-type account: the customer's own account for that company, or else the company's Default Receivable Account.
  - Blueline Enterprises' default, *Trade Receivable - BEPL*, is set up as a *Current Asset* account, not Receivable.
  - General Innovations has no Receivable account.
  - Until this is corrected in the chart of accounts, invoices can only be saved for customers that have their own receivable account for the company.
- **Commission rules.** An invoice line that matches no Sales Commission Rule is skipped. The skip is noted in the Error Log ("Sales Commission: no matching rule …"). This is expected and is not a failure.

## 8. Other documents

- [RELEASE_HISTORY.md](RELEASE_HISTORY.md): releases, commits and rollback points.
- [USER_MANUAL_UPDATES.md](USER_MANUAL_UPDATES.md): text changes to the User Manual per release.
- [WORKFLOW_CHANGES.md](WORKFLOW_CHANGES.md): changing the GI workflows and notifications without drift.
- [TRAINING_LANDED_COST_AND_SERVICE_INVOICING.md](TRAINING_LANDED_COST_AND_SERVICE_INVOICING.md): Landed Cost Vouchers and service invoicing.
