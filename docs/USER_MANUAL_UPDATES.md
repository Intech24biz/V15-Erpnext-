# Blueline — User Manual: text changes for the client-review fixes

**Applies to:** *Blueline — User Manual* dated Oct 8, 2026 (13 pages).
**Reason:** three behaviours changed on branch `fix/client-review-hard-blocks`:

1. nobody can approve a document they created or sent for approval;
2. one person can't give both commission approvals;
3. an approved Sales Invoice is corrected with a Credit Note, not cancelled.

Added from branch `feature/credit-note-commission-approval-roles` (update the manual only once that branch is deployed too):

4. a Credit Note adjusts the sales commission on the invoice automatically (new 3.2a);
5. a System Manager changes who can approve in the Workflow screen, and the change is kept (new 5.4).

Added on `release/client-review-1`:

6. Credit Notes are applied to the invoice with Payment Reconciliation (9.10, rewritten);
7. commission can only be approved once its invoice is fully paid or credited (3.3, new paragraphs).

Added on `feature/final-items`:

8. Mark as Paid links the payout's Payment Entry (new 3.4);
9. the VAT Dashboard's raw-totals switch explains itself under the cards (VAT Dashboard section).

Added on `release/client-review-2`:

10. documents can't be dated before the company's Earliest Allowed Posting Date, except by a System Manager (new 5.5).

Each block below says exactly which part of the manual it replaces or adds to. Text in quotes is the **current** wording, for locating it. Everything under "New text" is ready to paste. Update the manual only once the branch is deployed to production.

Notes for the editor are marked **[Editor]** and are not part of the manual.

---

## Section 2 — Who Can Do What

### 2a. Replace the box "Why two roles are needed for commission."

**New text:**

> **Why two people are needed for commission.** A sales commission payout only goes through once two *different* people have signed it off — one for Management (the Financial Manager) and one for Technical (a Technical Approver). The system records who gave each sign-off and will not accept both from the same person, whatever their role. This is a deliberate two-person check, covered in Section 3.

### 2b. Roles table — replace these cells

| Row | Column | New text |
|---|---|---|
| System Manager | What they can do | Full access everywhere. Manages users and settings, and can cancel most documents — but **not** an approved Sales Invoice (those are corrected with a Credit Note, see 5.3). Like everyone else, cannot approve a document they created or sent for approval. |
| GI Management | What they can do | Approves Quotations, Purchase Orders, Sales Invoices (including Credit Notes) and Payment Entries once they're sent for approval — but never one they created or sent themselves. Also a Technical Approver on commission. |
| GI Sales Dept / GI Tech Dept | What they can do | Creates and sends Quotations, Purchase Orders, Sales Invoices (including Credit Notes) and Payment Entries for approval. Can approve documents sent by others, but never one they created or sent themselves. |

### 2c. Add this paragraph directly after the roles table

**New text:**

> **The one rule that applies to everyone.** You can never approve a document that you created, or that you sent for approval — no matter which roles you hold, System Manager included. Another person must approve it. If you try, the system refuses with: *"You cannot approve a document you created or sent for approval."*

---

## Section 3.2 — The life cycle of a commission entry

### Replace the paragraph "If the original sale is ever cancelled, any commission entry that hasn't yet been paid is automatically cancelled with it."

**New text:**

> An approved Sales Invoice can no longer be cancelled; it is corrected with a Credit Note instead (Section 5.3).

### Add a new section 3.2a directly after 3.2 (from branch `feature/credit-note-commission-approval-roles`)

**New text:**

