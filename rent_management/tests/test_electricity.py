from datetime import date

from freezegun import freeze_time

from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestRentElectricity(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('rent_management.group_rent_admin')
        cls.env.company.write({
            'rent_deposit_account_id': cls.env['account.account'].create({
                'name': "Tenant Security Deposits", 'code': 'RENTDEP', 'account_type': 'liability_current',
            }).id,
            'rent_electricity_rate': 8.0,
        })
        cls.tenant = cls.env['res.partner'].create({'name': "Meter Tenant", 'is_tenant': True})
        prop = cls.env['rent.property'].create({'name': "Meter Tower"})
        cls.unit = cls.env['rent.unit'].create({'name': "M-1", 'property_id': prop.id, 'meter_number': 'MTR-001'})

    def _active_lease(self, **vals):
        lease = self.env['rent.lease'].create({
            'tenant_id': self.tenant.id,
            'unit_id': self.unit.id,
            'start_date': date(2026, 7, 1),
            'end_date': date(2027, 6, 30),
            'rent_amount': 10000,
            'deposit_amount': 30000,
            'electricity_billing': 'metered',
            'electricity_fixed_amount': 100,
            'electricity_opening_reading': 1000,
            **vals,
        })
        lease.action_confirm()
        lease.action_activate()
        return lease

    @freeze_time('2026-08-01')
    def test_monthly_reading_billed_with_rent(self):
        lease = self._active_lease()
        self.assertEqual(lease.electricity_rate, 8.0, "The rate defaults from the company settings.")

        readings = self.env['rent.lease']._cron_prepare_electricity_readings()
        self.assertEqual(len(readings), 1)
        self.assertRecordValues(readings, [{
            'lease_id': lease.id,
            'period_start': date(2026, 7, 1),
            'period_end': date(2026, 7, 31),
            'previous_reading': 1000.0,
            'state': 'draft',
        }])
        self.assertTrue(readings.activity_ids, "The manager is asked to enter the reading.")
        # Running the cron again does not duplicate the reading.
        self.assertFalse(self.env['rent.lease']._cron_prepare_electricity_readings())

        readings.current_reading = 1120
        readings.action_confirm()
        self.assertEqual(readings.consumption, 120.0)
        self.assertEqual(readings.amount, 120 * 8.0 + 100)

        lease.next_invoice_date = date(2026, 8, 1)
        invoice = lease._create_rent_invoices()
        self.assertEqual(invoice.amount_total, 10000 + 1060)
        self.assertEqual(readings.state, 'invoiced')
        self.assertEqual(readings.invoice_id, invoice)

        with freeze_time('2026-09-01'):
            september = self.env['rent.lease']._cron_prepare_electricity_readings()
        self.assertEqual(september.previous_reading, 1120.0, "The previous reading carries over from last month.")
        self.assertEqual(september.period_start, date(2026, 8, 1))

    @freeze_time('2026-08-01')
    def test_cancel_or_delete_invoice_releases_reading_and_period(self):
        lease = self._active_lease(electricity_fixed_amount=0)
        reading = self.env['rent.lease']._cron_prepare_electricity_readings()
        reading.current_reading = 1100
        reading.action_confirm()
        lease.next_invoice_date = date(2026, 8, 1)

        first = lease._create_rent_invoices()
        self.assertEqual(first.amount_total, 10800.0)
        self.assertEqual(lease.next_invoice_date, date(2026, 9, 1))

        first.button_cancel()
        self.assertEqual(reading.state, 'confirmed')
        self.assertFalse(reading.invoice_id)
        self.assertEqual(lease.next_invoice_date, date(2026, 8, 1), "The cancelled period is invoiced again.")
        with self.assertRaises(UserError):
            first.button_draft()

        second = lease._create_rent_invoices()
        self.assertEqual(second.amount_total, 10800.0, "Rent and electricity are on the new invoice again.")
        self.assertEqual(reading.invoice_id, second)

        # Deleting (reset to draft, then delete) behaves the same.
        second.button_draft()
        second.unlink()
        self.assertEqual(reading.state, 'confirmed')
        self.assertEqual(lease.next_invoice_date, date(2026, 8, 1))

        # Only the latest rent invoice moves the billing date back.
        august = lease._create_rent_invoices()
        lease._create_rent_invoices()
        august.button_cancel()
        self.assertEqual(lease.next_invoice_date, date(2026, 10, 1))

    @freeze_time('2026-08-01')
    def test_missed_month_is_covered(self):
        lease = self._active_lease()
        july = self.env['rent.lease']._cron_prepare_electricity_readings()
        july.current_reading = 1100
        july.action_confirm()
        # The cron did not run at all in September: October's reading covers August and September.
        with freeze_time('2026-10-01'):
            reading = self.env['rent.lease']._cron_prepare_electricity_readings()
        self.assertRecordValues(reading, [{
            'lease_id': lease.id,
            'period_start': date(2026, 8, 1),
            'period_end': date(2026, 9, 30),
            'previous_reading': 1100.0,
        }])

    @freeze_time('2026-08-01')
    def test_reading_lower_than_previous(self):
        lease = self._active_lease()
        reading = self.env['rent.lease']._cron_prepare_electricity_readings()
        reading.current_reading = 900
        with self.assertRaises(ValidationError):
            reading.action_confirm()
        with self.assertRaises(ValidationError):
            self.env['rent.electricity.reading'].create({
                'lease_id': lease.id, 'period_start': date(2026, 7, 15), 'period_end': date(2026, 7, 31),
            })

    @freeze_time('2026-08-01')
    def test_invoice_readings_now(self):
        lease = self._active_lease(electricity_fixed_amount=0)
        reading = self.env['rent.lease']._cron_prepare_electricity_readings()
        reading.current_reading = 1050
        reading.action_confirm()
        reading.action_create_invoice()
        self.assertEqual(reading.state, 'invoiced')
        self.assertRecordValues(reading.invoice_id, [{
            'rent_invoice_type': 'electricity', 'amount_total': 400.0, 'rent_lease_id': lease.id,
        }])

    @freeze_time('2026-08-01')
    def test_fixed_electricity_on_rent_invoice(self):
        lease = self._active_lease(electricity_billing='fixed', electricity_fixed_amount=750)
        self.assertFalse(self.env['rent.lease']._cron_prepare_electricity_readings())
        lease.next_invoice_date = date(2026, 8, 1)
        invoice = lease._create_rent_invoices()
        self.assertEqual(invoice.amount_total, 10750.0)

    @freeze_time('2026-08-20')
    def test_moveout_final_reading(self):
        lease = self._active_lease(electricity_fixed_amount=0)
        lease.action_create_deposit_invoice()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=lease.deposit_invoice_id.ids,
        ).create({})._create_payments()
        july = self.env['rent.electricity.reading'].create({
            'lease_id': lease.id, 'period_start': date(2026, 7, 1), 'period_end': date(2026, 7, 31),
            'current_reading': 1100,
        })
        july.action_confirm()

        wizard_form = Form(self.env['rent.moveout.wizard'].with_context(default_lease_id=lease.id))
        self.assertEqual(wizard_form.previous_meter_reading, 1100.0)
        wizard_form.final_meter_reading = 1150
        wizard = wizard_form.save()
        # July (100 kWh) is not billed yet, plus 50 kWh until the move-out: 150 * 8.
        self.assertEqual(wizard.electricity_charges, 1200.0)
        self.assertEqual(wizard.refund_amount, 30000 - 1200)

        wizard.action_confirm()
        self.assertEqual(lease.deposit_refunded_amount, 28800.0)
        self.assertEqual(lease.moveout_electricity_charges, 1200.0)
        final = lease.electricity_reading_ids.filtered(lambda r: r.period_end == date(2026, 8, 20))
        self.assertRecordValues(final, [{'previous_reading': 1100.0, 'current_reading': 1150.0, 'state': 'invoiced'}])
        self.assertEqual(july.state, 'invoiced')
        self.assertEqual(lease.deposit_refund_id.amount_residual, 28800.0)
