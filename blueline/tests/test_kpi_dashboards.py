"""Management (Business KPI) and staff (My Dashboard) dashboards: who may open them, that the
figures move with real documents, and that "waiting for my approval" follows the same rule as
the approval itself (never the creator or the sender)."""

import frappe
from frappe.utils import flt

from blueline.blueline.page.business_kpi_dashboard.business_kpi_dashboard import (
	get_commission_payroll,
	get_financial_health,
	get_sales_performance,
)
from blueline.blueline.page.my_dashboard.my_dashboard import get_my_dashboard
from blueline.tests.utils import (
	COMPANY,
	FINANCIAL_MANAGER,
	GI_MANAGEMENT,
	GI_SALES,
	GI_SALES_2,
	GI_TECH,
	SYSTEM_MANAGER,
	BluelineTestCase,
	act,
	approved_invoice,
	make_purchase_order,
	reload,
	workflow,
)

MANAGEMENT_ENDPOINTS = (get_sales_performance, get_financial_health, get_commission_payroll)


class TestManagementDashboard(BluelineTestCase):
	def test_staff_cannot_read_management_figures(self):
		for endpoint in MANAGEMENT_ENDPOINTS:
			with self.subTest(endpoint=endpoint.__name__):
				self.assertRefused(lambda: act(GI_SALES, endpoint, COMPANY), "management roles only")

	def test_management_roles_can_read_every_tab(self):
		for user in (FINANCIAL_MANAGER, GI_MANAGEMENT, SYSTEM_MANAGER):
			for endpoint in MANAGEMENT_ENDPOINTS:
				with self.subTest(user=user, endpoint=endpoint.__name__):
					data = act(user, endpoint, COMPANY)
					self.assertTrue(data["currency"])

	def test_net_sales_move_by_the_invoice_net_total(self):
		before = act(FINANCIAL_MANAGER, get_sales_performance, COMPANY)["kpis"]
		invoice = approved_invoice()
		after = act(FINANCIAL_MANAGER, get_sales_performance, COMPANY)["kpis"]
		for period in ("this_month", "fy_to_date"):
			with self.subTest(period=period):
				self.assertAlmostEqual(after[period] - before[period], flt(invoice.base_net_total), places=2)

	def test_receivables_include_a_new_unpaid_invoice(self):
		before = act(FINANCIAL_MANAGER, get_financial_health, COMPANY)["receivables"]
		invoice = approved_invoice()
		after = act(FINANCIAL_MANAGER, get_financial_health, COMPANY)["receivables"]
		self.assertAlmostEqual(after["total"] - before["total"], flt(invoice.base_rounded_total or invoice.base_grand_total), places=2)
		self.assertEqual(after["count"], before["count"] + 1)

	def test_commission_tab_groups_by_payee_and_counts_pending(self):
		data = act(FINANCIAL_MANAGER, get_commission_payroll, COMPANY)
		for row in data["top_salespeople"]:
			self.assertIn("commission_credited_to", row)
		self.assertEqual(data["pending_total"], sum(r.count for r in data["pending_by_company"]))

	def test_vat_position_reports_discrepancy_counts(self):
		data = act(FINANCIAL_MANAGER, get_financial_health, COMPANY)
		[row] = [r for r in data["vat_position"] if r["company"] == COMPANY]
		self.assertIn("discrepancies", row)


class TestMyDashboard(BluelineTestCase):
	def sent_purchase_order(self, creator=GI_TECH):
		po = make_purchase_order(creator)
		workflow(po, "Send for Approval", creator)
		return reload(po)

	def names(self, rows):
		return {(r.doctype, r.name) for r in rows}

	def test_a_sent_document_waits_for_an_approver_not_for_its_sender(self):
		po = self.sent_purchase_order(GI_TECH)
		key = ("Purchase Order", po.name)

		approver = act(GI_MANAGEMENT, get_my_dashboard)
		self.assertIn(key, self.names(approver["waiting_for_me"]))

		sender = act(GI_TECH, get_my_dashboard)
		self.assertNotIn(key, self.names(sender["waiting_for_me"]), "the sender may never approve it")
		self.assertIn(key, self.names(sender["sent_by_me"]))

	def test_a_document_sent_by_someone_else_is_still_not_waiting_for_its_creator(self):
		po = make_purchase_order(GI_MANAGEMENT)
		workflow(po, "Send for Approval", GI_MANAGEMENT)
		self.assertNotIn(("Purchase Order", po.name), self.names(act(GI_MANAGEMENT, get_my_dashboard)["waiting_for_me"]))

	def test_users_without_the_approve_role_see_nothing_to_approve(self):
		approvers = {
			t.allowed
			for t in frappe.get_doc("Workflow", "GI Purchase Order Approval").transitions
			if t.action == "Approve"
		}
		user = next((u for u in (GI_SALES_2, GI_SALES) if not approvers & set(frappe.get_roles(u))), None)
		if not user:
			self.skipTest("every test user may approve Purchase Orders on this site")
		po = self.sent_purchase_order(GI_TECH)
		self.assertNotIn(("Purchase Order", po.name), self.names(act(user, get_my_dashboard)["waiting_for_me"]))

	def test_drafts_are_counted_until_sent(self):
		def po_drafts():
			drafts = act(GI_TECH, get_my_dashboard)["drafts"]
			return next((d["count"] for d in drafts if d["doctype"] == "Purchase Order"), 0)

		before = po_drafts()
		po = make_purchase_order(GI_TECH)
		self.assertEqual(po_drafts(), before + 1)
		workflow(po, "Send for Approval", GI_TECH)
		self.assertEqual(po_drafts(), before)

	def test_a_user_without_a_sales_person_gets_no_sales_figures(self):
		data = act(GI_TECH, get_my_dashboard)
		if data["sales_persons"]:
			self.skipTest("tech@ is linked to a Sales Person on this site")
		self.assertIsNone(data["sales"])
		self.assertIsNone(data["commission"])
