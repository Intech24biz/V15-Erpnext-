# Blueline — Manual Testing Guide (Production)

**Site:** https://erpnext.intech24.biz
**Code version this guide was written against:** `blueline` branch `fix/client-review-hard-blocks` (commits `9ba85a1`–`5e0caba` on top of `79615c0`), plus the role changes made on 2026-10-08.
**Who this is for:** a person testing in the browser as real logged-in users. No scripts, no console.

> **Updated 2026-10-27 for the client-review fixes.** These are **not on production until that branch is deployed** — run the new checks only after deployment. What changed:
> - **No self-approval (all GI approval workflows):** the person who **created** a document, and the person who **sent it for approval**, can never approve it — any role, including System Manager. Message: *"You cannot approve a document you created or sent for approval."* Every two-person step below now uses two different logins.
> - **Commission approvals need two different people:** the same user can't tick both *Approved by Management* and *Approved by Technical*. Who ticked each box is now recorded, and both boxes are locked once the entry is Approved or Paid.
> - **Approved Sales Invoices can't be cancelled** — they're reversed with a **Credit Note** instead, which has its own number series (`BTAX-RET-…`) and goes through the same approval workflow. This changes the cleanup in Section 2.8.
> - New sections: **3.6** (self-approval), **3.7** (Credit Note instead of Cancel), and new checks in **2.4–2.6**.
>
> **Updated 2026-10-29 (branch `feature/credit-note-commission-approval-roles`, not deployed):**
> - **Credit Notes now adjust commission** (K11 resolved). Approving a Credit Note reduces the original invoice's unpaid commission entries in proportion to what was returned (a full return cancels them), and creates a negative **Deduction** entry for commission that was already paid. Cancelling the Credit Note undoes all of it. No ledger entries are involved. New section **2.9**; changed **2.8** step 5 and **3.7** step 12.
> - **Credit Notes are applied with Payment Reconciliation** (new **3.7 C**; 2.8 step 4 changed). Production's ERPNext has no "Update Outstanding for Self" option, so a Credit Note always stands on the customer's account until the accountant reconciles it against the invoice. **Commission is now released whenever the invoice's outstanding reaches 0 by any route** — payment, reconciliation, Journal Entry, in any order — and never earlier.
> - **No commission approval while the invoice is unpaid** (new **2.10**): neither tick, the Approve action, nor any other route to Approved is accepted — for any role — until the invoice's outstanding is 0. If a payment is undone later, untouched entries go back to Accrued; ticked, Approved or Paid ones keep their status and show a **Payment Warning**.
> - **Deduction entries need the two-person approval** (start in *Payment Received - Pending Approval*), and **a Credit Note whose commission can't be adjusted is refused** with *"Commission could not be adjusted for this Credit Note; nothing was changed. Contact the administrator."* — nothing is half-done. See 2.9 C and H.
> - **Approver roles are changed in the Workflow screen and stay changed.** Previously every update (bench migrate) silently put the shipped approver roles and notification recipients back. Workflows and pending-approval notifications are now only created if missing, never overwritten; only a System Manager can edit a workflow, and each change is recorded. New section **3.8**.

---

## 0. Read this first

### 0.1 Labels used in every step

| Label | Meaning |
|---|---|
| **[SAFE]** | Read-only. Nothing is created or changed. |
| **[REVERSIBLE]** | Creates something that you can fully delete afterwards (e.g. a Draft that is deleted). Leaves no trace. |
| **[PERMANENT]** | Creates a record that cannot be fully removed. It can be **cancelled** (and its accounting reversed), but the cancelled document, its number, and any ledger reversal stay in the system forever. A cleanup step is always given. |

### 0.2 Important warnings about testing on production

1. **This is the live company database.** Anything marked [PERMANENT] leaves a cancelled document behind.
2. **Sales Invoices use gazette-style Tax Invoice serial numbers** (format `26OCT_BLIN_00012`). Approving a test invoice consumes the next serial number. An approved invoice **can no longer be cancelled** — the only way to reverse it is a **Credit Note**, which is itself a permanent, approved document (with its own `BTAX-RET-…` number, so the tax-invoice sequence is not affected). Before doing any Sales Invoice step marked [PERMANENT], **get the accountant's OK** (or skip those steps and only do the [REVERSIBLE] parts).
3. Use **tiny amounts** (Rs. 1–100) for anything that posts to the ledger.
4. **Pending-approval notifications are "System Notifications"** — they appear under the **bell icon** (top-right) of the recipient users. Real users (Chris, office, sales, tech, the accountant) will see your test notifications. Warn them before you start.

### 0.3 Logging in as different users

- Production runs Frappe 15.5, which **does not have an "Impersonate" button**. To test as another user you need **that user's password**.
- Use a **separate browser profile or a private/incognito window per user** so sessions don't overwrite each other. Example: normal window = Administrator, incognito window 1 = office@gen-innov.com, a second browser = the accountant.
- Log in at https://erpnext.intech24.biz/login.

### 0.4 Who has which role (verified on production 2026-10-08)

| User | Relevant roles | Use in this guide as |
|---|---|---|
| `Administrator` | everything | admin checks |
| `ceo@gen-innov.com` (Chris A) | System Manager, GI Management, Technical Approver, Accounts Manager, Sales/Purchase roles | System Manager, approver, cancelling |
| `office@gen-innov.com` | GI Management, Technical Approver, Accounts User | approver (GI Management), Technical Approver |
| `mohamedsafras97831@gmail.com` (Accountant) | Financial Manager, Accounts Manager, Accounts User | Financial Manager |
| `sales@gen-innov.com` | GI Sales Dept (+ Sales/Purchase/Accounts User) | "normal" GI user |
| `tech@gen-innov.com` | GI Tech Dept (+ standard roles) | "normal" GI user (alternative) |
| `geninnov.tech2@gmail.com` | GI Sales Dept 2 (+ standard roles) | restricted user |
| `erpnext.sl@gmail.com`, `sales@globalintech.com.sg` | System Manager | — |

### 0.5 Known issues found while preparing this guide

These were confirmed before writing the guide. If you see them, it is **expected** — tick the step as "known issue", not "new bug".

