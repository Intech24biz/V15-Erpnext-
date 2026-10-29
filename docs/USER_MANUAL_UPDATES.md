# Blueline — User Manual: text changes for the client-review fixes

**Applies to:** *Blueline — User Manual* dated Oct 8, 2026 (13 pages).
**Reason:** three behaviours changed on branch `fix/client-review-hard-blocks`:

1. nobody can approve a document they created or sent for approval;
2. one person can't give both commission approvals;
3. an approved Sales Invoice is corrected with a Credit Note, not cancelled.

Added from branch `feature/credit-note-commission-approval-roles` (update the manual only once that branch is deployed too):

4. a Credit Note adjusts the sales commission on the invoice automatically (new 3.2a);
5. a System Manager changes who can approve in the Workflow screen, and the change is kept (new 5.4).

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
> **Outstanding deductions** are listed per person at the top of the **Sales Commission Register** — whether still waiting for approval or already approved. Take them off that person's next commission payout. Deductions are not included in the status totals, and a deduction can't be marked as Paid.
>
> If the commission can't be adjusted for some reason, the Credit Note is **not approved**. The approver sees *"Commission could not be adjusted for this Credit Note; nothing was changed. Contact the administrator."* Nothing has changed — not the Credit Note, not the accounts, not the commission — so the administrator can fix the cause and the Credit Note can then be approved as normal.

**[Editor]** Deductions don't yet have a payout step; an approved deduction stays listed on the register until it is taken off a payout. Update this paragraph once the payout netting is built.

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
| A customer returned goods after the commission was paid. Do I have to fix the commission? | No. Approving the Credit Note creates a Deduction entry for that person automatically. It is listed under Outstanding Deductions on the Sales Commission Register; take it off their next payout. |

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
