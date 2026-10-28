"""Run the blueline suites against a site without persisting anything.

	bench --site <site> execute blueline.tests.runner.run
	bench --site <site> execute blueline.tests.runner.run --kwargs "{'module': 'test_self_approval'}"

Not wired into `bench run-tests` on purpose: that runner creates and commits its own test
records, which must not happen on a site holding real business data.
"""

import importlib
import pkgutil
import unittest

import frappe

import blueline.tests

SUITES = (
	"test_existing_behaviour",
	"test_self_approval",
	"test_commission_approvers",
	"test_credit_note",
	"test_credit_note_commission",
	"test_approver_roles",
	"test_item5_commission_matching",
	"test_coa_valuation_method",
)


def run(module=None, verbosity=2):
	names = [module] if module else [n for n in SUITES if _exists(n)]
	loader = unittest.TestLoader()
	suite = unittest.TestSuite(loader.loadTestsFromModule(importlib.import_module(f"blueline.tests.{n}")) for n in names)

	real_commit = frappe.db.commit

	def refuse_commit(*args, **kwargs):
		raise RuntimeError("frappe.db.commit() called during a blueline test run")

	frappe.db.commit = refuse_commit
	try:
		result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
	finally:
		frappe.db.rollback()
		frappe.db.commit = real_commit
		frappe.set_user("Administrator")

	# A test with failing subTests appears once per failing subTest; count the test once.
	failed = {getattr(test, "test_case", test).id() for test, _ in result.failures + result.errors}
	print(f"\nBLUELINE TESTS: {result.testsRun - len(failed)}/{result.testsRun} passed")
	return {"run": result.testsRun, "failed": sorted(failed)}


def _exists(name):
	return any(m.name == name for m in pkgutil.iter_modules(blueline.tests.__path__))
