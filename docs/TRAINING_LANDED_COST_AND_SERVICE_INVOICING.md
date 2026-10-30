# Training: Landed Cost Vouchers and Technical Service Invoicing

**For:** the finance team (Landed Cost Vouchers, service invoices) and technical staff (Timesheets).
**System:** ERPNext v15, standard features, with the Blueline approval rules on top.

Both topics use standard ERPNext screens. Nothing here needs custom code. Part A and Part B each start with a one-time setup that the accountant or a System Manager does once.

---

## Part A — Landed Cost Vouchers (imported and locally purchased items)

### A.1 What a Landed Cost Voucher does

The real cost of an item in stock is more than the supplier's price. For an **import** it also includes freight, insurance, customs duty and other charges on the CusDec, port and clearing-agent charges, and bank charges on the LC. For a **local purchase** it can include transport and unloading.

A **Landed Cost Voucher (LCV)** adds these costs to the stock you received, so that:
- the items' **valuation rate** (cost per unit) is correct, and
- profit on each sale (sale price minus cost) is correct.

An LCV doesn't pay anyone. The freight forwarder, clearing agent or customs are paid and invoiced as usual. The LCV only moves the cost from an expense account into the value of the stock.

**Not a landed cost:** **VAT paid at customs** is recoverable Input VAT. Book it to the Input VAT account, never in an LCV, or it disappears into stock value and is lost from the VAT return.

### A.2 One-time setup (accountant / System Manager)

1. **Receive stock in ERPNext.** An LCV can only be applied to a **Purchase Receipt**, or to a **Purchase Invoice with "Update Stock" ticked**. Today the system has neither, so goods are not yet received through ERPNext. Start receiving stock this way first; until then there is nothing for an LCV to attach to.
2. **Company accounts** (*Company* → each company → *Accounts* / *Stock* sections):
   - **Stock Received But Not Billed**, a liability account used between receiving goods and booking the supplier's invoice;
   - **Expenses Included In Valuation**, the clearing account an LCV credits, for example *Expenses Included In Valuation - BEPL*.
   Both are empty on all three companies today. Also fill the matching fields in the **COA Mapping Console**, so the configuration and the company agree.
3. **Expense accounts for landed costs.** Either use *Expenses Included In Valuation* for everything, or create one leaf account per cost type under it (*Freight Inward*, *Customs Duty*, *Clearing & Port Charges*, *Insurance on Imports*). Separate accounts make it easier to see what imports cost.
4. **Supplier invoices for the charges** (freight forwarder, clearing agent, insurer, customs) are **Purchase Invoices** for a **non-stock service item** (e.g. *Freight Charges*, *Clearing Charges*, *Customs Duty*). Their expense account is the landed-cost account from step 3. The existing payable accounts such as *FDE Freight Payable - BEPL*, *HSD Clearing Payable - BEPL* and *Speed International Freight Payable - BEPL* are where those suppliers are paid from.

### A.3 Imported goods — step by step

Example: 500 units arrive by sea. The supplier invoice is USD 10,000. Freight is LKR 180,000, customs duty on the CusDec is LKR 250,000, and clearing charges are LKR 45,000.

1. **Receive the goods:** *Purchase Receipt* (from the Purchase Order: *Create → Purchase Receipt*). Check quantities and warehouse → Save → Submit.
2. **Book the charges** as they are invoiced: one *Purchase Invoice* each for the freight forwarder (180,000), the clearing agent (45,000) and the duty (250,000), each using the service item and landed-cost expense account from A.2. Put the **CusDec number** in the invoice's *Bill No* / remarks, and **attach the CusDec**: it is filed automatically under *Fiscal Year … / Company / Shipping & CusDec* when attached to the LCV, or under *Purchases* when attached to the Purchase Invoice.
3. **Create the Landed Cost Voucher:** search *Landed Cost Voucher* → **New**.
   - **Company**: the company that received the goods.
   - **Purchase Receipts** table: *Receipt Document Type* = Purchase Receipt, *Receipt Document* = the receipt from step 1. Click **Get Items From Purchase Receipts**: the items table fills in.
   - **Taxes and Charges** table: one row per cost. *Expense Account* is the same landed-cost account the charge was booked to in step 2; *Description* names the cost and its reference (e.g. *Sea freight, B/L 123*, *Customs duty, CusDec 45678*); *Amount* is the cost in company currency. **Leave out VAT.**
   - **Distribute Charges Based On**:
     - **Amount** (usual for imports): each item takes a share in proportion to its value. Use this for duty, insurance and most freight.
     - **Qty**: each unit takes the same share. Use this when items are similar in size and weight.
     - **Distribute Manually**: type each item's share in the items table. Use this when one item clearly causes most of a cost (e.g. one bulky item and the freight is by volume).
   - Save. Check the **Applicable Charges** column in the items table, then **Submit**.
4. **What happens:** each item's valuation rate goes up by its share. In the ledger, Stock is debited and the landed-cost expense accounts are credited, so the expense from step 2 is cleared into stock.
5. **Check:** open the item → *Stock Ledger* report for that item and receipt: the incoming rate now includes the landed cost.

**Timing.** Make the LCV as soon as all the charges are known, ideally before the goods are sold. If some units were already delivered, ERPNext re-posts the valuation and adjusts the cost of goods already sold. That is correct, but it changes figures in a period that may already have been reviewed.

**A charge arrives later** (e.g. a demurrage invoice a month on): make a **second** LCV against the same Purchase Receipt for just that charge. Don't cancel the first one.

### A.4 Locally purchased goods