_K1 (Financial Manager's "Mark as Paid" silently failing) and K2 (wrong-role approval tick silently reverting) were also found while preparing this guide and were fixed before testing began (commit `1e67389`)._

| # | Known issue | Where |
|---|---|---|
| K3 | **The Draft state is editable only by "GI Sales Dept 2"** in all approval workflows. After a GI Sales Dept / GI Management / GI Tech Dept user saves a draft, the form **may become read-only** for them. Record what you see. This also applies to a **Credit Note** draft (e.g. changing the returned quantity). | Sections 3, 3.7 |
| K4 | **Narrowed.** Outside the browser (via the API) a user with standard Submit permission can still submit **someone else's** Draft directly, skipping "Send for Approval". They can **no longer** do this to a document they created or sent (self-approval is blocked on every path, API included). Not testable in the browser. | Section 3 |
| K5 | **Narrowed.** Petty Cash Voucher still has the direct "Submit" shortcut (Draft → Approved) for GI Management / GI Sales Dept / GI Tech Dept, but it is now **refused on a voucher you created yourself** — it only works on someone else's voucher. | Section 4 |
| ~~K6~~ | **Fixed.** Self-approval is now refused for every role (see 3.6). | Section 3 |
| K10 | **"Approve" is still shown** in the Actions menu to the creator / sender of a document. Clicking it is refused with *"You cannot approve a document you created or sent for approval."* — the block is enforced on the server, the button is not hidden. | Sections 3.6, 3.7 |
| ~~K11~~ | **Resolved (2026-10-29 branch).** A Credit Note now adjusts the original invoice's commission entries instead of creating negative Accrued entries — see 2.9. | Sections 2.8, 2.9, 3.7 |
| K12 | **An approved Credit Note can still be cancelled** (it has no Tax Invoice Serial, so the cancel block doesn't apply to it). Pending client confirmation. Cancelling it now also restores the commission it adjusted (2.9 E). | Sections 2.9, 3.7 |
| K13 | **Deduction entries have no payout step yet.** A Deduction is created in **Payment Received - Pending Approval** and is approved like any commission entry (two different people). After that it stays **Approved**: **Mark as Paid** refuses it, and it shows as outstanding on the Sales Commission Register until netting against a payout is built. | Section 2.9 |
| K7 | **The VAT Dashboard page does not show the list of VAT accounts** — only totals, a chart and a monthly table. To see which accounts it uses, use the read-only URL in Section 5.4. | Section 5 |
| K8 | **"Earliest Allowed Posting Date" on the COA configuration is not enforced yet** (that guard is not deployed). You can fill it in, but nothing will block back-dated postings. Don't test enforcement. | Section 1 |
| K9 | **Blueline Enterprises has no default cash/bank account set**, so on Payment Entries you must pick "Account Paid To" by hand. (Filling "Default Cash Account" in the COA console is part of the long-term fix.) | Sections 2, 3 |

### 0.6 Where everything lives

A sidebar workspace **"Blueline Control Center"** has shortcuts to every feature below. Direct URLs are also given in each section.

---

## SECTION 1 — Centralised COA Mapping Console

**What it is:** one page that shows each company's key ledger/stock/currency settings (a "Company COA Configuration" record per company), with inline editing for authorised users.
**Current production state:** **0 companies configured.**

### 1.1 View the console (empty state) — as Administrator — [SAFE]

1. Log in as **Administrator** (or ceo@gen-innov.com).
2. Go to **https://erpnext.intech24.biz/app/coa-console**
   (or sidebar → *Blueline Control Center* → *COA Mapping Console*).
3. **Expected:**
   - Page title **"COA Configuration Console"**.
   - A green indicator **"Edit access"** near the title.
   - A **Refresh** button (top right).
   - Body text: **"No COA configurations available to you"** (because none exist yet).
4. **Wrong result:** an error popup, a "Not permitted" message, or a blank white page. Note the exact message.

### 1.2 Create the first real configuration — as Administrator — [PERMANENT, but editable/deletable]

The console itself has **no "create" button** — new configurations are created on the doctype form, then appear in the console.

> **Company to use:** _________________________ (fill in — e.g. `Blueline Enterprises Pvt Ltd`, `General Innovations (Pvt) Ltd`, or `Global Intech Pte Ltd`). Only ONE company per configuration. Agree the account choices with the accountant first; these are real settings.

1. Go to **https://erpnext.intech24.biz/app/company-coa-configuration/new**
2. Fill the fields (only **Company** is mandatory; leave anything you're unsure of blank):

   | Section | Field | What to enter |
   |---|---|---|
   | Financial & Balancing | **Company** * | the company chosen above (cannot be changed later) |
   | | Default Cash Account | a **leaf** account of type Cash belonging to that company |
   | | Default Bank Account | a leaf Bank account of that company |
   | | Temporary Opening Account | e.g. that company's "Temporary Opening" account |
   | | Default Cost Center | that company's main cost center (e.g. "Main - <abbr>") |
   | Stock & Valuation | Stock Adjustment Account | that company's stock adjustment account |
   | | Stock Received But Not Billed | that company's SRBNB account |
   | | Expenses Included In Valuation | that company's account |
   | | Default Valuation Method | `FIFO` (default) or `Moving Average` |
   | | Default Warehouse | a warehouse of that company (e.g. "Stores - <abbr>") |
   | Multi-Currency | Exchange Gain/Loss Account | that company's exchange gain/loss account |
   | | Foreign Currency Revaluation Account | optional |
   | | Inter Company Clearing Account | optional |
   | Guardrail | Earliest Allowed Posting Date | optional — **not enforced yet (K8)** |

3. Click **Save** (or Ctrl+S).
4. **Expected:** "Saved" toast; the record name becomes the company name.
5. **Validation checks (do these on purpose, then fix) — [SAFE, nothing saves]:**
   - Pick an account from a **different company** in any account field → Save → **Expected error:** `<Field label> "<account>" does not belong to Company <company>`.
   - Pick a **group** account (a folder-type account) → **Expected error:** `<Field label> "<account>" is a group account. Please select a leaf account.`
   - Pick a cost center or warehouse of another company → same "does not belong to Company" error.
   - **Wrong result:** it saves with another company's account.
6. Go back to **/app/coa-console** → click **Refresh**.
7. **Expected (configured state):** one panel for the company, a green **"Editable"** badge, each field showing its value (unset fields show **"Not set"**), and a **Save** button on the panel.

**Cleanup:** none needed if the values are real. To remove it: open the record at `/app/company-coa-configuration/<Company>` → **⋯ menu → Delete** (System Manager only).

### 1.3 Edit as Financial Manager — as `mohamedsafras97831@gmail.com` — [REVERSIBLE: change a value, then change it back]

1. Log in as the **accountant** (Financial Manager).
2. Open **/app/coa-console**.
3. **Expected:** indicator **"Edit access"**; the panel shows the **"Editable"** badge and a **Save** button.
4. Change one field (e.g. **Default Valuation Method** FIFO → Moving Average). Note the old value.
   (Safe to change: it is only stored on this configuration. It does **not** change any Item, stock balance, stock ledger entry or the global Stock Settings — confirmed by test on 2026-10-27.)
5. Click the panel's **Save**.
6. **Expected:** green message **"Saved COA configuration for <Company>"**; the value stays after **Refresh**.
7. Try an account from another company in an account field → **Save** → **Expected:** red message `... does not belong to Company ...` and nothing saved.
8. **Cleanup:** set the field back to its original value → **Save**.
9. **Wrong result:** "Not permitted", the Save button missing, or the change not persisting after Refresh.

### 1.4 View-only as a normal user — as `sales@gen-innov.com` — [SAFE]

1. Log in as **sales@gen-innov.com** (no Financial Manager / System Manager).
2. Open **/app/coa-console**.
3. **Expected:** indicator **"View only"** (grey); the company panel shows a grey **"Read-only"** badge; values are displayed as text; **no Save button** and no editable inputs.
4. **Wrong result:** an "Editable" badge or a Save button appears. (If a Save button appears and you click it, the server should still refuse with "Not permitted to update the COA configuration for this company" — note this as a UI bug.)

### 1.5 Company segregation — [PERMANENT setup: creates a test user + a User Permission; cleanup given]

Goal: a user restricted to one company sees only that company's configuration.

1. As **Administrator**, create a test user: **/app/user/new**
   - Email: `coa.test@gen-innov.com` (or any address you control)
   - First Name: `COA Test`
   - **Untick "Send Welcome Email"**
   - Save. In the **Roles** section tick **Accounts User** only. Save. Then **Set New Password** (⋯ menu / "Change Password" section) so you can log in.
2. Restrict them to a company that **has no configuration** (e.g. if you configured Blueline in 1.2, restrict to `General Innovations (Pvt) Ltd`):
   **/app/user-permission/new** → User: `coa.test@gen-innov.com`; Allow: `Company`; For Value: `General Innovations (Pvt) Ltd`; **Apply To All Document Types** ticked → Save.
3. Log in as `coa.test@gen-innov.com` → **/app/coa-console**.
4. **Expected:** **"No COA configurations available to you"** even though a configuration exists for another company. **Wrong result:** the other company's panel is visible.
5. As Administrator, edit that User Permission → change **For Value** to the company you configured → Save.
6. As `coa.test@...` → **Refresh** the console. **Expected:** that one company's panel, **"Read-only"** badge (they have no Financial Manager role), no Save.
7. **Cleanup:** delete the User Permission (`/app/user-permission`, filter by user → open → ⋯ → Delete), then disable the test user (open user → untick **Enabled** → Save) or delete it.

---

## SECTION 2 — Sales Commission (full lifecycle)

**How it works (so results make sense):**
- When a **Sales Invoice is submitted**, every invoice line is matched against **Sales Commission Rule** by **Item + Customer** (the invoice's "Sales Team" table is **ignored**). Priority: customer+item rule → item-only rule → customer-only rule → catch-all.
- **Every** rule matched at that level creates **its own Sales Commission Entry** (one sale can pay several people).
- Each entry records **Matched Sales Person** (whose rule matched) and **Commission Credited To** (that person's **direct parent** if the parent is a group, otherwise the person themself).
- Amount: *Percentage of Line Value* = % × line Amount (before tax); *Fixed Amount Per Unit* = rate × qty.
- Entry statuses: **Accrued** → (invoice fully paid) **Payment Received - Pending Approval** → (both approval boxes ticked, **by two different users**) **Approved** → **Paid**. Approved invoices can no longer be cancelled (they're reversed by Credit Note — see 2.8 and 2.9).
- **Credit Note:** when it is approved, each unpaid entry (Accrued / Pending Approval / Approved) on the returned line is reduced in proportion to the returned amount — a full return sets it to **Cancelled** with amount 0. A **Paid** entry is left as it is and a separate negative **Deduction** entry is created for the same person, ticked **Deduct from Next Payout**. Each change is listed in the entry's **Adjustments** table. Nothing posts to the ledger.
- **Every approval in this section needs two logins:** whoever creates and sends a document can't approve it. The steps below use **ceo@** to create/send and **office@** to approve.

### 2.1 View the 43 rules — as Administrator or the accountant — [SAFE]

1. Go to **https://erpnext.intech24.biz/app/sales-commission-rule** (or *Blueline Control Center* → *Sales Commission Rule*).
2. **Expected:** **43** rules in the list (count at the bottom/"43 of 43"), all **Enabled**. List columns include Sales Person, Company, Enabled, Commission Type, Rate. Use the sidebar filters (Sales Person, Customer, Item Code, Company, Enabled).
3. Open one, e.g. filter **Sales Person = J D SILVA** and **Customer = Cherish Biscuit Pvt. Ltd.** → open the row with **Item Code = ENM10018596** (ID `08785e8e83`).
4. **How to read it:**
   - **Sales Person** — who made the sale (`J D SILVA`).
   - **Customer / Item Code** — the rule applies only when this customer buys this item (blank = "any").
   - **Company** — `Blueline Enterprises Pvt Ltd`.
   - **Commission Type / Rate** — `Percentage of Line Value`, `3` → 3% of the line amount.
   - **Enabled** — ticked.
5. **Wrong result:** fewer/more than 43 rules, or rules for held items (none should exist for: 170xi4 - 300 DPI, 3811 DOD Water Based Black Ink, BL 080 1/2", BL110, BLZLWRFIPC 33mmX450M BLK, GI WR3811BK - HP, GI WR3913 BK - HP, SAVEMA 53C Thermal Printer Head). Search each in the Item Code filter — **expected: 0 rules**.

### 2.2 Single-payee sale → commission entry — as `ceo@gen-innov.com` — [PERMANENT — see warning 0.2.2; accountant's OK first]

1. Log in as **ceo@gen-innov.com**.
2. **https://erpnext.intech24.biz/app/sales-invoice/new**
3. Fill:
   - **Customer:** `Cherish Biscuit Pvt. Ltd.`
   - **Company:** `Blueline Enterprises Pvt Ltd`
   - **Date / Posting Date:** today; **Payment Due Date:** today
   - **Items** table, row 1: **Item Code** `ENM10018596`, **Quantity** `1`, **Rate** `100`
   - **Do not fill the "Sales Team" table** (it is ignored for commission).
4. Click **Save**. **Expected:** saved as Draft; the **Workflow State** shows **Draft**. Note the invoice number (e.g. `BTAX-000xx`) and the line **Amount** (should be 100.00; if a pricing rule changed the rate, use the actual Amount below).
5. Click **Actions → Send for Approval**. **Expected:** state **Pending Approval**; there is **no plain "Submit" button**; the **Sent for Approval By** field shows ceo@.
6. Still as ceo@: click **Actions → Approve**. **Expected:** refused — *"You cannot approve a document you created or sent for approval."* (ceo@ is System Manager; there is no exemption). State stays **Pending Approval**.
7. Log in as **office@gen-innov.com** → open the invoice → **Actions → Approve**. **Expected:** state **Approved**, document status **Submitted**, a **Tax Invoice Serial** is filled in.
8. Find the commission entry — either:
   - **https://erpnext.intech24.biz/app/sales-commission-entry?sales_invoice=BTAX-000xx** (replace with your number), or
   - **/app/sales-commission-register** → filter Status = Accrued → find your invoice in the table.
9. **Expected — exactly ONE entry:**
   | Field | Expected |
   |---|---|
   | Sales Invoice | your invoice |
   | Matched Sales Person | `J D SILVA` |
   | Commission Credited To | `Sales Team  LDA Perera` (note: two spaces in the name) |
   | Customer / Item | Cherish Biscuit Pvt. Ltd. / ENM10018596 |
   | Commission Rule | `08785e8e83` |
   | Commission Type | Percentage of Line Value |
   | Commission Amount | **3.00** (3% of 100) |
   | Status | **Accrued** |
10. **Wrong results:**
   - **No entry** → check **/app/error-log** for "Sales Commission: no matching rule (BTAX-… / ENM10018596)" and report.
   - **Commission Credited To = J D SILVA** → leader resolution is broken.
   - **Amount ≠ 3% of the line Amount** → calculation bug.
   - **More than one entry** → unexpected extra rule matched.

### 2.3 Payment → "Payment Received - Pending Approval" — as `ceo@gen-innov.com` — [PERMANENT]

1. Open your invoice → **Create → Payment** (button group top-right).
2. In the new Payment Entry:
   - **Payment Type:** Receive (pre-filled)
   - **Account Paid To:** pick a Blueline **Cash or Bank** account (must be chosen by hand — K9)
   - **Paid Amount:** the invoice's outstanding (pre-filled)
   - If the account is a Bank account: **Cheque/Reference No** `TEST`, **Cheque/Reference Date** today
3. **Save** → **Actions → Send for Approval** (as ceo@) → log in as **office@** → **Actions → Approve**. (ceo@ can't approve a payment they created — same rule as 2.2.)
4. **Expected:** Payment Entry submitted; the invoice's **Outstanding Amount = 0** and status **Paid**.
5. Re-open the commission entry. **Expected:** **Status = Payment Received - Pending Approval**.
6. **Notification check:** log in as **office@** and the **accountant** → bell icon. **Expected:** "Sales Commission Entry SCE-… pending your approval".
7. **Wrong result:** status still **Accrued** after the invoice shows Outstanding 0 → report.

### 2.4 Dual approval — the core test — two different people — [PERMANENT, part of the same test record]

The entry becomes **Approved** only when **both** boxes are ticked:
- **Approved by Management** — can be ticked by **Financial Manager** (accountant) or System Manager.
- **Approved by Technical** — can be ticked by **Technical Approver** (office@ or ceo@) or System Manager.

For a real two-person test use **office@ for Technical** and **the accountant for Management**.

**New — one person can never give both approvals (any role).** Do this first, on the same entry, while both boxes are unticked:

0a. Log in as **ceo@gen-innov.com** (System Manager — the only user who *can* tick both boxes) → open the entry → tick **both** boxes → **Update**.
    **Expected:** refused — *"Approved by Management and Approved by Technical must be given by two different users. ceo@gen-innov.com cannot give both approvals."* Reload: both boxes unticked.
0b. Still as ceo@: tick **only Approved by Technical** → **Update** → **Expected:** saved; the field **Technical Approval By** now shows `ceo@gen-innov.com`. Then tick **Approved by Management** as well → **Update** → **Expected:** the same "two different users" refusal.
0c. Untick **Approved by Technical** → **Update** → **Expected:** saved; **Technical Approval By** is cleared. The entry is back to both boxes unticked for the steps below.
    **Wrong results:** either save in 0a/0b succeeds; the entry becomes Approved.

**Safeguard check — "Approve" requires both boxes (new, added with the K1 fix).** The entry's **Actions → Approve** button must refuse unless both boxes are ticked. Do these as **the accountant** (or ceo@). office@ is Technical Approver only, so if office@ clicks Approve they get a *different* refusal ("You don't have permission to change Status. Required role: Financial Manager or System Manager.") — that is also correct, but it doesn't test this safeguard.

1. Log in as **the accountant** → open the commission entry (both boxes unticked).
2. **Safeguard, 0 boxes:** click **Actions → Approve**.
   **Expected:** refused with **"Both approvals are required before this entry can be Approved: tick Approved by Management and Approved by Technical."**; status stays **Payment Received - Pending Approval**. **Wrong result:** status becomes Approved.
3. Tick **Approved by Management** → click **Update** (top-right, appears after the change).
4. **Expected:** saved; **Status stays "Payment Received - Pending Approval"**. **Wrong result:** it jumps to Approved with only one box ticked.
5. **Safeguard, 1 box:** still as the accountant, click **Actions → Approve** again.
   **Expected:** the same **"Both approvals are required…"** refusal; status unchanged. **Wrong result:** status becomes Approved with only Management ticked.
6. Log in as **office@gen-innov.com** → open the same entry → reload.
7. **Expected:** "Approved by Management" shows ticked (read-only for office@).
8. Tick **Approved by Technical** → **Update**.
9. **Expected:** **Status = Approved** immediately. **Management Approval By** = the accountant's email, **Technical Approval By** = `office@gen-innov.com` (filled in by the system; nobody can type in these fields).
10. **Wrong results:** status still Pending with both ticked; or an error "Not allowed"; either "… Approval By" field empty or showing the wrong person.
11. **New — ticks are locked once Approved.** As **office@**: untick **Approved by Technical** → **Update**. **Expected:** refused — *"Approved by Technical cannot be changed once the entry is Approved."* As **ceo@** (System Manager): try to untick either box → same refusal. Reload: both still ticked, status still Approved.

### 2.5 Negative checks on the approval boxes — [SAFE: the attempt is refused, nothing changes]

Do these on the entry **before** step 2.4.8 (while "Approved by Technical" is still unticked), or on a second test entry:
- As **office@**: try to tick **Approved by Management** → **Update**. **Expected:** either the checkbox is greyed out and can't be ticked, or, if it can be ticked, **Update** is refused with a clear message: **"You don't have permission to change Approved by Management. Required role: Financial Manager or System Manager."** After reload the box is unchanged.
- As **the accountant**: try to tick **Approved by Technical** → **Update**. **Expected:** greyed out, or refused with **"You don't have permission to change Approved by Technical. Required role: System Manager or Technical Approver."**
- **Wrong results:** the other person's box stays ticked (two-person control broken), or it "saves" with no message and is silently unticked after reload (the old K2 behaviour has come back).

### 2.6 Mark as Paid — [PERMANENT]

> **Check this one carefully.** This is the **first real-world confirmation** of the accountant's "Mark as Paid" path: the fix was deployed when production had **zero** Sales Commission Entries, so it has only been verified in local tests, never on production.

1. As **the accountant**: open the Approved entry → **Actions → Mark as Paid**.
   **Expected:** **Status = Paid** — reload the page and confirm it is still Paid. The **Payment Entry** field on the commission entry stays **empty** (the browser has no way to link the payout payment; it's informational).
2. **Only if step 1 did not reach Paid:** as **ceo@gen-innov.com** (System Manager): **Actions → Mark as Paid** → **Expected:** **Status = Paid**. Record that step 1 failed.
3. **Wrong results:** after the accountant's Mark as Paid, the status is still **Approved** after reload (the K1 bug has come back), or an error appears.
4. **New — still locked once Paid.** As **ceo@**: try to untick either approval box → **Update**. **Expected:** refused — *"… cannot be changed once the entry is Paid."*

### 2.7 Multi-payee sale — as `ceo@gen-innov.com` — [PERMANENT]

This combination has **three** rules: the rep and two customer-side payees under the group lead **W Chaminda Priyalal**.

1. New Sales Invoice: **Customer** `CBL Foods International Pvt Ltd`; **Company** `Blueline Enterprises Pvt Ltd`; **Items** row: **Item Code** `BLZLWRFOPVC 33mmX450M BLK`, **Quantity** `2`, **Rate** `100`.
2. **Save → Actions → Send for Approval**, then as **office@** → **Actions → Approve.**
3. Open **/app/sales-commission-entry?sales_invoice=<this invoice>**.
4. **Expected — exactly THREE entries, all Accrued:**
   | Matched Sales Person | Commission Credited To | Type | Amount |
   |---|---|---|---|
   | M M M M PARIS | Sales Team  LDA Perera | 3% of line | **6.00** (3% × 200) |
   | W.B.Prasanna | W Chaminda Priyalal | Rs. 65 per unit | **130.00** (65 × 2) |
   | M.Madusha Darshani | W Chaminda Priyalal | Rs. 65 per unit | **130.00** (65 × 2) |
5. **Wrong results:** only one entry; an "ambiguous rules" Error Log; Prasanna/Darshani credited to themselves or to Sales Team LDA Perera.
   (Two entries credited to **W Chaminda Priyalal** is expected: one per rep. Each **Matched Sales Person** appears only once.)
6. (A "sub-team" example — a rep whose parent is a sub-team lead, e.g. H P DE SILVA → L C L PERERA — has **no live rule on production**, so it can't be tested here without creating a rule.)

### 2.8 Cleanup for Section 2 — **changed: invoices are reversed by Credit Note, not cancelled**

> Get the accountant's OK first: each Credit Note is a permanent, approved document.

1. **Commission entries that are Approved or Paid** (from 2.4/2.6): as **ceo@**, open each → **Cancel** → confirm. **Expected:** Status **Cancelled**.
2. **Payment Entry** (from 2.3): as **ceo@**, open → **Cancel**. **Expected:** Cancelled; the invoice goes back to Unpaid/Overdue.
3. **Sales Invoices** (2.2 and 2.7): as **ceo@**, open → **Cancel**. **Expected: refused** — *"Sales Invoice BTAX-… has been approved and issued Tax Invoice Serial …, so it cannot be cancelled. Issue a Credit Note instead: open the invoice and use Create > Return / Credit Note."* This is the new, correct behaviour.
4. Reverse each invoice with a Credit Note exactly as in **3.7 B** (ceo@ creates and sends, office@ approves), then **apply it to the invoice with Payment Reconciliation (3.7 C)**. **Expected:** after the reconciliation the original invoice shows Outstanding **0** and status **Credit Note Issued**, and keeps its number and Tax Invoice Serial. (Before the reconciliation it still shows its full outstanding — that is normal on production's ERPNext.)
5. **Commission:** once the full Credit Note is approved, the original invoice's commission entries that weren't paid show **Status Cancelled, Commission Amount 0**; a Paid entry stays Paid and gets a **Deduction** entry (see 2.9). No entries appear under the Credit Note's own number (`/app/sales-commission-entry?sales_invoice=BTAX-RET-…` is empty).
6. What remains forever: the approved invoices (and their tax serial numbers), the approved Credit Notes (`BTAX-RET-…`), the cancelled payment, the commission entries, and the ledger entries.

### 2.9 Credit Note → commission adjustment — [PERMANENT — accountant's OK first; each Credit Note is an approved document]

Use the multi-payee invoice from 2.7 (three entries: 6.00, 130.00, 130.00) and the single-payee invoice from 2.2. ceo@ creates and sends each Credit Note, office@ approves it (as in 3.7 B). **These Credit Notes are the 2.8 cleanup for those two invoices** — do 2.9 instead of 2.8 step 4, not as well.

**A. Partial return of unpaid commission**
1. On the 2.7 invoice (entries still **Accrued**): **Create → Return / Credit Note** → change the quantity from `-2` to `-1` → Save → Send for Approval → (office@) Approve.
2. Open `/app/sales-commission-entry?sales_invoice=<2.7 invoice>`. **Expected:** the same three entries, now **3.00, 65.00, 65.00**, still **Accrued**. Each has **Original Commission Amount** 6.00 / 130.00 / 130.00, and an **Adjustments** row: Credit Note = your `BTAX-RET-…`, Adjustment **Reduced**, Commission Before/After, **Adjusted By** = office@ (the approver).
3. Open one entry → the timeline at the bottom shows *"Commission reduced by … by Credit Note BTAX-RET-…"* and a version change on Commission Amount.
4. **Wrong results:** new negative entries under the Credit Note's number; the amounts unchanged; Adjusted By empty.

**B. Full return → cancelled**
5. On the same invoice, issue a second Credit Note for the remaining quantity (`-1`) and approve it. **Expected:** all three entries **Cancelled**, Commission Amount **0**, two Adjustments rows (*Reduced*, *Cancelled*). Docstatus stays **Submitted** (so cancelling the Credit Note can bring them back).

**C. Paid commission → Deduction entry**
6. Use the 2.2 invoice whose entry is **Paid** (from 2.6). Issue and approve a full Credit Note.
7. **Expected:** the Paid entry is **unchanged** (still Paid, 3.00), with an Adjustments row *Deduction Created* linking a new entry. That new entry: **Entry Type = Deduction**, **Commission Amount −3.00**, **Deduct from Next Payout** ticked, **Credit Note** = your `BTAX-RET-…`, **Against Commission Entry** = the paid entry, same Matched Sales Person and Credited To, Status **Payment Received - Pending Approval**. The accountant and office@ get the usual "pending your approval" bell notification.
8. **Approve the deduction like any commission entry (2.4):** as ceo@, try ticking both boxes → refused (*"… must be given by two different users …"*). Then the accountant ticks **Approved by Management**, office@ ticks **Approved by Technical** → **Expected:** Status **Approved**, both "… Approval By" names filled in, ticks locked.
8a. As the accountant: **Actions → Mark as Paid** on the approved deduction → **Expected:** refused — *"… is a deduction. Deductions are taken off a payout, not marked as Paid."* (K13). It stays Approved.

**D. Register**
9. Open **/app/sales-commission-register** (company Blueline). **Expected:** a table **Outstanding Deductions (deduct from next payout)** listing `Sales Team  LDA Perera` with **Amount to Deduct 3.00** and the deduction entry, shown with its **Approved** badge (approved but not yet taken off a payout still counts as outstanding). The status cards do **not** include the deduction. In the main table, the deduction row shows Type **Deduction**, and reduced entries show *"was …"* under the amount.

**E. Cancel a Credit Note → everything restored (K12)**
10. As ceo@: open the Credit Note from step 1 → **Cancel**. **Expected:** the three entries go back to their amounts before that Credit Note; any that it cancelled return to their previous status. Its Adjustments rows stay, ticked **Reversed**, with **Reversed By**. Cancelling the Credit Note from step 6 cancels its Deduction entry (status Cancelled) and the deduction disappears from the register.

**F. The lock still holds**
11. As ceo@ (System Manager) or the accountant: on an adjusted entry, try to change **Status** to/from Cancelled → **Expected:** *"Status can only be set to or from Cancelled by approving or cancelling a Credit Note."* Commission Amount, Original Commission Amount and the Adjustments table can't be edited by anyone (read-only; the API refuses "Not allowed to change … after submission").

**G. Ledger** — open each Credit Note → **View → Accounting Ledger**: only the Credit Note's own sales/receivable reversal; nothing for commission (commission entries never post to the ledger).

**H. A failed commission adjustment blocks the Credit Note — [not testable in the browser]**
A failure can't be forced from the screen; it is covered by the automated test (a failure is injected halfway through the adjustment). What a user would see: **Approve** on the Credit Note is refused with *"Commission could not be adjusted for this Credit Note; nothing was changed. Contact the administrator."* The Credit Note stays **Pending Approval** with no ledger entries, no commission entry changes, and an entry appears in **/app/error-log** titled *"Sales Commission credit note adjustment failed: BTAX-RET-…"* (written within about a minute, by the scheduler). If you ever see this message, report it with the Error Log entry.

### 2.10 No approval while the invoice is unpaid — [A: SAFE; B: PERMANENT]

Expected message every time: *"This commission cannot be approved while the invoice still has an outstanding amount. Wait until the invoice is fully paid or credited."* It applies to every role — ceo@ (System Manager) and Administrator included.

**A. Unpaid or partly paid invoice — [SAFE: every attempt is refused]**
1. Approve an invoice as in 2.2 but **don't pay it** (or pay only part of it, as in 2.3 with a smaller Paid Amount). Its commission entry stays **Accrued**.
2. As **the accountant**: tick **Approved by Management** → **Update** → **Expected:** the message above; the box is unticked after reload. Same as **office@** with **Approved by Technical**, and as **ceo@** with either box.
3. As **ceo@**: change **Status** to *Approved* (if the field is editable for you) → **Update** → **Expected:** the same message.
4. **Wrong results:** any tick is saved, or the entry becomes Approved.

**B. Undone payment after release — [PERMANENT]**
5. Pay the invoice in full (2.3) → the entries go to **Payment Received - Pending Approval**. As the accountant tick **Approved by Management** on **one** entry only.
6. As **ceo@**: **Cancel** the Payment Entry.
7. **Expected:**
   - the entries **nobody had ticked** go back to **Accrued**, with a timeline comment *"Moved back to Accrued: Payment Entry … was cancelled, and invoice … has … outstanding again…"*;
   - the **ticked** entry keeps its status and tick, shows a red **Payment Warning** at the top of the form (*"…This entry is already ticked, so its status was not changed. Check it before any commission is paid."*), and the same text in its timeline; office@ can't tick the second box (message above). An entry that was already **Approved** or **Paid** is treated the same way: status unchanged, warning shown.
8. Pay the invoice in full again. **Expected:** the Accrued entries are released again; the Payment Warning disappears; the second approval can now be given.
9. **Wrong results:** a ticked/Approved entry changes status; an untouched entry stays in Pending Approval while the invoice owes money; the warning stays after the invoice is paid again.

**C. Settled by a Credit Note** — after 3.7 C brings the invoice to 0 through reconciliation (with or without a payment), approval works normally. **Deduction entries** (2.9 C) are not affected by this rule: they can be approved even if the original invoice owes money again.

---

## SECTION 3 — Approval workflows (Quotation, Purchase Order, Sales Invoice, Payment Entry)

**Rules now in force (same for all four):**
- **Draft → [Send for Approval] → Pending Approval:** GI Sales Dept 2, GI Management, GI Sales Dept, GI Tech Dept.
- **Pending Approval → [Approve] → Approved (submitted):** GI Management, GI Sales Dept, GI Tech Dept.
- **No direct "Submit" from Draft for anyone in the GI roles.**
- GI Sales Dept 2 is additionally blocked by a server check from submitting directly.
- **New: nobody can approve a document they created or sent for approval** — any role, System Manager included (K10: the Approve action still appears, but is refused). The form shows who sent it in **Sent for Approval By**.
- **New: an approved Sales Invoice can't be cancelled** — reverse it with a Credit Note (3.7).
- On "Pending Approval", users with GI Management / GI Sales Dept / GI Tech Dept get a bell notification.

**Recommended approach to limit permanent data:** do the **full cycle (including Approve) only on the Quotation** (no ledger impact). For Purchase Order, Sales Invoice and Payment Entry, go as far as **Pending Approval**, confirm **Approve is offered** to the approver, then **do not approve** — delete the document instead. Optional full-approve steps are marked.

### 3.1 Quotation

**A. As `sales@gen-innov.com` (GI Sales Dept) — [REVERSIBLE until approved]**
1. **https://erpnext.intech24.biz/app/quotation/new**
2. Fill: **Quotation To** `Customer`; **Customer** e.g. `Cherish Biscuit Pvt. Ltd.`; **Company** `Blueline Enterprises Pvt Ltd`; **Date** today; **Valid Till** today + 7 days; **Items**: **Item Code** `ENM10018596`, **Quantity** `1`, **Rate** `100`.
3. **Save.** **Expected:** Workflow State **Draft**.
   - **Note K3:** if the form becomes read-only after saving, record it.
4. Look at the top-right. **Expected:** an **Actions** dropdown containing **only "Send for Approval"**. There must be **no "Submit" button** and no "Submit" in Actions.
   **Wrong result:** a Submit button/action is present → the bypass fix did not apply.
5. **Actions → Send for Approval.** **Expected:** Workflow State **Pending Approval**; still not submitted (docstatus Draft).

**B. As `office@gen-innov.com` (GI Management) — [PERMANENT once approved]**
6. Check the **bell icon**. **Expected:** "Quotation QTN-… pending your approval".
7. Open the quotation. **Expected:** **Actions → Approve** is available.
8. **Actions → Approve.** **Expected:** Workflow State **Approved**; status **Submitted** (Open).
9. **Wrong result:** Approve missing, or it approves but stays Draft.

**C. Self-approval check — [SAFE: the attempt is refused]**
10. As `office@`: create another quotation (same fields) → Save → **Actions** shows only **Send for Approval** (no Submit) → Send for Approval.
11. Still as `office@`: **Actions → Approve**. **Expected:** refused — *"You cannot approve a document you created or sent for approval."*; state stays **Pending Approval** (K10: the action is shown but refused). **Wrong result:** it becomes Approved.
12. Delete this second quotation (⋯ → Delete).

**D. As `geninnov.tech2@gmail.com` (GI Sales Dept 2) — [REVERSIBLE]**
13. Create a quotation (same fields) → Save. **Expected:** Actions shows only **Send for Approval**; no Submit.
14. Send for Approval → **Expected:** Pending Approval, and **no Approve** action for this user.
15. Delete it (as the creator, or as Administrator: ⋯ → Delete).

**Cleanup (3.1):** the approved quotation from step 8: open → **Cancel** (as office@ or ceo@). Drafts/pending ones: ⋯ → **Delete**.

### 3.2 Purchase Order — [REVERSIBLE if not approved]

1. As **sales@gen-innov.com**: **https://erpnext.intech24.biz/app/purchase-order/new**
2. Fill: **Supplier** any existing supplier; **Company** `Blueline Enterprises Pvt Ltd`; **Required By** today + 7 days; **Items**: any purchasable item, **Quantity** `1`, **Rate** `100`; if asked, **Set Target Warehouse** to a Blueline warehouse.
3. Save → **Expected:** Draft; Actions = only **Send for Approval**; **no Submit**.
4. **Send for Approval** → **Expected:** Pending Approval.
5. As **office@**: open it → **Expected:** **Approve** available. **Do not approve** (or, optional [PERMANENT]: Approve → expect Submitted/To Receive and Bill, then Cancel it).
6. **Cleanup:** ⋯ → **Delete** (pending documents are still drafts and can be deleted).

### 3.3 Sales Invoice — [REVERSIBLE if not approved]

> Use a customer/item with **no commission rule** so nothing accrues even if you approve, e.g. Customer `Mr.Aruna` and any item not in the rules list.

1. As **sales@gen-innov.com**: **/app/sales-invoice/new** → **Customer** (no-rule customer), **Company** Blueline, **Items** one line, qty 1, rate 1.
2. Save → **Expected:** Draft; only **Send for Approval**; no Submit.
3. **Send for Approval** → **Pending Approval**.
4. As **office@**: **Approve** is offered → **do not approve** (approving consumes a tax invoice serial — warning 0.2.2).
5. **Cleanup:** ⋯ → **Delete**.

### 3.4 Payment Entry — [REVERSIBLE if not approved]

1. As **sales@gen-innov.com**: **/app/payment-entry/new**
2. Fill: **Payment Type** `Receive`; **Company** Blueline; **Party Type** `Customer`; **Party** any customer; **Account Paid To** a Blueline cash/bank account (K9); **Paid Amount** `1`; if Bank: **Cheque/Reference No** `TEST`, **Reference Date** today.
3. Save → **Expected:** Draft; only **Send for Approval**; no Submit.
4. **Send for Approval** → **Pending Approval**.
5. As **office@**: **Approve** offered → **do not approve**.
6. **Cleanup:** ⋯ → **Delete**.

### 3.5 GI Sales Dept 2 across the other three — [REVERSIBLE]

Repeat 3.2–3.4 steps 1–4 as **geninnov.tech2@gmail.com** (shortcut: just Purchase Order + Payment Entry). **Expected each time:** only **Send for Approval**, **no Submit**, and **no Approve** once pending. Delete afterwards.

### 3.6 Self-approval is blocked for creator *and* sender, every role — [SAFE: every attempt is refused; delete the drafts afterwards]

Use a **Purchase Order** (no ledger impact even if something goes wrong). Expected message every time: *"You cannot approve a document you created or sent for approval."*

**A. Creator, System Manager**
1. As **ceo@gen-innov.com**: new Purchase Order (as in 3.2) → Save → **Actions → Send for Approval**.
2. Still as ceo@: **Actions → Approve** → **Expected:** refused. ceo@ holds System Manager — there is no exemption.

**B. Sender who is not the creator**
3. As **geninnov.tech2@gmail.com**: new Purchase Order → Save (do **not** send it).
4. As **office@**: open it → **Actions → Send for Approval**. **Expected:** Pending Approval; **Sent for Approval By** = `office@gen-innov.com`.
5. Still as office@: **Actions → Approve** → **Expected:** refused (office@ sent it).
6. As **ceo@** (neither creator nor sender): **Approve** is offered → **do not approve**; delete both POs (⋯ → Delete). (Optional [PERMANENT]: approve as ceo@ → expect Approved, then Cancel the PO.)

**C. A different approver still works** — already covered by 3.1 B (sales@ creates, office@ approves).

**D. Petty Cash direct "Submit" (K5)** — see 4.2 step 5.

**Wrong results:** any of the refused steps approves the document; a different message appears (note it exactly).

### 3.7 Credit Note instead of Cancel (Sales Invoice) — [A: SAFE; B: PERMANENT — accountant's OK first]

**A. Cancel is refused on an approved invoice — [SAFE]**
1. As **ceo@gen-innov.com** (System Manager, can normally cancel anything): open any **approved** Sales Invoice that has a **Tax Invoice Serial** (e.g. the one from 2.2) → **Cancel** → confirm.
2. **Expected:** refused — *"Sales Invoice BTAX-… has been approved and issued Tax Invoice Serial …, so it cannot be cancelled. Issue a Credit Note instead: open the invoice and use Create > Return / Credit Note."* The invoice stays **Submitted / Approved**.
3. **Draft and Pending Approval invoices are unaffected:** create a draft invoice (3.3 steps 1–3) → ⋯ → **Delete** → **Expected:** deleted as before.

**B. Issue a Credit Note — [PERMANENT]**
4. As **ceo@**: open the approved invoice → **Create → Return / Credit Note**. A new Sales Invoice opens with **Is Return** ticked, **Return Against** = the original, negative quantities.
5. **Before saving:** for a partial return, reduce the quantities now. (Production's ERPNext has no "Update Outstanding for Self" option — if a newer version shows it, leave it **ticked** so these steps apply unchanged.)
6. **Save.** **Expected:** name in the **credit-note series** — `BTAX-RET-0000x` for Blueline (`TAX-RET-…` for `TAX-` invoices, `SVAT-RET_…` for `SVAT-` invoices). It must **not** take a `BTAX-0000x` number. Workflow State **Draft**. (K3: the form may be read-only after saving.)
7. Still as ceo@: **Actions → Send for Approval** → **Pending Approval**. Then **Actions → Approve** → **Expected:** refused (self-approval).
8. As **office@**: **Actions → Approve**. **Expected:** Credit Note **Approved / Submitted**, status **Return**; the **Tax Invoice Serial** field on the Credit Note is **empty** (Credit Notes don't take a tax-invoice serial).
9. Check the **original invoice**: same number, same **Tax Invoice Serial**, still **Approved / Submitted**, and its **Outstanding is unchanged** for now. The Credit Note shows a **negative** Outstanding (e.g. −100.00): the credit sits on the customer until it is applied (C below).
10. **Ledger:** on the Credit Note → **View → Accounting Ledger**. **Expected:** the reverse of the invoice — Debit Sales (and VAT, if any), Credit the customer's receivable, same amounts.
11. **Numbering:** create and approve the next ordinary invoice (if one is due anyway) → **Expected:** it takes the next `BTAX-` number right after the last ordinary invoice — no gap, nothing skipped for the Credit Note.
12. **Commission:** see 2.8 step 5 and 2.9. **Cancelling the Credit Note (K12):** possible; it restores the commission (2.9 E).

**C. Apply the Credit Note to the invoice (Payment Reconciliation) — as the accountant — [PERMANENT]**
13. Go to **/app/payment-reconciliation** (Accounting → Payment Reconciliation). Fill **Company**, **Party Type** `Customer`, **Party** (the invoice's customer), **Receivable / Payable Account** (the invoice's *Debit To*, e.g. `Trade Receivable - BEPL`). Click **Get Unreconciled Entries**.
14. In **Payments**, tick the row for your Credit Note (Reference Type *Sales Invoice*, `BTAX-RET-…`). In **Invoices**, tick the original invoice. Click **Allocate**, check the **Allocated Amount** (the Credit Note's amount, or the invoice's outstanding if that is smaller), then click **Reconcile**.
15. **Expected:** the original invoice's Outstanding drops by the credited amount; the Credit Note's Outstanding becomes **0**. If that brings the invoice to **0**, its status is **Credit Note Issued**. (Behind the scenes ERPNext posts a Journal Entry of type *Credit Note*; it only moves the balance between the two documents.)
16. **Commission release:** if the invoice's Outstanding is now 0 (whatever got it there — a payment, this reconciliation, or both, in either order), its *Accrued* commission entries move to **Payment Received - Pending Approval** at that moment. While anything is still outstanding they stay Accrued. A fully returned invoice has nothing to release (its commission was cancelled in 2.9 B).
17. **If the customer has already paid in full:** don't reconcile against the invoice; the credit stays on the customer's account to be used on a later invoice (same screen, tick the later invoice) or refunded (Payment Entry, type *Pay*, against the Credit Note).

**Wrong results:** the Cancel in A goes through; the Credit Note gets a `BTAX-0000x` number or a Tax Invoice Serial; the original's number/serial changes; the creator can approve the Credit Note; after C the invoice is settled but its commission is still Accrued.

### 3.8 Changing approver roles — [REVERSIBLE: make a change, check it, change it back]

Use the **Purchase Order** workflow (no ledger impact). The steps a System Manager follows are in the user manual (new section 5.4).

**A. Only a System Manager can change a workflow — [SAFE]**
1. As **office@** (GI Management, not System Manager): open **/app/workflow/GI Purchase Order Approval**. **Expected:** read-only or "Not permitted"; no Save. **Wrong result:** office@ can save it.

**B. Add an approver role**
2. As **ceo@** (System Manager): open **/app/workflow/GI Purchase Order Approval** → **Transitions** table → **Add Row**: State `Pending Approval`, Action `Approve`, Next State `Approved`, Allowed `GI Sales Dept 2`, **Allow Self Approval** ticked (like the other Approve rows) → **Save**.
3. As **tech@**: new Purchase Order (as in 3.2) → Save → Send for Approval.
4. As **geninnov.tech2@gmail.com** (GI Sales Dept 2): open it. **Expected:** **Actions → Approve** is now offered. Don't approve (or, optional [PERMANENT]: approve, then cancel the PO).
5. As **geninnov.tech2@**: create your own Purchase Order → Send for Approval → **Actions → Approve**. **Expected:** refused — *"You cannot approve a document you created or sent for approval."* The new role gets no exemption.
6. On the workflow, scroll to the bottom (timeline / version history). **Expected:** an entry by ceo@ showing the added transition row.

**C. The change survives an update**
7. Ask whoever deploys to run the next update (`bench migrate`) — or skip on production and rely on the local test. Afterwards, reopen the workflow. **Expected:** the `GI Sales Dept 2` Approve row is still there. **Wrong result:** it disappeared (the old overwrite has come back).

**D. Remove the role again (cleanup)**
8. As ceo@: in the Transitions table tick the `GI Sales Dept 2` Approve row → **Delete** → **Save**. As geninnov.tech2@: open the pending PO from step 3. **Expected:** no Approve action. Delete both POs (⋯ → Delete).

---

## SECTION 4 — Petty Cash Voucher

**What it does:** a small cash payment voucher. On final approval it **automatically creates and submits a Journal Entry**: Debit *Expense Account*, Credit *Petty Cash Account*. Cancelling the voucher cancels that Journal Entry.

**Workflow (GI Petty Cash Approval):** Draft → **Send for Approval** (GI Sales Dept 2) → Pending Approval → **Approve** (GI Management, GI Tech Dept) → Approved (submitted). **K5:** GI Management / Sales / Tech still also have a direct **Submit** from Draft on this doctype, but **not on a voucher they created themselves**. The creator and the sender can never approve the voucher.

### 4.1 Validation checks — as `geninnov.tech2@gmail.com` — [SAFE: nothing saves]

1. **https://erpnext.intech24.biz/app/petty-cash-voucher/new**
2. Try saving with **Amount** `0` → **Expected:** "Amount must be greater than zero".
3. Pick a **Petty Cash Account** that is not of type Cash/Bank (e.g. an expense account) → **Expected:** "Petty Cash Account must be of type Cash or Bank".
4. Pick an account belonging to **another company** → **Expected:** "<Petty Cash Account / Expense Account> <account> does not belong to Company <company>".

### 4.2 Create and send for approval — as `geninnov.tech2@gmail.com` — [REVERSIBLE until approved]

1. New Petty Cash Voucher. Fill:
   | Field | Value |
   |---|---|
   | Series | `PCV-.YYYY.-` (default) |
   | Company | `Blueline Enterprises Pvt Ltd` |
   | Posting Date | today (default) |
   | Requested By | you (default) |
   | Mode of Payment | `Cash` |
   | Petty Cash Account | a Blueline account of type **Cash** |
   | Payee | `Manual test` |
   | Expense Account | a Blueline expense (leaf) account, e.g. miscellaneous/sundry expenses |
   | Cost Center | Blueline main cost center |
   | Amount | `1` |
   | Purpose | `Manual test - will be cancelled` |
2. **Save.** **Expected:** name like `PCV-2026-00001`; Workflow State **Draft**; Journal Entry field empty.
3. **Actions → Send for Approval.** **Expected:** Workflow State **Pending Approval**, not submitted.
4. **Notification:** as **office@** (GI Management) or **tech@** (GI Tech Dept) → bell → **Expected:** "Petty Cash Voucher PCV-… pending your approval". (Recipients: GI Management and GI Tech Dept only.)
5. **New — direct Submit on your own voucher is refused [SAFE]:** as **office@**, create a second voucher (same fields) → Save → **Actions → Submit**. **Expected:** refused — *"You cannot approve a document you created or sent for approval."* Delete that voucher (⋯ → Delete, as ceo@ if office@ can't).

### 4.3 Approve → Journal Entry created — as `office@gen-innov.com` — [PERMANENT]

1. Open the voucher → **Actions → Approve**.
2. **Expected:** Workflow State **Approved**; status **Submitted**; the **Journal Entry** field now shows a link (e.g. `ACC-JV-2026-…`).
3. Click the Journal Entry link. **Expected:**
   - Entry Type **Cash Entry**, status **Submitted**, same posting date and company.
   - Accounts table: **Debit** 1.00 to your Expense Account (with your cost center); **Credit** 1.00 to your Petty Cash Account.
   - User Remark: "Petty Cash Voucher PCV-…: Manual test - will be cancelled".
4. GL impact: on the Journal Entry → **View → Ledger** (or Accounting Ledger). **Expected:** two GL rows, Dr expense 1.00 / Cr cash 1.00.
5. **Wrong results:** voucher submitted but Journal Entry field empty; JE in Draft; amounts/accounts swapped.

### 4.4 Cleanup — as `ceo@gen-innov.com` (needs Accounts Manager / System Manager; office@ cannot cancel)

1. Open the voucher → **Cancel** → confirm.
2. **Expected:** voucher **Cancelled**; open the linked Journal Entry → **Cancelled** too; ledger shows reversing entries.
3. **Wrong result:** the Journal Entry is still Submitted after the voucher is cancelled.

---

## SECTION 5 — VAT Dashboard — [SAFE, read-only throughout]

1. Log in as **ceo@gen-innov.com** or the **accountant** (needs read access to the General Ledger).
2. **https://erpnext.intech24.biz/app/vat-dashboard** (or *Blueline Control Center* → *VAT Dashboard*).
3. The page has filters **Company**, **From Date**, **To Date**, buttons **Refresh** and **Export to Excel**. Below: summary cards (**Total Output VAT**, **Total Input VAT (Recoverable)**, **Net VAT Payable** or **Net VAT Refund**, and SVAT if any), a chart **"Monthly Output vs Input vs Net VAT"**, and a table **"Monthly VAT Summary"**.

### 5.1 Each company (From = 2025-10-08, To = 2026-10-08)

| Company | Expected cards | Expected monthly table |
|---|---|---|
| General Innovations (Pvt) Ltd | Output **429,000.00**, Input 0.00, **Net VAT Payable 429,000.00** | 2026-08: Output 429,000.00, Input 0.00, Net 429,000.00 |
| Blueline Enterprises Pvt Ltd | Output **0.00**, Input **1,458,401.43**, **Net VAT Refund 1,458,401.43** | 2026-08: Output **−564,871.43**, Input 893,530.00, Net **−1,458,401.43** |
| Global Intech Pte Ltd | all 0.00 | **"No Data"** |

(These were the values on 2026-10-08; new postings will change them.)

**Why Blueline's cards and table look different (expected, not a bug):** both show the same **net** (−1,458,401.43). The **table** shows each month's raw movement — the output VAT account has a net *debit*, so output shows as −564,871.43. The **cards** move any output account with a net debit balance into "Input", so cards show Output 0 and Input 564,871.43 + 893,530.00 = 1,458,401.43.

### 5.2 Export
Click **Export to Excel** with Blueline selected. **Expected:** a CSV download with Month / Output VAT / Input VAT / Net VAT columns and a Total row. With Global Intech selected: message "No data to export".

### 5.3 Wrong results
Error popup / "Not permitted to view GL Entry" (for an accounts user), blank page, or totals that don't match the table's net.

### 5.4 Confirm the "private vehicle" fix (the page does not list accounts — K7)

While logged in, open these URLs in the browser (read-only; they return the dashboard's raw data as JSON):

- Global Intech:
  `https://erpnext.intech24.biz/api/method/blueline.blueline.page.vat_dashboard.vat_dashboard.get_vat_data?company=Global%20Intech%20Pte%20Ltd&from_date=2000-01-01&to_date=2030-12-31`
  **Expected:** `"summary"` all zeros, `"monthly": []`, `"account_detail": []` — and **no "Transport - private vehicle expenses - I24" anywhere**.
- General Innovations:
  `https://erpnext.intech24.biz/api/method/blueline.blueline.page.vat_dashboard.vat_dashboard.get_vat_data?company=General%20Innovations%20(Pvt)%20Ltd&from_date=2000-01-01&to_date=2030-12-31`
  **Expected:** `account_detail` lists GIL VAT accounts **that have postings** (e.g. `Vat Control Account - GIL`). Note: `account_detail` only lists accounts with ledger activity in the range, so `SVAT 18% - GIL`, `VAT 15% - GIL`, `VAT 18% - GIL` appear only if they have postings. (Server-side, all four GIL accounts — SVAT 18%, VAT 15%, VAT 18%, Vat Control Account — were confirmed as detected on 2026-10-08.)
- **Wrong result:** "Transport - private vehicle expenses - I24" appears for Global Intech.

---

## SECTION 6 — Role assignments sanity check — [SAFE, read-only; do NOT click Save on these users]

> **Do not press Save on ceo@'s user record unnecessarily** — it's safe now (no Role Profile), but there's no reason to.

1. Log in as **Administrator**. Go to **https://erpnext.intech24.biz/app/user**.
2. Open **mohamedsafras97831@gmail.com** → **Roles** section (Settings tab / "Roles & Permissions").
   **Expected:** **Financial Manager** ticked (also Accounts Manager, Accounts User).
3. Open **office@gen-innov.com** → Roles. **Expected:** **GI Management** and **Technical Approver** ticked.
4. Open **ceo@gen-innov.com**:
   - **Role Profile** field: **empty**. **Wrong result:** "System Administrator" shown.
   - Roles: **GI Management**, **Technical Approver**, **System Manager**, Accounts Manager, and the rest of the previous admin set ticked.
5. Optional cross-check: **/app/has-role?role=Technical%20Approver** may not be browsable; instead use **/app/user?enabled=1** and open each user. Expected holders:
   | Role | Holders |
   |---|---|
   | Financial Manager | mohamedsafras97831@gmail.com |
   | Technical Approver | ceo@gen-innov.com, office@gen-innov.com |
   | GI Management | ceo@gen-innov.com, office@gen-innov.com |

---

## Checklist summary

Tick **P** (pass), **F** (fail), or **K** (known issue from 0.5).

| # | Check | P | F | K |
|---|---|---|---|---|
| 1.1 | COA console loads; empty state "No COA configurations available to you" | ☐ | ☐ | |
| 1.2 | First COA configuration created; wrong-company / group-account errors shown | ☐ | ☐ | |
| 1.3 | Accountant (Financial Manager) can edit + save in console | ☐ | ☐ | |
| 1.4 | Normal user sees "View only"/"Read-only", no Save | ☐ | ☐ | |
| 1.5 | Company-restricted user sees only their company | ☐ | ☐ | |
| 2.1 | 43 enabled rules; none for held items | ☐ | ☐ | |
| 2.2 | Single-payee invoice → 1 entry, J D SILVA → Sales Team LDA Perera, 3.00, Accrued; ceo@ refused approving own invoice | ☐ | ☐ | |
| 2.3 | Payment (approved by office@) → entry "Payment Received - Pending Approval" + notifications | ☐ | ☐ | |
| 2.4a | **New:** one user (ceo@, System Manager) can't tick both boxes — in one save or one after the other | ☐ | ☐ | |
| 2.4 | One tick = still pending; both ticks (2 people) = Approved; "… Approval By" fields show the two users | ☐ | ☐ | |
| 2.4s | Safeguard: Actions → Approve refused with 0 boxes and with 1 box ("Both approvals are required…") | ☐ | ☐ | |
| 2.4l | **New:** ticks locked once Approved (office@ and ceo@ refused) | ☐ | ☐ | |
| 2.5 | Wrong-person tick refused with a clear "Required role" message | ☐ | ☐ | |
| 2.6 | Mark as Paid by the accountant → Paid (first production confirmation); ticks still locked | ☐ | ☐ | |
| 2.7 | Multi-payee invoice → 3 entries with correct credited-to and amounts | ☐ | ☐ | |
| 2.8 | Cleanup: invoice Cancel refused; reversed by Credit Note; unpaid commission Cancelled, none under the Credit Note | ☐ | ☐ | |
| 2.10 | **New:** no tick / Approve / Approved while the invoice owes money (any role); undone payment → untouched entries back to Accrued, ticked/Approved ones keep status with a Payment Warning, cleared when paid again | ☐ | ☐ | |
| 2.9 | **New:** Credit Note reduces unpaid commission in proportion / cancels on full return; paid → Deduction entry (Pending Approval, two different approvers, can't be marked Paid); register shows outstanding deductions, approved ones included; cancelling the Credit Note restores all; status lock holds; no ledger posting | ☐ | ☐ | ☐ (K12/K13) |
| 3.1 | Quotation: no Submit; Send for Approval → Approve submits; SD2 unchanged; office@ refused approving own quotation | ☐ | ☐ | ☐ (K3/K10) |
| 3.2 | Purchase Order: no Submit; Send for Approval; Approve offered | ☐ | ☐ | |
| 3.3 | Sales Invoice: no Submit; Send for Approval; Approve offered | ☐ | ☐ | |
| 3.4 | Payment Entry: no Submit; Send for Approval; Approve offered | ☐ | ☐ | |
| 3.5 | GI Sales Dept 2: Send for Approval only, never Approve | ☐ | ☐ | |
| 3.6 | **New:** creator (System Manager) and sender both refused on Approve; a third user is offered Approve | ☐ | ☐ | ☐ (K10) |
| 3.7A | **New:** Cancel refused on an approved invoice, message points to Credit Note; drafts still deletable | ☐ | ☐ | |
| 3.7B | **New:** Credit Note numbered `BTAX-RET-…`, no tax serial, goes through Send for Approval → Approve (creator refused), reverses the ledger; original keeps number/serial | ☐ | ☐ | ☐ (K3/K12) |
| 3.7C | **New:** Credit Note applied with Payment Reconciliation → invoice outstanding drops (Credit Note Issued at 0); commission released only when nothing is left to pay, payment and reconciliation in either order | ☐ | ☐ | |
| 3.8 | **New:** only System Manager can edit a workflow; an added approver role works, its holder still can't self-approve; change is in the version history and survives an update; removal takes effect | ☐ | ☐ | |
| 4.1 | Petty Cash validation messages | ☐ | ☐ | |
| 4.2 | Petty Cash → Pending Approval + notification; direct Submit refused on own voucher | ☐ | ☐ | ☐ (K5) |
| 4.3 | Approve → Journal Entry auto-created, Dr expense / Cr cash | ☐ | ☐ | |
| 4.4 | Cancel voucher → JE cancelled | ☐ | ☐ | |
| 5.1 | VAT dashboard figures per company match the table above | ☐ | ☐ | |
| 5.2 | Export to Excel works | ☐ | ☐ | |
| 5.4 | "Transport - private vehicle expenses - I24" absent for Global Intech | ☐ | ☐ | |
| 6 | Roles: accountant = Financial Manager; ceo@ & office@ = GI Management + Technical Approver; ceo@ has no Role Profile | ☐ | ☐ | |
