"""Create the specific missing Items needed by the commission rule import.

Dry run (default, writes nothing):
	bench --site <site> execute blueline.scripts.create_missing_items.run

Create the items listed under WOULD CREATE (all-or-nothing, through normal validation):
	bench --site <site> execute blueline.scripts.create_missing_items.run --kwargs "{'execute': True}"

Only the items in CANDIDATES are ever considered. An Item that already exists is never
modified. A missing Item Group / Brand / UOM blocks that item — masters are never
auto-created here.
"""

import re

import frappe

CANDIDATES = [
	# Synced from production: exact copy of production's clean record.
	{
		"item_code": "Savema KCE-53-12PAT1-SV 53mm",
		"item_name": "Savema KCE-53-12PAT1-SV 53mm",
		"description": "Savema KCE-53-12PAT1-SV 53mm",
		"item_group": "Marking and Coding Printers & Spares",
		"stock_uom": "Nos",
		"is_stock_item": 1,
	},
	# Synced from production: exact copy of production's clean record.
	{
		"item_code": 'BL 100 1"',
		"item_name": 'BL 100 1"',
		"description": 'BL 100 1"',
		"item_group": "Components",
		"stock_uom": "Nos",
		"is_stock_item": 1,
	},
	# Genuinely new item (maintain stock = No, per the stock sheet).
	{
		"item_code": "11S+",
		"item_name": "11S+ Cartridge (370ml)",
		"description": "11S+ Cartridge (370ml)",
		"brand": "Sojet",
		"item_group": "Marking and Coding Consumables",
		"stock_uom": "Nos",
		"is_stock_item": 0,
	},
]
# field -> master doctype that must already exist
MASTERS = {"item_group": "Item Group", "brand": "Brand", "stock_uom": "UOM"}


def _alnum(value):
	return re.sub(r"[^0-9a-z]", "", (value or "").casefold())


def _resolve_master(doctype, value):
	"""-> (existing name or None, note). The DB collation is case-insensitive, so a
	case-differing master is reported and its canonical name used, never re-created."""
	name = frappe.db.get_value(doctype, value, "name")
	if not name:
		return None, ""
	return name, ("" if name == value else f"{doctype} {value!r} resolved to existing {name!r}")


def _similar_items(spec, all_items):
	"""Existing items whose code/name contain this item's code or name once punctuation,
	spacing and case are ignored — possible duplicates of the same product."""
	keys = {k for k in (_alnum(spec["item_code"]), _alnum(spec["item_name"])) if len(k) >= 4}
	hits = []
	for item in all_items:
		hay = {_alnum(item.name), _alnum(item.item_name)}
		if any(k in h or (len(h) >= 4 and h in k) for k in keys for h in hay):
			hits.append(f"{item.name} ({item.item_name})" if item.item_name != item.name else item.name)
	return hits


def run(execute=False):
	all_items = frappe.get_all("Item", fields=["name", "item_name"])
	create, exists, blocked = [], [], []

	for spec in CANDIDATES:
		existing = frappe.db.exists("Item", spec["item_code"])
		if existing:
			exists.append((spec, existing))
			continue

		doc_fields, notes, missing = dict(spec), [], []
		for field, doctype in MASTERS.items():
			if not spec.get(field):
				continue
			name, note = _resolve_master(doctype, spec[field])
			if not name:
				missing.append(f"{doctype} {spec[field]!r}")
				continue
			doc_fields[field] = name
			if note:
				notes.append(note)
		if missing:
			blocked.append((spec, missing))
			continue

		similar = _similar_items(spec, all_items)
		if similar:
			notes.append(f"POSSIBLE DUPLICATE of existing: {'; '.join(similar)}")
		create.append((spec, doc_fields, notes))

	_report(execute, create, exists, blocked)

	if not execute:
		print("\nDRY RUN — nothing was written.")
		frappe.db.rollback()
		return

	created = []
	try:
		for spec, doc_fields, _notes in create:
			doc = frappe.get_doc({"doctype": "Item", **doc_fields}).insert()
			created.append(doc.name)
	except Exception:
		frappe.db.rollback()
		print(f"\nEXECUTE FAILED at {spec['item_code']!r} — rolled back, nothing was created.")
		raise
	frappe.db.commit()
	print(f"\nEXECUTED — created {len(created)} Item(s): {', '.join(repr(n) for n in created)}")
	_summary(created, exists, blocked)


def _line(spec):
	return (f"  {spec['item_code']!r:<18} item_name={spec['item_name']!r} | group={spec['item_group']!r} | "
	        f"brand={spec.get('brand') or '-'!r} | uom={spec['stock_uom']!r} | stock item={spec['is_stock_item']}")


def _report(execute, create, exists, blocked):
	p = print
	p(f"MISSING ITEM CREATION — {'EXECUTE' if execute else 'DRY RUN'}")
	p(f"Totals: would create {len(create)} | already exist {len(exists)} | blocked by missing masters {len(blocked)}")

	p("\n=== MASTER DATA CHECK (per item) — reported only; masters are never auto-created")
	for spec in CANDIDATES:
		p(f"  {spec['item_code']!r}")
		for field, doctype in MASTERS.items():
			if not spec.get(field):
				p(f"      {doctype:<10} (none specified)")
				continue
			name, _note = _resolve_master(doctype, spec[field])
			status = "MISSING" if not name else ("exists" if name == spec[field] else f"exists as {name!r} (case differs; existing record used)")
			p(f"      {doctype:<10} {spec[field]!r}: {status}")

	p(f"\n=== WOULD CREATE ({len(create)})")
	for spec, doc_fields, notes in create:
		p(_line(spec))
		for note in notes:
			p(f"      note: {note}")

	p(f"\n=== SKIPPED — ALREADY EXISTS, NOT TOUCHED ({len(exists)})")
	for spec, existing in exists:
		p(_line(spec) + f"  -> existing Item {existing!r}")

	p(f"\n=== BLOCKED — MISSING MASTER DATA ({len(blocked)}) — nothing created for these; masters are not auto-created")
	for spec, missing in blocked:
		p(_line(spec))
		p(f"      missing: {', '.join(missing)}")

	if not execute:
		_summary([], exists, blocked, would_create=[s["item_code"] for s, _, _ in create])


def _summary(created, exists, blocked, would_create=()):
	print("\n=== SUMMARY (per item)")
	status = {}
	for code in would_create:
		status[code] = "would be created"
	for code in created:
		status[code] = "created"
	for spec, existing in exists:
		status[spec["item_code"]] = f"already existed ({existing!r}) — not touched"
	for spec, missing in blocked:
		status[spec["item_code"]] = f"blocked — missing {', '.join(missing)}"
	for spec in CANDIDATES:
		print(f"  {spec['item_code']!r:<18} {status.get(spec['item_code'], 'not created')}")
