import io

from dateutil.relativedelta import relativedelta
from PIL import Image

from odoo import fields
from odoo.tests import Form, HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestMeterQr(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.manager = new_test_user(
            cls.env, login='meter_mgr', password='meter_mgr', groups='rent_management.group_rent_user', name="Meter Manager")
        new_test_user(cls.env, login='other_mgr', password='other_mgr', groups='rent_management.group_rent_user')
        new_test_user(cls.env, login='meter_portal', password='meter_portal', groups='base.group_portal')
        prop = cls.env['rent.property'].create({'name': "QR Tower", 'manager_id': cls.manager.id})
        cls.unit = cls.env['rent.unit'].create({'name': "Q-1", 'property_id': prop.id, 'meter_number': 'MTR-QR-1'})
        cls.tenant = cls.env['res.partner'].create({'name': "QR Tenant", 'is_tenant': True})
        cls.lease = cls.env['rent.lease'].create({
            'tenant_id': cls.tenant.id,
            'unit_id': cls.unit.id,
            'start_date': today - relativedelta(months=1),
            'end_date': today + relativedelta(months=11),
            'rent_amount': 1000,
            'electricity_billing': 'metered',
            'electricity_rate': 8.0,
            'electricity_opening_reading': 1000,
        })
        cls.lease.action_confirm()
        cls.lease.action_activate()
        cls.url = f'/rent/meter/{cls.unit.meter_qr_token}'

    def _post(self, **data):
        return self.url_open(self.url, data={'csrf_token': self.csrf_token(), **data})

    def test_qr_image_and_unique_token(self):
        other = self.env['rent.unit'].create({'name': "Q-2", 'property_id': self.unit.property_id.id})
        self.assertTrue(self.unit.meter_qr_image)
        self.assertTrue(self.unit.meter_qr_url.endswith(self.url))
        self.assertNotEqual(other.meter_qr_token, self.unit.meter_qr_token)
        # Several units at once, as in list views and the label sheet.
        units = self.unit | other
        self.assertTrue(all(units.mapped('meter_qr_image')))
        html, _ = self.env['ir.actions.report']._render_qweb_html('rent_management.action_report_meter_qr_label', units.ids)
        self.assertEqual(html.count(b'data:image/png;base64'), 2)

    def test_scan_and_save_reading(self):
        self.authenticate('meter_mgr', 'meter_mgr')
        page = self.url_open(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertIn("QR Tenant", page.text)
        self.assertIn(self.lease.name, page.text)
        self.assertIn("1000.0", page.text)

        photo = io.BytesIO()
        Image.new('RGB', (4, 4), 'white').save(photo, format='PNG')
        response = self.url_open(self.url, data={
            'csrf_token': self.csrf_token(), 'current_reading': '1100', 'rate': '9', 'apply_rate': '1',
        }, files={'photo': ('meter.png', photo.getvalue(), 'image/png')})
        self.assertIn("Reading saved", response.text)
        reading = self.lease.electricity_reading_ids
        self.assertRecordValues(reading, [{
            'state': 'confirmed', 'previous_reading': 1000.0, 'current_reading': 1100.0,
            'consumption': 100.0, 'rate': 9.0, 'amount': 900.0,
        }])
        self.assertTrue(reading.meter_photo)
        self.assertEqual(self.lease.electricity_rate, 9.0, "The new rate is kept for the next months.")

    def test_scan_fills_prepared_reading(self):
        prepared = self.env['rent.lease']._cron_prepare_electricity_readings()
        self.assertTrue(prepared)
        self.authenticate('meter_mgr', 'meter_mgr')
        self._post(current_reading='1050', rate='8')
        self.assertEqual(self.lease.electricity_reading_ids, prepared, "The prepared reading is filled, not duplicated.")
        self.assertEqual(prepared.state, 'confirmed')
        self.assertEqual(self.lease.electricity_rate, 8.0)

    def test_unmetered_lease_explained(self):
        self.lease.electricity_billing = 'none'
        self.authenticate('meter_mgr', 'meter_mgr')
        page = self.url_open(self.url).text
        self.assertIn(self.lease.name, page)
        self.assertIn(f'/odoo/rent.lease/{self.lease.id}', page)
        self.assertNotIn('name="current_reading"', page)

    def test_new_lease_defaults_to_metered(self):
        other = self.env['rent.unit'].create({'name': "Q-9", 'property_id': self.unit.property_id.id, 'meter_number': 'M-9'})
        with Form(self.env['rent.lease']) as lease_form:
            lease_form.tenant_id = self.tenant
            lease_form.unit_id = other
            self.assertEqual(lease_form.electricity_billing, 'metered')

    def test_reading_lower_than_previous(self):
        self.authenticate('meter_mgr', 'meter_mgr')
        response = self._post(current_reading='900', rate='8')
        self.assertIn("cannot be lower", response.text)
        self.assertFalse(self.lease.electricity_reading_ids.filtered(lambda r: r.state == 'confirmed'))

    def test_access(self):
        self.authenticate('other_mgr', 'other_mgr')
        self.assertIn("not valid anymore", self.url_open(self.url).text)
        self.authenticate('meter_portal', 'meter_portal')
        self.assertIn("Only property managers", self.url_open(self.url).text)

        old_url = self.url
        self.unit.action_regenerate_meter_qr()
        self.authenticate('meter_mgr', 'meter_mgr')
        self.assertIn("not valid anymore", self.url_open(old_url).text)