> **3.2a When goods come back: Credit Notes and commission**
>
> When a Credit Note is approved against an invoice, the system adjusts the commission on that invoice by itself. Nobody needs to do anything.
>
> - **Commission not yet paid out** (Accrued, Payment Received – Pending Approval, or Approved): the amount goes down in proportion to what was returned. If half the line comes back, the commission halves. If the whole line comes back, the entry is **Cancelled** and its amount becomes zero.
> - **Commission already paid**: the paid entry stays exactly as it was. The system creates a separate **Deduction** entry for the same person with a negative amount — the share of the commission for the goods that came back. It is marked **Deduct from Next Payout**. A deduction is signed off exactly like a commission entry: it starts at *Payment Received – Pending Approval*, and two different people tick **Approved by Management** and **Approved by Technical** (section 3.3).
>
> Each entry keeps its **Original Commission Amount**, and its **Adjustments** table lists every Credit Note that changed it: the amount before and after, and who approved the Credit Note. Nobody can edit these by hand, and approval ticks are never changed.
>
> If the Credit Note is later cancelled, everything is put back: reduced amounts are restored, cancelled entries go back to their earlier status, and its Deduction entries are cancelled. The Adjustments rows stay, marked **Reversed**.
>
> Commission entries never post anything to the accounts. Only the Credit Note itself changes the ledger.
>
> **Outstanding deductions** are listed per person at the top of the **Sales Commission Register**, in three columns:
>
> - **Awaiting Approval (won't come off yet)** — not yet signed off by two people; nothing takes these off a payout.
> - **Comes Off Next Payout** — Approved, and they fit into the person's Approved commission that is waiting to be paid (shown under their name as *Approved commission*), if all of it is paid out on one payout.
> - **Approved, Too Large to Fit Yet** — Approved, but they don't fit into that commission; they wait until there is enough.
>
> Each deduction entry is labelled with its column. Deductions are not included in the status totals.
>
> **Deductions come off the next payout by themselves.** When one of a person's commission entries is marked Paid (section 3.4), the system goes through that person's **Approved** deductions for the same company, **oldest first** (by date, then entry number), and takes each one off **whole** if it fits: the person's commission on that payout, less the deductions already taken off, must not go below zero. A deduction that doesn't fit is **skipped** — it stays Approved and waits for a later payout — and the system carries on with the next one, so a **later, smaller deduction can come off before an older, larger one**. Deductions still awaiting approval are never taken off. Each deduction taken off is marked **Paid** with the same Payment Entry and leaves the Outstanding Deductions list.
>
> **When the deductions cancel the commission exactly.** If the deductions taken off add up to exactly the commission (net 0.00), there is nothing to pay out — and ERPNext can't record a payment of 0.00. Leave **Payment Entry** empty and use **Actions → Mark as Paid**: the commission entry and the deductions are all marked **Paid** with no Payment Entry, and each one's timeline says *"Fully offset by deductions …"*. In every other case a Payment Entry is required.
>
> A deduction can't be marked Paid by hand, and once it has been taken off, the Credit Note that created it can no longer be cancelled.
>
> If the commission can't be adjusted for some reason, the Credit Note is **not approved**. The approver sees *"Commission could not be adjusted for this Credit Note; nothing was changed. Contact the administrator."* Nothing has changed — not the Credit Note, not the accounts, not the commission — so the administrator can fix the cause and the Credit Note can then be approved as normal.

**[Editor]** The "come off the next payout by themselves" paragraph is from branch `feature/commission-deduction-netting`; use it only once that branch is deployed.

---

## Section 3.3 — The two-person approval (dual sign-off)

### Replace the whole of 3.3

**New text:**

> **3.3 The two-person approval (dual sign-off)**
>
> Once a commission entry reaches "Payment Received – Pending Approval", it needs two separate ticks before it can move to Approved:
>
> - **Approved by Management** — ticked by the Financial Manager (the accountant), or a System Manager.
> - **Approved by Technical** — ticked by a Technical Approver, or a System Manager.
>
> **The two ticks must come from two different people.** The system records who ticked each box — you'll see the names in **Management Approval By** and **Technical Approval By** on the entry. Nobody can type in these fields. If the same person tries to tick the second box, or both at once, the system refuses. This applies to every role, including a System Manager, who is otherwise allowed to tick either box.
>
> Each person can only tick the box that matches their own role: a Financial Manager cannot tick the Technical box, and a Technical Approver cannot tick the Management box. If someone tries to approve the entry with only one box ticked, the system refuses and says both approvals are required first.
>
> Once the second box is ticked by the second person, the entry becomes Approved immediately. There is no separate "Approve" button to click afterwards.
>
> **Ticks are locked once approved.** When an entry is Approved, or later Paid, neither box can be unticked or re-ticked by anyone. While the entry is still pending, a box can be unticked, for example if it was ticked by mistake. Its "Approval By" name is then cleared.
>
> **Only once the invoice is paid.** Nobody — whatever their role — can tick either box or approve a commission entry while its invoice still has anything left to pay. The system checks the invoice at that moment and refuses with: *"This commission cannot be approved while the invoice still has an outstanding amount. Wait until the invoice is fully paid or credited."* An invoice counts as paid when nothing is left outstanding, whether through payments, a Credit Note applied to it (Payment Reconciliation, 9.10), or both.
>
> **If a payment is cancelled later.** When the invoice owes money again, entries that nobody had ticked yet go back to **Accrued** and become ready again automatically once the invoice is fully paid. Entries that were already ticked, Approved or Paid keep their status; they show a red **Payment Warning** at the top, and a note in their history, so the accountant can check them before any commission is paid. The warning disappears when the invoice is fully paid again. Deduction entries (3.2a) are not affected by these rules.

---

## Section 3.4 — Paying commission out (from branch `feature/final-items`)

### Add a new section 3.4 after 3.3 (replaces any text saying Mark as Paid only changes the status)

**New text:**

> **3.4 Paying commission out: Mark as Paid**
>
> A commission entry is marked **Paid** only together with the payment that paid it out. First record the payout as usual: a **Payment Entry** of type **Pay** — to the sales person (as an Employee) or, for an outside agent, to their Supplier record — sent for approval and approved by another person.
>
> Then, as the Financial Manager, on each **Approved** commission entry the payout covers:
>
> 1. In **Payment Entry**, choose the payout. Only submitted Payment Entries of type Pay for the same company are offered.
> 2. Click **Update**, then **Actions → Mark as Paid**.
>
> One payout can cover several commission entries, as long as their commission adds up to no more than the amount the payout paid; the entry that would go over is refused. Once an entry is Paid, its Payment Entry can't be changed by anyone, and the payout can't be cancelled while Paid entries point to it.
>
> **Deductions** (3.2a): when you mark an entry Paid, the person's Approved deductions that fit are taken off the same payout automatically (oldest first; one that doesn't fit is skipped and a later one may still be taken), so record the payout for the commission **minus** the deductions that will come off.
>
> To know that amount, use the register's **Comes Off Next Payout** column, not the whole Outstanding Deductions list: deductions *Awaiting Approval* or *Too Large to Fit Yet* will **not** come off. The column assumes all of the person's Approved commission is paid on **one** payout. If you pay their entries on separate payouts, each Mark as Paid only fits deductions into the commission on that payout, so less may come off at a time.
>
> If the payout turns out smaller than the commission minus what actually comes off, Mark as Paid is refused (*"… more than was paid"*) and nothing changes. The confirmation after Mark as Paid names the deductions that were taken off.
>
> **Nothing to pay (net 0.00):** if the deductions that come off equal the commission exactly, skip step 1 — leave **Payment Entry** empty and use **Actions → Mark as Paid** (3.2a). Any other amount needs a Payment Entry.

