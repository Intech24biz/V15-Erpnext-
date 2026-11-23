# Blueline: release history

Each release is a tag on `main` in https://github.com/Intech24biz/V15-Erpnext-.git. The **rollback point** of a release is the code and database to return to if it has to be undone (procedure in the Technical Handover Document, [BLUELINE_TECHNICAL_HANDOVER.pdf](BLUELINE_TECHNICAL_HANDOVER.pdf), section 14).

| Release | Commit | Deployed | Rollback point |
|---|---|---|---|
| release-2026-11-24 | `3af81ac` | 2026-11-24 | code `6884679` (release-2026-11-23-docs) + backup `20261124_041635-erpnext_intech24_biz` (copies in `/root/blueline-release-2026-11-24-backup/`); no data migration |
| release-2026-11-23 | `4e12923` | 2026-11-23 | code `c55b9a9` (release-2026-11-02) + backup `20261123_050021-erpnext_intech24_biz` (copies in `/root/blueline-release-2026-11-23-backup/`) |
| release-2026-11-02 | `c55b9a9` | 2026-11-03 | code `8a548e5` (release-client-review-1) + backup `20261103_003529-erpnext_intech24_biz` (copies in `/root/blueline-release-2026-11-02-backup/`) |
| release-client-review-1 | `8a548e5` | 2026-10-29 | code `79615c0` + backup `20261029_081159` |

## release-2026-11-24 (`3af81ac`)

Every amount on the custom pages now uses its own company's currency, symbol and number format. This covers:
- the VAT Dashboard and its export
- the Sales Commission Register
- the Business KPI Dashboard
- My Dashboard
- the Quotation History Dashboard
- the commission entry screens and messages
- Credit Note comments

Where a page covers several companies, it shows one section per currency and never adds different currencies together.

No data migration. Rolling back the code alone is enough: return to `6884679` (release-2026-11-23-docs); the pre-deploy backup set `20261124_041635` is kept in `/root/blueline-release-2026-11-24-backup/`.

## release-2026-11-23 (`4e12923`)

Fixes after the pre-delivery review (branch `fix/petty-cash-and-commission-messages`, from release-2026-11-02 `c55b9a9`). The deploy migrate ran one new patch.

- **Petty Cash Voucher approval.** Approving a voucher failed with "Cost Center … does not belong to Company …" when the voucher's company was not the site's default company. The Journal Entry created on approval now takes its cost centre from the voucher's own company: the expense line uses the cost centre chosen on the voucher, or else the company's Default Cost Center; the petty cash line uses the company's Default Cost Center. If the company has no Default Cost Center, approval stops with a message naming the company. A cost centre of another company is refused when the voucher is saved.
- **Cancel on an approved Sales Invoice with commission.** On an invoice with a Sales Commission Entry, Cancel showed a generic "Cancel All Documents … no permission" dialog. It now shows the same message as on any approved invoice: *Cancel Not Allowed — Issue a Credit Note*.
- **Financial Manager and the commission list.** Filtering the Sales Commission Entry list by sales person failed for the Financial Manager role ("You do not have Read or Select Permissions for Sales Person"). The role now has *Select* on Sales Person. It can pick and filter by a sales person but still cannot open Sales Person records. This turns Sales Person's permissions into custom permissions, as Role Permission Manager does; the existing rules are kept.

## release-2026-11-02 (`c55b9a9`)

Client review release 2:
- deductions netted from commission payouts, including the zero-net Mark as Paid with no Payment Entry
- the VAT Dashboard's raw ledger totals and its *Ledger discrepancies* panel
- posting-date guard v2: Earliest Allowed Posting Date per company, on 18 ledger document types, with System Manager override recorded
- workflow snapshot and drift check (see [WORKFLOW_CHANGES.md](WORKFLOW_CHANGES.md))
- Business KPI and My Dashboard pages
- document storage by fiscal year
- training notes for Landed Cost Vouchers and service invoicing
- user manual sections 3.2a, 3.4 and 5.5

## release-client-review-1 (`8a548e5`)

Client review release 1:
- nobody can approve a document they created or sent for approval
- the two commission approvals must come from two different people
- an approved Sales Invoice is corrected with a Credit Note, never cancelled
- Credit Notes adjust sales commission
- Mark as Paid is tied to the payout's Payment Entry

Earlier changes are in the git history.
