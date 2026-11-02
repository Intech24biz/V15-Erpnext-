"""Keep the GI workflows and their pending-approval notifications aligned with git.

They are seeded insert-only (setup.create_missing_seed_records) so a System Manager's change
on site survives every migrate, which makes the live site their source of truth. This module
brings that state back into the repository:

	bench --site <site> execute blueline.workflow_sync.export_snapshot
		Writes the live records to blueline/setup_data/snapshot/. Commit the result. New
		environments (after_install) are then seeded from the snapshot, not the original seed.

	bench --site <site> execute blueline.workflow_sync.check_drift
		Lists what differs between the live records and the committed snapshot (or the
		original seed if there is no snapshot yet). Also printed at the end of bench migrate.

Changes made in code go in as a patch (patches.txt), never by editing these files; see
docs/WORKFLOW_CHANGES.md.
"""

import json
import os

import frappe

SEED_FILES = {"workflow.json": "Workflow", "notification.json": "Notification"}
SNAPSHOT_DIR = "snapshot"

# Set by Frappe on every save, or layout-only: never a difference that matters. "doctype" is
# dropped from child rows only (live rows carry it, the seed files' rows don't);
# normalize() puts the record's own doctype back.
VOLATILE_FIELDS = {
	"doctype",
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"idx",
	"docstatus",
	"parent",
	"parentfield",
	"parenttype",
	"workflow_builder_id",
	"workflow_data",
	"_user_tags",
	"_comments",
	"_assign",
	"_liked_by",
	"_seen",
}


def seed_path(fname, snapshot=False):
	parts = ("setup_data", SNAPSHOT_DIR, fname) if snapshot else ("setup_data", fname)
	return frappe.get_app_path("blueline", *parts)


def load(fname, snapshot=False):
	path = seed_path(fname, snapshot)
	if not os.path.exists(path):
		return None
	with open(path) as f:
		return json.load(f)


def seed_records(fname):
	"""The records to seed or compare against: the committed snapshot when there is one,
	otherwise the original seed shipped with the app."""
	return load(fname, snapshot=True) or load(fname)


def _clean(value):
	if isinstance(value, dict):
		return {k: _clean(v) for k, v in sorted(value.items()) if k not in VOLATILE_FIELDS and v not in (None, "")}
	if isinstance(value, list):
		rows = [_clean(v) for v in value]
		# Row order carries no meaning in these tables; sort so a reorder isn't a change.
		return sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, default=str))
	return value


def normalize(record):
	"""A record as compared and as written to the snapshot: volatile fields dropped, empty
	values dropped, child rows in a stable order. Keeps doctype and name."""
	clean = _clean(record)
	clean["doctype"], clean["name"] = record["doctype"], record["name"]
	return clean


def live_fields_only(record, doctype):
	"""`record` without the fields this site's `doctype` doesn't have, child rows included.
	Seed files and snapshots written on another Frappe/ERPNext version can carry fields that
	don't exist here (15.110 has Workflow Document State.send_email, 15.5 doesn't); a field
	the site can't hold is never a difference on that site."""
	meta = frappe.get_meta(doctype)
	kept = {}
	for key, value in record.items():
		if key in ("doctype", "name"):
			kept[key] = value
			continue
		df = meta.get_field(key)
		if not df:
			continue
		if df.fieldtype in frappe.model.table_fields and isinstance(value, list):
			value = _clean([live_fields_only(row, df.options) for row in value])
		kept[key] = value
	return kept


def live_records(fname):
	doctype = SEED_FILES[fname]
	names = [r["name"] for r in load(fname)]
	records = []
	for name in names:
		if frappe.db.exists(doctype, name):
			records.append(normalize(frappe.get_doc(doctype, name).as_dict(convert_dates_to_str=True)))
	return records


def export_snapshot():
	"""Write the live GI workflows and notifications to setup_data/snapshot/."""
	written = []
	os.makedirs(os.path.dirname(seed_path("workflow.json", snapshot=True)), exist_ok=True)
	for fname in SEED_FILES:
		path = seed_path(fname, snapshot=True)
		with open(path, "w") as f:
			json.dump(live_records(fname), f, indent=1, sort_keys=True, ensure_ascii=False, default=str)
			f.write("\n")
		written.append(path)
	print("Snapshot written; commit these files:\n  " + "\n  ".join(written))
	return written


def _row_label(row):
	keys = ("state", "action", "next_state", "allowed", "receiver_by_role", "receiver_by_document_field")
	return ", ".join(f"{k}={row[k]}" for k in keys if row.get(k)) or json.dumps(row, sort_keys=True, default=str)


def _diff(expected, actual):
	changes = []
	for key in sorted(set(expected) | set(actual)):
		before, after = expected.get(key), actual.get(key)
		if before == after:
			continue
		if isinstance(before, list) or isinstance(after, list):
			before_rows = {json.dumps(r, sort_keys=True, default=str): r for r in before or []}
			after_rows = {json.dumps(r, sort_keys=True, default=str): r for r in after or []}
			changes += [f"{key}: removed row ({_row_label(r)})" for k, r in before_rows.items() if k not in after_rows]
			changes += [f"{key}: added row ({_row_label(r)})" for k, r in after_rows.items() if k not in before_rows]
		else:
			changes.append(f"{key}: {before!r} -> {after!r}")
	return changes


def check_drift(verbose=True):
	"""{"<Doctype> <name>": [differences]} between the live site and the committed snapshot
	(or the original seed). Empty when they match."""
	drift = {}
	for fname, doctype in SEED_FILES.items():
		expected = {r["name"]: live_fields_only(normalize(r), doctype) for r in seed_records(fname)}
		actual = {r["name"]: r for r in live_records(fname)}
		for name, record in expected.items():
			if name not in actual:
				drift[f"{doctype} {name}"] = ["missing on this site"]
				continue
			changes = _diff(record, actual[name])
			if changes:
				drift[f"{doctype} {name}"] = changes
	if verbose:
		_report(drift)
	return drift


def _report(drift):
	source = "committed snapshot" if load("workflow.json", snapshot=True) else "original seed (no snapshot committed yet)"
	if not drift:
		print(f"GI workflows and notifications match the {source}.")
		return
	print(f"GI workflows / notifications differ from the {source}:")
	for record, changes in drift.items():
		print(f"  {record}")
		for change in changes:
			print(f"    - {change}")
	print("If these changes are intended, run blueline.workflow_sync.export_snapshot and commit the result.")