**[Editor]** The company needs a Payable account to pay commission from (for example *Commission payable*); the accountant sets this up once.

---

## Section 5 — Document Approvals

### 5a. In 5.1, replace step 3 ("Approve. An approver (see below) opens the document…")

**New text:**

> 3. **Approve.** A *different* person — an approver who neither created the document nor sent it for approval — opens it and, if everything looks right, chooses **Actions → Approve**. The document is now finalised and submitted. The form shows who sent it, in **Sent for Approval By**.

### 5b. In 5.2, add this paragraph directly after the "Who can do what" table

**New text:**

> Whatever the table says, **no one can approve a document they created or sent for approval** — this includes GI Management and System Managers. The Approve action may still appear in your Actions menu, but the system will refuse it with *"You cannot approve a document you created or sent for approval."* Ask another approver.

### 5c. Replace the whole of 5.3 ("A word on Sales Invoices specifically")

**New text:**

> **5.3 Sales Invoices: correct with a Credit Note, never cancel**
>
> Each Sales Invoice receives a serial Tax Invoice number when it's approved. An approved invoice is **final**: the system will not let anyone cancel it, whatever their role. Instead, if an approved invoice is wrong or the goods come back, you issue a **Credit Note** against it (step-by-step in 9.10).
>
> A Credit Note:
>
> - reverses the sale in the accounts and on the customer's balance — for the whole invoice or for part of it;
> - has its own number series (for example `BTAX-RET-00001`), so it never uses up a Tax Invoice number and never leaves a gap in the tax invoice sequence;
> - leaves the original invoice exactly as it was — same number, same Tax Invoice serial, still approved;
> - goes through the same Send for Approval → Approve steps as an invoice, and the person who created or sent it can't approve it.
>
> Draft invoices and invoices still waiting for approval can be deleted as before, so mistakes caught before approval are still the simplest to fix.

