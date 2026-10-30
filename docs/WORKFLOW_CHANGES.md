# Changing GI workflows and notifications without drift

**For:** developers and the System Manager who maintain production.

The six GI approval workflows and their *Pending Approval* notifications are **not** fixtures. Fixtures are re-imported with `force=True` on every `bench migrate`, which used to wipe out approver roles changed on site. Instead they are seeded **insert-only** from `blueline/setup_data/`: created when missing, never overwritten.

That makes the **live production site the source of truth** for these records. The rules below keep git in step with it.

## The three rules

1. **Changes made on site** (user manual 5.4: a System Manager adds or removes an approver role) are brought back into git with a snapshot:

   ```bash
   bench --site <production-site> execute blueline.workflow_sync.export_snapshot
   ```

   This writes `blueline/setup_data/snapshot/workflow.json` and `notification.json` in the app folder on the server. Commit them, either from the server checkout or by copying the two files into a branch. Every change is also in the record's own Version history (who and when).

2. **Changes made in code** go in as a **patch** listed in `blueline/patches.txt`, never by editing `setup_data/*.json` (existing sites never re-read those files). Example:

   ```python
   # blueline/patches/add_gi_tech_dept_po_approver.py
   import frappe

   def execute():
       wf = frappe.get_doc("Workflow", "GI Purchase Order Approval")
       if any(t.action == "Approve" and t.allowed == "GI Tech Dept" for t in wf.transitions):
           return  # already there (e.g. added on site)
       wf.append("transitions", {
           "state": "Pending Approval", "action": "Approve",
           "next_state": "Approved", "allowed": "GI Tech Dept", "allow_self_approval": 1,
       })
       wf.flags.ignore_permissions = True
       wf.save()
   ```

   After deploying, run `export_snapshot` and commit, as in rule 1.

3. **Check before and after each deploy:**

   ```bash
   bench --site <site> execute blueline.workflow_sync.check_drift
   ```

   This lists every difference between the live records and the committed snapshot (or the original seed if no snapshot is committed yet), for example `transitions: added row (state=Pending Approval, action=Approve, next_state=Approved, allowed=GI Sales Dept 2)`. The same report is printed at the end of every `bench migrate`. It never changes anything and never fails the migrate.

## New environments

A fresh install (staging, a new site) is seeded from the committed snapshot when there is one, so it starts with production's approver roles, not the roles originally shipped. Without a snapshot it falls back to `setup_data/workflow.json` and `notification.json`.

## First-time setup

Run `export_snapshot` once on production and commit the result. Until then, `check_drift` compares against the original seed and will report the role changes already made on production (for example the 2026-10-08 role changes).
