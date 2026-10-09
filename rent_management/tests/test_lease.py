from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestRentLease(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('rent_management.group_rent_admin')
        cls.today = fields.Date.context_today(cls.env['rent.lease'])
        cls.deposit_account = cls.env['account.account'].create({
            'name': "Tenant Security Deposits",
            'code': 'RENTDEP',
            'account_type': 'liability_current',
        })
        cls.env.company.write({
            'rent_deposit_account_id': cls.deposit_account.id,
            'rent_income_account_id': cls.company_data['default_account_revenue'].id,
            'rent_invoice_advance_days': 5,
        })
        cls.tenant = cls.env['res.partner'].create({'name': "Test Tenant", 'is_tenant': True})
        cls.property = cls.env['rent.property'].create({'name': "Test Tower"})
        cls.unit = cls.env['rent.unit'].create({
            'name': "T-1",
            'property_id': cls.property.id,
            'base_rent': 10000,
            'deposit_amount': 30000,
        })

    def _create_lease(self, **vals):
        return self.env['rent.lease'].create({
            'tenant_id': self.tenant.id,
            'unit_id': self.unit.id,
            'start_date': self.today - relativedelta(months=2),
            'end_date': self.today + relativedelta(months=10),
            'rent_amount': 10000,
            'maintenance_charge': 500,
            'deposit_amount': 30000,
            **vals,
        })

    def _active_lease(self, **vals):
        lease = self._create_lease(**vals)
        lease.action_confirm()
        lease.action_activate()
        return lease

    def test_dashboard_without_units(self):
        self.env['rent.unit'].search([]).action_archive()
        data = self.env['rent.property'].get_dashboard_data()
        kpis = {kpi['key']: kpi['value'] for section in data['sections'] for kpi in section['kpis']}
        self.assertEqual(kpis['units'], 0)
        self.assertEqual(kpis['occupancy'], 0.0)
        self.assertEqual(kpis['collection_rate'], 0.0)

    def test_overlapping_lease_constraint(self):
        lease = self._create_lease()
        lease.action_confirm()
        self.assertEqual(self.unit.state, 'reserved')

        overlapping = self._create_lease(start_date=self.today, end_date=self.today + relativedelta(years=1))
        with self.assertRaises(ValidationError):
            overlapping.action_confirm()

        after = self._create_lease(
            start_date=lease.end_date + timedelta(days=1),
            end_date=lease.end_date + relativedelta(years=1))
        after.action_confirm()
        self.assertEqual(after.state, 'confirmed')

        with self.assertRaises(ValidationError):
            self._create_lease(end_date=self.today - relativedelta(months=3))

    def test_invoice_generation_cron(self):
        lease = self._active_lease()
        self.assertEqual(self.unit.state, 'occupied')
        self.assertEqual(self.unit.current_tenant_id, self.tenant)
        lease.next_invoice_date = self.today + timedelta(days=2)

        self.env['rent.lease']._cron_generate_invoices()

        invoice = lease.invoice_ids
        self.assertEqual(len(invoice), 1)
        self.assertRecordValues(invoice, [{
            'state': 'posted',
            'move_type': 'out_invoice',
            'partner_id': self.tenant.id,
            'invoice_origin': lease.name,
            'invoice_date_due': self.today + timedelta(days=2),
            'rent_invoice_type': 'rent',
            'amount_total': 10500.0,
        }])
        self.assertEqual(lease.next_invoice_date, self.today + timedelta(days=2) + relativedelta(months=1, day=lease.billing_day))

        # Nothing left to invoice within the advance window.
        self.env['rent.lease']._cron_generate_invoices()
        self.assertEqual(len(lease.invoice_ids), 1)

    def test_late_fee_applied_once(self):
        lease = self._active_lease(late_fee_type='fixed', late_fee_value=500, grace_days=5)
        lease.next_invoice_date = self.today - timedelta(days=20)
        rent_invoice = lease._create_rent_invoices()

        self.env['rent.lease']._cron_apply_late_fees()
        fee_invoice = lease.invoice_ids.filtered(lambda m: m.rent_invoice_type == 'late_fee')
        self.assertEqual(len(fee_invoice), 1)
        self.assertEqual(fee_invoice.amount_total, 500.0)
        self.assertTrue(rent_invoice.rent_late_fee_applied)
        self.assertEqual(rent_invoice.rent_late_fee_invoice_id, fee_invoice)

        self.env['rent.lease']._cron_apply_late_fees()
        self.assertEqual(len(lease.invoice_ids.filtered(lambda m: m.rent_invoice_type == 'late_fee')), 1)

    def test_late_fee_respects_grace_period(self):
        lease = self._active_lease(late_fee_type='percent', late_fee_value=10, grace_days=30)
        lease.next_invoice_date = self.today - timedelta(days=10)
        lease._create_rent_invoices()
        self.env['rent.lease']._cron_apply_late_fees()
        self.assertFalse(lease.invoice_ids.filtered(lambda m: m.rent_invoice_type == 'late_fee'))

    def test_moveout_refund_calculation(self):
        lease = self._active_lease(maintenance_charge=0.0)
        lease.action_create_deposit_invoice()
        deposit_invoice = lease.deposit_invoice_id
        self.assertEqual(deposit_invoice.invoice_line_ids.account_id, self.deposit_account)
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=deposit_invoice.ids,
        ).create({})._create_payments()
        self.assertEqual(lease.deposit_status, 'received')

        lease.next_invoice_date = self.today
        rent_invoice = lease._create_rent_invoices()
        self.assertEqual(rent_invoice.amount_residual, 10000.0)

        wizard_form = Form(self.env['rent.moveout.wizard'].with_context(default_lease_id=lease.id))
        wizard_form.damage_charges = 2000.0
        wizard = wizard_form.save()
        self.assertEqual(wizard.unpaid_dues, 10000.0)
        self.assertEqual(wizard.refund_amount, 18000.0)

        wizard.action_confirm()
        self.assertEqual(lease.state, 'terminated')
        self.assertEqual(self.unit.state, 'vacant')
        self.assertEqual(lease.deposit_refunded_amount, 18000.0)
        self.assertEqual(lease.deposit_status, 'partially_refunded')
        credit_note = lease.deposit_refund_id
        self.assertEqual(credit_note.move_type, 'out_refund')
        self.assertEqual(credit_note.amount_total, 30000.0)
        # The deposit paid the rent and the damages; the rest is owed to the tenant.
        self.assertEqual(credit_note.amount_residual, 18000.0)
        # Settled by the credit note: Odoo flags such invoices 'reversed'.
        self.assertTrue(rent_invoice.currency_id.is_zero(rent_invoice.amount_residual))