### 5d. Add a new section 5.4 after 5.3 (from branch `feature/credit-note-commission-approval-roles`)

**New text:**

> **5.4 Changing who can approve (System Manager only)**
>
> Who may approve each type of document is set in its *workflow*. Only a System Manager can change a workflow. Every change is recorded with who made it and when, and it stays in place when the system is updated.
>
> | Document | Workflow to open |
> |---|---|
> | Quotation | GI Quotation Approval |
> | Purchase Order | GI Purchase Order Approval |
> | Sales Invoice (and Credit Note) | GI Sales Invoice Approval |
> | Payment Entry | GI Payment Entry Approval |
> | Petty Cash Voucher | GI Petty Cash Approval |
>
> **To let another role approve:**
>
> 1. Log in as a System Manager.
> 2. Type **Workflow List** in the search bar and open the workflow from the table above.
> 3. Scroll down to the **Transitions** table. Each row where **State** is *Pending Approval* and **Action** is *Approve* gives one role the right to approve.
> 4. Click **Add Row** and fill it in exactly like the other Approve rows: **State** *Pending Approval*, **Action** *Approve*, **Next State** *Approved*, **Allowed** the new role. Tick **Allow Self Approval**, as on the other rows. (This box doesn't let anyone approve their own document — the system always blocks that.)
> 5. Click **Save**. The change works straight away; people may need to reload the page.
> 6. So that the new role is also told when something is waiting, type **Notification List** in the search bar, open the matching notification (for example *GI Purchase Order Pending Approval*), add a row in **Recipients** with **Receiver By Role** set to the new role, and **Save**.
> 7. Make sure the people who should approve actually have that role: open each person under **User**, tick the role under **Roles**, and **Save**.
>
> **To stop a role approving:** open the workflow, tick the role's *Approve* row in **Transitions**, click **Delete**, then **Save**. Remove the role from the notification's **Recipients** too.
>
> **To see who changed what:** open the workflow and scroll to the bottom. The activity list shows each change, who made it and when.
>
> Leave the *Send for Approval* rows alone unless you also want to change who can send documents for approval. Whatever the workflow says, nobody can approve a document they created or sent for approval.

**[Editor]** On Petty Cash Vouchers today, *Approve* is given to GI Management and GI Tech Dept only — GI Sales Dept has the direct *Submit* shortcut but not *Approve*. If GI Sales Dept should approve vouchers too, a System Manager can add it with the steps above.

### 5e. Add a new section 5.5 after 5.4 (from branch `feature/posting-date-guard-v2`)

**New text:**

> **5.5 Earliest Allowed Posting Date (closing a period)**
>
> Each company can be given an **Earliest Allowed Posting Date**: once the accountant has closed a period, nothing can be dated before it. It is set in the **COA Mapping Console**, under **Guardrail**, for each company separately. The field's help text reads: *"Documents that post to this company's ledger can't be dated before this. A System Manager may override; the override is recorded on the document."* Leave it empty and there is no restriction.
>
> **Which documents.** The documents that post to the company's accounts or stock (18 types): Sales Invoices and Credit Notes, Purchase Invoices, Payment Entries, Journal Entries, Petty Cash Vouchers, Delivery Notes, Purchase Receipts, Stock Entries, Stock Reconciliations, Landed Cost Vouchers, POS Invoices and POS Closing Entries, Subcontracting Receipts, Asset Capitalizations, Asset Value Adjustments, Exchange Rate Revaluations, Invoice Discounting and Period Closing Vouchers. The date checked is the document's **Posting Date**, except: Period Closing Voucher — its **Transaction Date**; Asset Value Adjustment — its **Date**.
>
> **Asset Repairs are not checked:** ERPNext 15.6 posts an Asset Repair on the day it is submitted, whatever its completion date, so it can never post before the cut-off.
>
> **What you see.** The check runs **every time the document is saved — including Save as a draft**, not only when it is sent for approval or submitted. A document dated before the cut-off is refused with:
>
> *"Journal Entry cannot be dated 2026-10-31 for company Blueline Enterprises Pvt Ltd: postings before 2026-11-01 are not allowed. Contact a System Manager if this document genuinely needs to be backdated."*
>
> (with the document type, dates and company filled in). Nothing is saved; change the date to the cut-off or later, or ask a System Manager.
>
> **Who can override.** Only a user with the **System Manager** role (and the built-in Administrator account) can save a document dated before the cut-off. The save goes through, and the document's timeline gets a comment such as: *"Posting date override: ceo@gen-innov.com saved this Journal Entry with posting_date = 2026-10-31 for company Blueline Enterprises Pvt Ltd, before the configured earliest allowed posting date of 2026-11-01. Allowed because the user holds the System Manager role."* Each override leaves this comment — one per document per person per day, so re-saving the same document the same day doesn't repeat it.

**[Editor]** If the manual has an "Accounts setup" or COA console section, add a one-line pointer there to 5.5.

---

## VAT Dashboard section (from `feature/vat-raw-ledger-totals`, `feature/final-items` and `feature/vat-discrepancies`)

### Add this paragraph after the description of the summary cards

**New text:**

> **Ledger discrepancies.** If any VAT account's balance for the period runs the wrong way — an Output VAT account with a debit balance, or an Input VAT account with a credit balance — a red box at the top lists it: the account, which way it should be and which way it is, and the amount. This usually means a posting to the wrong account or a reversed entry; click the account name to open its General Ledger and correct it. The box is always shown when there is something to check, and the list is also included in **Export to Excel**.
>
> **Show raw ledger totals.** Above the cards there is a switch, **Show raw ledger totals**. On (the default), the cards show each account exactly as posted — Output can then be negative — and the line under the cards reads *"Showing raw ledger totals; no regrouping applied."* Off, the cards count any Output VAT account with a debit balance under Input instead; those accounts are still listed in the discrepancies box. The Net VAT figure, the chart and the monthly table are the same either way.

**[Editor]** Place this in the VAT Dashboard section of the manual; it describes behaviour shipped on the release branch.

---

## Section 6 — Petty Cash Vouchers

### Add this paragraph at the end of 6.1

**New text:**

> As with all approvals, the person who created the voucher, and the person who sent it for approval, cannot approve it. Approvers who have a direct **Submit** option on vouchers can use it only on vouchers created by someone else, never on their own.

---

## Section 8 — Quick Reference / FAQ

### 8a. Replace the answer to "Can one person tick both approval boxes on a commission entry?"

**New text:**

> No. The two ticks must come from two different people, whatever their roles — even a System Manager can only give one of them. The system records who gave each tick, and once the entry is Approved, neither tick can be changed.

### 8b. Replace the answer to "I made a mistake on a Sales Invoice that's already approved — what now?"

**New text:**

> Issue a Credit Note against it (Create → Return / Credit Note, see 9.10). An approved invoice can't be cancelled. The Credit Note reverses it without touching the invoice's number or the tax invoice sequence. Check with the accountant first. Catching mistakes before approval avoids this entirely.

### 8c. Add a new question

| Question | Answer |
|---|---|
| I clicked Approve and got "You cannot approve a document you created or sent for approval." Why? | You created this document or sent it for approval, so someone else has to approve it. This is deliberate and applies to every role. |
| I tried to approve a commission entry and got "This commission cannot be approved while the invoice still has an outstanding amount." | The customer hasn't paid the invoice in full yet (or a payment was cancelled). Approve it once the invoice shows nothing outstanding — after the remaining payment, or after a Credit Note is applied to it. |
| Mark as Paid says "Select the Payment Entry that paid this commission out". | Record the payout first (Payment Entry, type Pay, approved), choose it in the entry's **Payment Entry** field, click **Update**, then Mark as Paid. |
| A commission entry shows a red Payment Warning. What do I do? | A payment on its invoice was cancelled after the entry was ticked or approved. Don't pay that commission until the invoice is fully paid again; the warning then disappears by itself. |
| A customer returned goods after the commission was paid. Do I have to fix the commission? | No. Approving the Credit Note creates a Deduction entry for that person automatically. Once it is approved, it comes off by itself when one of their commission entries is marked Paid, as soon as it fits into the commission on that payout (3.2a). Until then it is listed under Outstanding Deductions on the Sales Commission Register, in the column that says whether it will come off next. |

---

## Section 9 — Step-by-Step

### 9a. In 9.1, replace step 5

**New text:**

> 5. An approver (GI Management) — someone other than you — will see it under their bell icon and open it.

### 9b. In 9.4, add this as a new step 5

**New text:**

> 5. The names of the two approvers now show in **Management Approval By** and **Technical Approval By**. The two boxes are now locked. If one person tries to tick both boxes, the system refuses — the second tick must come from someone else.

### 9c. Add a new section 9.10 after 9.9

**New text:**

> **9.10 Issue a Credit Note (instead of cancelling an approved invoice)**
>
> 1. Open the approved Sales Invoice.
> 2. Click **Create → Return / Credit Note**. A new Credit Note opens with the invoice's lines, shown as negative quantities.
> 3. For a partial return, reduce the quantities to what is actually being credited. Remove any lines that aren't being credited.
> 4. Click **Save**. The Credit Note takes a number like `BTAX-RET-00001` — not a Tax Invoice number.
> 5. Click **Actions → Send for Approval**.
> 6. Another approver opens it and clicks **Actions → Approve**. You can't approve your own Credit Note.
> 7. Once approved, the sale is reversed in the accounts. The original invoice keeps its number and Tax Invoice serial. The credit now sits on the customer's account: the Credit Note shows a negative outstanding amount, and the invoice still shows what it showed before.
> 8. **Apply the credit to the invoice** (the accountant): open **Payment Reconciliation**. Choose the **Company**, **Party Type** *Customer*, the **Party**, and the customer's **Receivable / Payable Account**, then click **Get Unreconciled Entries**. Tick the Credit Note in the **Payments** table and the invoice in the **Invoices** table, click **Allocate**, check the amount, and click **Reconcile**. The invoice's outstanding drops by the credit; if nothing is left to pay, its status shows **Credit Note Issued**.
>    If the customer has already paid in full, don't apply it to that invoice: leave the credit on their account for a later invoice (same screen) or refund it with a Payment Entry.
> 9. The sales commission on the invoice is adjusted automatically when the Credit Note is approved (see 3.2a). Commission already paid shows up as a deduction on the Sales Commission Register. Commission on the rest of the invoice becomes ready for approval as soon as nothing is left to pay — whether that happens through a payment, this reconciliation, or both, in any order.
>
> **[Editor]** Production's ERPNext has no "Update Outstanding for Self" option on a Credit Note, so these steps always use Payment Reconciliation. If ERPNext is upgraded and the option appears, keep it ticked and these steps still apply.

---

## New section — Dashboards (from branch `feature/kpi-dashboards`)

### Add as a new section after the VAT Dashboard section

**New text:**

> **Dashboards**
>
> Both dashboards are on the **Blueline Control Center** workspace, under **Dashboards**.
>
> **My Dashboard** — for everyone. It shows your own work:
>
> - **Waiting for my approval** — documents someone else sent for approval that you are allowed to approve. Documents you created or sent yourself are never listed here, because you can't approve them. Click a document to open it.
> - **Sent by me, still waiting** — documents you sent for approval that nobody has approved yet, and how long they have been waiting.
> - **My drafts** — documents you started but haven't sent for approval.
> - **My quotations** — submitted this month, and those still open.
> - **My sales and commission** — your net sales this month and this fiscal year, and your commission by status. This shows only if your user is linked to your Sales Person (your administrator sets your **User ID** on your Employee record, and that Employee on your Sales Person).
>
> **Business KPI Dashboard** — for management (GI Management, the Financial Manager and System Managers). Choose a **Company**, or leave it empty for all companies you can see. Three tabs:
>
> - **Sales Performance** — net sales this month (with last month) and this fiscal year (with the same period last year); quotations this fiscal year and how many became orders; the 12-month trend; top customers and items; sales by company. *Net sales* means excluding VAT, with Credit Notes deducted.
> - **Financial Health** — receivables and payables outstanding, how much is overdue, and how long (aging); cash and bank balances; each company's VAT position for this fiscal year, with a red warning when the VAT Dashboard lists ledger discrepancies; petty cash this month.
> - **Commission** — entries waiting for approval, approved but not yet paid, outstanding deductions, this month's commission by status, and the top earners this fiscal year.
>
> If a section says **No access**, your role can't read that kind of document; the rest of the dashboard still works.

---

## New section — Document storage by fiscal year (from branch `feature/fiscal-year-folders`)

### Add as a new section at the end of the manual

**New text:**

> **Where your documents are kept**
>
> Every file you attach to a document (the paperclip / **Attach** on any form) is stored online and filed automatically by **fiscal year**, **company** and **type of document**. Open them from the document itself, or browse them in **File Manager** (search *File*):
>
> *Home → Fiscal Year 2026-2027 → Blueline Enterprises Pvt Ltd → Sales*
>
> | Folder | What goes there |
> |---|---|
> | Sales | attachments on Quotations, Sales Orders, Delivery Notes, Sales Invoices and Credit Notes |
> | Purchases | Purchase Orders, Purchase Receipts, Purchase Invoices |
> | Bank & Payments | Payment Entries, Journal Entries, bank transactions |
> | Petty Cash | Petty Cash Vouchers |
> | Shipping & CusDec | Landed Cost Vouchers (CusDec, bills of lading, shipping documents) |
> | General | anything you want to keep for the year that isn't attached to a document |
>
> The fiscal year comes from the document's date, not the day you attach the file, so a file attached in May to a March invoice goes into March's fiscal year.
>
> Filing doesn't change who can open a file: an attachment can be opened by the people who can open its document.
>
> Folders for a new fiscal year appear automatically when the accountant creates the Fiscal Year.

**[Editor]** Attachments made before this branch was deployed stay in *Home/Attachments* until an administrator runs the one-off move (`blueline.document_folders.refile_existing_attachments`, dry run first).
