from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestRentUi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.portal_user = new_test_user(
            cls.env, login='rent_tenant', password='rent_tenant', groups='base.group_portal', name="Portal Tenant")
        cls.tenant = cls.portal_user.partner_id
        cls.tenant.is_tenant = True
        prop = cls.env['rent.property'].create({'name': "UI Tower"})
        cls.unit = cls.env['rent.unit'].create({'name': "U-1", 'property_id': prop.id, 'base_rent': 900})
        other_unit = cls.env['rent.unit'].create({'name': "U-2", 'property_id': prop.id})
        cls.lease = cls.env['rent.lease'].create({
            'tenant_id': cls.tenant.id,
            'unit_id': cls.unit.id,
            'start_date': today - relativedelta(months=1),
            'end_date': today + relativedelta(months=11),
            'rent_amount': 900,
        })
        cls.lease.action_confirm()
        cls.lease.action_activate()
        other_tenant = cls.env['res.partner'].create({'name': "Someone Else", 'is_tenant': True})
        cls.other_lease = cls.env['rent.lease'].create({
            'tenant_id': other_tenant.id,
            'unit_id': other_unit.id,
            'start_date': today,
            'end_date': today + relativedelta(years=1),
            'rent_amount': 500,
        })
        cls.other_lease.action_confirm()

    def test_dashboard_renders(self):
        self.browser_js(
            '/odoo/action-rent_management.rent_dashboard_action',
            """
            const check = () => {
                const kpis = document.querySelectorAll(
                    'button.o_rent_hero, button.o_rent_highlight, button.o_rent_tile');
                const sparklines = document.querySelectorAll('.o_rent_hero .o_rent_sparkline, .o_rent_highlight .o_rent_sparkline');
                const canvases = [...document.querySelectorAll('.o_rent_chart_canvas canvas')];
                // A chart without data shows a message instead of a canvas.
                const chartCards = canvases.length + document.querySelectorAll('.o_rent_card .o_rent_empty').length;
                const drawn = canvases.length >= 2 && canvases.every((canvas) => window.Chart && Chart.getChart(canvas));
                if (kpis.length === 16 && document.querySelectorAll('button.o_rent_hero').length === 1
                        && drawn && chartCards >= 3 && document.querySelector('.o_rent_table')
                        && !document.querySelector('.o_rent_skeleton')) {
                    console.log('test successful');
                } else if (kpis.length) {
                    console.log(`waiting: kpis=${kpis.length} sparklines=${sparklines.length} canvases=${canvases.length} drawn=${drawn}`);
                    setTimeout(check, 500);
                } else {
                    setTimeout(check, 200);
                }
            };
            check();
            """,
            login='admin',
        )

    def test_portal_pages(self):
        self.authenticate('rent_tenant', 'rent_tenant')
        for url in ('/my', '/my/leases', '/my/rent-invoices', '/my/maintenance', '/my/maintenance/new',
                    f'/my/leases/{self.lease.id}'):
            response = self.url_open(url)
            self.assertEqual(response.status_code, 200, url)
        self.assertIn(self.lease.name, self.url_open('/my/leases').text)

        # Another tenant's lease is not reachable.
        response = self.url_open(f'/my/leases/{self.other_lease.id}')
        self.assertNotIn(self.other_lease.name, response.text)

        response = self.url_open('/my/maintenance/new', data={
            'csrf_token': self.csrf_token(),
            'lease_id': str(self.lease.id),
            'category': 'plumbing',
            'description': "Tap is dripping",
        }, files={'photos': ('tap.png', b'\x89PNG\r\n\x1a\n', 'image/png')})
        self.assertEqual(response.status_code, 200)
        request = self.env['rent.maintenance.request'].search([('lease_id', '=', self.lease.id)])
        self.assertEqual(len(request), 1)
        self.assertRecordValues(request, [{'tenant_id': self.tenant.id, 'unit_id': self.unit.id, 'category': 'plumbing'}])
        self.assertEqual(len(request.image_ids), 1)

        # A forged lease id is rejected.
        self.url_open('/my/maintenance/new', data={
            'csrf_token': self.csrf_token(),
            'lease_id': str(self.other_lease.id),
            'category': 'plumbing',
            'description': "Not my unit",
        })
        self.assertFalse(self.env['rent.maintenance.request'].search([('lease_id', '=', self.other_lease.id)]))
