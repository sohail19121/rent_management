from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import fields
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
@freeze_time('2026-10-15')
class TestRentDashboard(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('rent_management.group_rent_admin')
        cls.env.company.rent_deposit_account_id = cls.env['account.account'].create({
            'name': "Tenant Security Deposits", 'code': 'RENTDEP', 'account_type': 'liability_current',
        })
        cls.manager = new_test_user(cls.env, login='dash_mgr', groups='rent_management.group_rent_user')
        cls.prop_a = cls.env['rent.property'].create({'name': "Alpha", 'manager_id': cls.manager.id})
        cls.prop_b = cls.env['rent.property'].create({'name': "Beta"})
        cls.lease_a = cls._make_lease(cls.prop_a, rent=10000)
        cls.lease_b = cls._make_lease(cls.prop_b, rent=7000)

    @classmethod
    def _make_lease(cls, prop, rent):
        unit = cls.env['rent.unit'].create({'name': f"{prop.name}-1", 'property_id': prop.id})
        cls.env['rent.unit'].create({'name': f"{prop.name}-2", 'property_id': prop.id})
        tenant = cls.env['res.partner'].create({'name': f"Tenant {prop.name}", 'is_tenant': True})
        lease = cls.env['rent.lease'].create({
            'tenant_id': tenant.id, 'unit_id': unit.id,
            'start_date': fields.Date.today() - relativedelta(months=1),
            'end_date': fields.Date.today() + relativedelta(days=40),
            'rent_amount': rent, 'deposit_amount': 3 * rent,
        })
        lease.action_confirm()
        lease.action_activate()
        return lease

    def _pay(self, invoice, amount=None):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({'amount': amount or invoice.amount_residual})._create_payments()

    def _kpis(self, data):
        return {kpi['key']: kpi['value'] for section in data['sections'] for kpi in section['kpis']}

    def test_money_figures(self):
        self.lease_a.action_create_deposit_invoice()
        self._pay(self.lease_a.deposit_invoice_id)
        self.lease_a.next_invoice_date = fields.Date.today()
        rent = self.lease_a._create_rent_invoices()
        self._pay(rent, 4000)

        data = self.env['rent.property'].get_dashboard_data('this_month', self.prop_a.id)
        kpis = self._kpis(data)
        self.assertEqual(kpis['billed'], 10000.0, "Deposits are not income.")
        self.assertEqual(kpis['collected'], 4000.0, "Only payments of income invoices are collected.")
        self.assertEqual(kpis['collection_rate'], 40.0)
        self.assertEqual(kpis['outstanding'], 6000.0)
        self.assertEqual(kpis['deposits'], 30000.0)
        self.assertEqual(kpis['units'], 2)
        self.assertEqual(kpis['occupancy'], 50.0)
        self.assertEqual(kpis['rent_roll'], 10000.0)
        self.assertEqual(kpis['expiring'], 1)
        self.assertEqual(data['monthly']['billed'][-1], 10000.0)
        self.assertEqual(data['monthly']['collected'][-1], 4000.0)
        self.assertEqual(data['income_mix'], [{'label': "Rent", 'value': 10000.0}])
        self.assertEqual([row['name'] for row in data['property_rows']], ["Alpha"])
        self.assertEqual(data['property_rows'][0]['outstanding'], 6000.0)
        self.assertEqual(data['recent_payments'][0]['amount'], 4000.0)

        # Last month: nothing billed then.
        last_month = self._kpis(self.env['rent.property'].get_dashboard_data('last_month', self.prop_a.id))
        self.assertEqual(last_month['billed'], 0.0)

    def test_overdue_tenants(self):
        self.lease_b.next_invoice_date = fields.Date.today() - relativedelta(days=10)
        self.lease_b._create_rent_invoices()
        data = self.env['rent.property'].get_dashboard_data()
        self.assertEqual(len(data['overdue_tenants']), 1)
        self.assertRecordValues(self.lease_b.tenant_id, [{'name': data['overdue_tenants'][0]['tenant']}])
        self.assertEqual(data['overdue_tenants'][0]['days'], 10)
        self.assertEqual(self._kpis(data)['overdue'], 7000.0)

    def test_manager_sees_own_properties_only(self):
        self.lease_b.next_invoice_date = fields.Date.today()
        self.lease_b._create_rent_invoices()
        data = self.env['rent.property'].with_user(self.manager).get_dashboard_data()
        self.assertEqual([p['name'] for p in data['properties']], ["Alpha"])
        self.assertEqual(self._kpis(data)['billed'], 0.0, "Beta's invoice is not visible to Alpha's manager.")
        self.assertFalse(data['can_bill'])
        self.assertFalse(data['recent_payments'])
        billed = next(k for s in data['sections'] for k in s['kpis'] if k['key'] == 'billed')
        self.assertFalse(billed['action'], "No invoice action without accounting rights.")