The steps are the same as A.3, usually with one or two rows: *Transport from supplier*, *Unloading*. Distribute by **Qty** or **Amount** as fits. If the supplier's own invoice already includes delivery, there is nothing to add: don't make an LCV.

### A.5 Mistakes and corrections

- **Wrong amount or account on a submitted LCV:** cancel it and amend it (*Cancel → Amend*). ERPNext reverses the valuation and re-applies the corrected one.
- **VAT included by mistake:** cancel and amend without the VAT row, then make sure the VAT is on the Input VAT account.
- **Back-dated LCV refused** with *"… postings before … are not allowed"*: the company's *Earliest Allowed Posting Date* (COA Mapping Console) is later than the LCV date. Ask a System Manager.

---

## Part B — Technical service charge invoicing with cost calculations

### B.1 The idea

A service job's price is built from:
- **labour**: technician hours × a billing rate per type of work;
- **travel / site visit**: a fixed visit charge or a rate per km;
- **parts and materials** used, at their selling price.

Its **cost** is technician hours × a **costing rate** (what the hour costs the company), plus travel cost, plus the parts' valuation. ERPNext calculates both sides and shows the margin per job. The standard tools are **Activity Types**, **Timesheets** and **Projects**.

### B.2 One-time setup (accountant / System Manager)

1. **Activity Types** (search *Activity Type*): one per kind of work, e.g. *Installation*, *Repair*, *Maintenance Visit*, *Commissioning*, *Consultation*. On each, set the **Default Billing Rate** (charged to the customer per hour) and the **Default Costing Rate** (cost to the company per hour). Five Activity Types already exist; rename or replace them to match the company's rate card.
2. **Activity Cost** (optional): a different billing or costing rate for a particular technician (Employee) on a particular Activity Type, e.g. a senior engineer billed at a higher rate.
3. **Service items** (non-stock; *Maintain Stock* unticked), with an Item Price on the selling price list:
   - *Technical Service — Labour* (UOM: Hour). Used when invoicing from a Timesheet.
   - *Site Visit Charge* (UOM: Nos), and/or *Travel* (UOM: Km).
   - *Call-out / Emergency Surcharge* if one applies.
   Today only one service item exists, so create these.
4. **Technicians as Employees**, each with their **User ID** set, so they can fill in their own Timesheets.

### B.3 A service job — step by step

1. **Project per job** (search *Project* → New): *Project Name* = job reference (e.g. *SRV-2026-041 CBL Foods chiller repair*), *Customer*, *Company*. The project collects all costs and billing for the job.
2. **Technicians log time** (*Timesheet* → New, one per technician per job or per week): each row has *Activity Type*, *From/To* or *Hours*, *Project* = the job, and **Is Billable** ticked for hours the customer pays. The billing and costing amounts fill in from the rates in B.2. Submit the Timesheet.
3. **Parts used:** issue them from stock with a *Stock Entry* (*Material Issue*) against the Project, or add them as item rows on the invoice in step 4.
4. **Invoice the job:** open the Timesheet → **Create Sales Invoice** (or on a new Sales Invoice use **Fetch Timesheet**). The billable hours come in as the labour line. Then add rows for:
   - *Site Visit Charge* / *Travel* (qty = visits or km);
   - the parts, if not already invoiced;
   - the correct **Sales Taxes and Charges Template** (VAT).
   Save → **Actions → Send for Approval**. Another person approves it, as for every Sales Invoice; it then gets its Tax Invoice serial.
5. **See the cost calculation:** open the **Project**. The *Costing and Billing* section shows **Total Costing Amount (via Timesheet)**, **Total Billable Amount (via Timesheet)**, **Total Billed Amount (via Sales Invoice)**, **Total Consumed Material Cost (via Stock Entry)**, and **Gross Margin** / **Gross Margin %**. To compare jobs, use the **Profitability Analysis** report with *Based On* = Project.

### B.4 Quick one-off service (no Timesheet)

For a small job with no need to track technician time: create a Sales Invoice directly with *Technical Service — Labour* (qty = hours, rate from the price list), *Site Visit Charge* and any parts, then Send for Approval. This bills correctly but records no labour cost, so the job's margin isn't calculated. Use B.3 for anything you want to measure.

### B.5 Quoting a service job first

Make a **Quotation** with the same lines (labour hours estimated, visit, parts). When the customer accepts, create the Sales Invoice from it, or follow B.3 and compare the invoice with the quotation.

---

## Where documents are filed

Attachments are filed automatically by fiscal year and company (*Home → Fiscal Year … → Company*):

| Attached to | Folder |
|---|---|
| Landed Cost Voucher (CusDec, B/L, shipping documents) | Shipping & CusDec |
| Purchase Receipt / Purchase Invoice / Purchase Order | Purchases |
| Sales Invoice / Quotation (incl. service invoices) | Sales |
| Payment Entry / Journal Entry | Bank & Payments |
| Petty Cash Voucher | Petty Cash |

## Checklist for the training session

- [ ] Company accounts in A.2 set for each company; matching COA console fields filled in
- [ ] Stock is received with Purchase Receipts
- [ ] Landed-cost expense accounts and service items for charges created
- [ ] Practice: one import LCV with three charges, distributed by Amount; check the Stock Ledger
- [ ] Practice: one local LCV distributed by Qty
- [ ] Activity Types carry the company's billing and costing rates
- [ ] Service items and prices created; technicians are Employees with User IDs
- [ ] Practice: one Project → Timesheet → Sales Invoice → approval; read the Project's Gross Margin
