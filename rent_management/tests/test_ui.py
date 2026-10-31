import re
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, fields
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
            'priority': '3',
            'description': "Tap is dripping",
        }, files={'photos': ('tap.png', b'\x89PNG\r\n\x1a\n', 'image/png')})
        self.assertEqual(response.status_code, 200)
        request = self.env['rent.maintenance.request'].search([('lease_id', '=', self.lease.id)])
        self.assertEqual(len(request), 1)
        self.assertRecordValues(request, [{
            'tenant_id': self.tenant.id, 'unit_id': self.unit.id, 'category': 'plumbing', 'priority': '3'}])
        page = self.url_open(f'/my/maintenance/{request.id}').text
        self.assertIn("o_rp_tracker", page, "The request page shows the status tracker.")
        self.assertIn("Report a problem", self.url_open('/my/maintenance/new').text)
        self.assertEqual(len(request.image_ids), 1)

        # A forged lease id is rejected.
        self.url_open('/my/maintenance/new', data={
            'csrf_token': self.csrf_token(),
            'lease_id': str(self.other_lease.id),
            'category': 'plumbing',
            'description': "Not my unit",
        })
        self.assertFalse(self.env['rent.maintenance.request'].search([('lease_id', '=', self.other_lease.id)]))

    def test_tenant_dashboard(self):
        self.lease.next_invoice_date = fields.Date.today()
        invoice = self.lease._create_rent_invoices()
        self.authenticate('rent_tenant', 'rent_tenant')

        response = self.url_open('/my')
        self.assertTrue(response.url.endswith('/my/rent'), "Tenants land on their rent dashboard.")
        page = response.text
        for expected in ("Welcome", self.lease.name, self.unit.name, "Amount due", "Pay rent", invoice.name,
                         "Edit information", "Quick actions", "My tenancy"):
            self.assertIn(expected, page)
        self.assertIn(invoice.get_portal_url().split('?')[0], page)

        # Another tenant's lease cannot be displayed by changing the URL.
        page = self.url_open(f'/my/rent?lease_id={self.other_lease.id}').text
        self.assertNotIn(self.other_lease.name, page)
        self.assertIn(self.lease.name, page)

        # The standard portal home stays reachable.
        response = self.url_open('/my?all=1')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.url.endswith('/my/rent'))

    def test_non_tenant_portal_user_not_redirected(self):
        new_test_user(self.env, login='plain_portal', password='plain_portal', groups='base.group_portal')
        self.authenticate('plain_portal', 'plain_portal')
        self.assertFalse(self.url_open('/my').url.endswith('/my/rent'))
        self.assertFalse(self.url_open('/my/rent').url.endswith('/my/rent'), "Non-tenants are sent back to the portal home.")


    def test_tenant_invoices(self):
        self.lease.next_invoice_date = fields.Date.today() - relativedelta(days=10)
        overdue = self.lease._create_rent_invoices()
        self.lease.next_invoice_date = fields.Date.today() + relativedelta(days=3)
        upcoming = self.lease._create_rent_invoices()
        self.authenticate('rent_tenant', 'rent_tenant')

        response = self.url_open('/my/invoices')
        self.assertTrue(response.url.endswith('/my/rent-invoices'), "Tenants get the tenant invoice list.")
        page = response.text
        self.assertIn(overdue.name, page)
        self.assertIn(upcoming.name, page)
        self.assertIn("days late", page)

        page = self.url_open('/my/rent-invoices?filterby=overdue').text
        self.assertIn(overdue.name, page)
        self.assertNotIn(upcoming.name, page)
        page = self.url_open(f'/my/rent-invoices?search={upcoming.name}').text
        self.assertIn(upcoming.name, page)
        self.assertNotIn(overdue.name, page)

        page = self.url_open(overdue.get_portal_url()).text
        self.assertIn("o_rp_paper", page, "The invoice is shown with the tenant design.")
        self.assertIn("Download PDF", page)
        self.assertIn("Amount due", page)

    def test_invoice_page_standard_for_non_tenants(self):
        customer = new_test_user(self.env, login='plain_customer', password='plain_customer', groups='base.group_portal')
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': customer.partner_id.id,
            'invoice_line_ids': [(0, 0, {'name': "Service", 'quantity': 1, 'price_unit': 100})],
        })
        invoice.action_post()
        self.authenticate('plain_customer', 'plain_customer')
        self.assertFalse(self.url_open('/my/invoices').url.endswith('/my/rent-invoices'))
        self.assertNotIn("o_rp_paper", self.url_open(invoice.get_portal_url()).text)

    def test_modern_invoice_pdf(self):
        self.lease.next_invoice_date = fields.Date.today()
        invoice = self.lease._create_rent_invoices()
        self.authenticate('rent_tenant', 'rent_tenant')
        response = self.url_open(f'/my/invoices/{invoice.id}/modern-pdf?download=1', timeout=60)
        self.assertEqual(response.headers.get('Content-Type'), 'application/pdf')
        # In test mode Odoo returns the report's HTML instead of calling wkhtmltopdf.
        self.assertIn(b'o_rinv', response.content, "The modern invoice layout is used.")
        self.assertIn(invoice.name.encode(), response.content)
        self.assertIn('attachment', response.headers.get('Content-Disposition', ''))
        self.assertIn(invoice.name, self.url_open(invoice.get_portal_url()).text)
        self.assertIn('modern-pdf', self.url_open(invoice.get_portal_url()).text)

        # Someone else cannot download it.
        new_test_user(self.env, login='other_portal', password='other_portal', groups='base.group_portal')
        self.authenticate('other_portal', 'other_portal')
        response = self.url_open(f'/my/invoices/{invoice.id}/modern-pdf', timeout=60)
        self.assertNotEqual(response.headers.get('Content-Type'), 'application/pdf')

    def test_tenant_lease_pages(self):
        self.authenticate('rent_tenant', 'rent_tenant')
        page = self.url_open('/my/leases').text
        self.assertIn(self.lease.name, page)
        self.assertIn("o_rp_lease_card", page)
        self.assertNotIn(self.other_lease.name, page)
        page = self.url_open(f'/my/leases/{self.lease.id}').text
        for expected in ("o_rp_lease_hero", "Lease timeline", "Move-in", "Security deposit", "Download agreement"):
            self.assertIn(expected, page)
        self.assertFalse(self.url_open(f'/my/leases/{self.other_lease.id}').url.endswith(f'/my/leases/{self.other_lease.id}'))

    def test_agreement_download_is_current(self):
        # A stored PDF on the lease (e.g. an old snapshot) must not replace the current agreement.
        old = self.env['ir.attachment'].create({
            'name': 'old.pdf', 'raw': b'%PDF-old', 'res_model': 'rent.lease', 'res_id': self.lease.id,
        })
        self.lease.agreement_attachment_id = old
        self.authenticate('rent_tenant', 'rent_tenant')
        response = self.url_open(f'/my/leases/{self.lease.id}/agreement', timeout=60)
        self.assertEqual(response.headers.get('Content-Type'), 'application/pdf')
        self.assertIn(b'o_rlease', response.content, "The current agreement layout is generated.")
        self.assertEqual(self.url_open(f'/my/leases/{self.lease.id}/signed-copy').content, b'%PDF-old')
        self.assertIn("Signed copy", self.url_open(f'/my/leases/{self.lease.id}').text)


    def test_tenant_account_and_addresses(self):
        self.authenticate('rent_tenant', 'rent_tenant')
        account = self.url_open('/my/account')
        self.assertEqual(account.status_code, 200)
        # Tenant design, with the hooks of the standard portal scripts.
        for marker in ('o_rp_account_hero', 'o_customer_address_fill', 'o_portal_profile_card',
                       'id="save_address"', 'name="address_form"', 'name="street"', '% complete'):
            self.assertIn(marker, account.text)

        delivery = self.env['res.partner'].create({
            'name': "Parents' home", 'type': 'delivery', 'parent_id': self.tenant.id,
            'street': "1 Lake Road", 'city': "Pune", 'zip': "411001",
            'country_id': self.env.ref('base.in').id,
        })
        addresses = self.url_open('/my/addresses')
        self.assertEqual(addresses.status_code, 200)
        for marker in ('o_portal_addresses', 'o_rp_main_address', 'id="use_delivery_as_billing"',
                       'id="billing_container"', 'o_add_billing_address_btn', "1 Lake Road",
                       f'data-partner-id="{delivery.id}"'):
            self.assertIn(marker, addresses.text)

        form = self.url_open(f'/my/address?address_type=delivery&partner_id={delivery.id}')
        self.assertEqual(form.status_code, 200)
        self.assertIn('o_rp_address_form', form.text)
        self.assertIn('Edit address', form.text)

    def test_account_page_standard_for_non_tenants(self):
        new_test_user(self.env, login='plain_account', password='plain_account', groups='base.group_portal')
        self.authenticate('plain_account', 'plain_account')
        page = self.url_open('/my/account')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('o_rp_account_hero', page.text)
        self.assertIn('o_customer_address_fill', page.text)

    def test_tenant_security_page(self):
        self.authenticate('rent_tenant', 'rent_tenant')
        page = self.url_open('/my/security')
        self.assertEqual(page.status_code, 200)
        # Tenant design, keeping the hooks of the standard security scripts.
        for marker in ('o_rp_sec_hero', 'o_portal_security_body', 'o_rp_password_form', 'name="new1"',
                       'id="portal_revoke_all_sessions_popup"', 'id="portal_deactivate_account_modal"'):
            self.assertIn(marker, page.text)

        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
        wrong = self.url_open('/my/security', data={
            'csrf_token': csrf, 'op': 'password', 'old': 'nope', 'new1': 'N3w-pass!word', 'new2': 'N3w-pass!word'})
        self.assertIn('o_rp_sec_hero', wrong.text)
        self.assertIn('is-invalid', wrong.text, "A wrong current password is flagged on the tenant page.")
        done = self.url_open('/my/security', data={
            'csrf_token': csrf, 'op': 'password', 'old': 'rent_tenant', 'new1': 'N3w-pass!word', 'new2': 'N3w-pass!word'})
        self.assertIn('Your password was updated.', done.text)

    def test_security_page_standard_for_non_tenants(self):
        new_test_user(self.env, login='plain_security', password='plain_security', groups='base.group_portal')
        self.authenticate('plain_security', 'plain_security')
        page = self.url_open('/my/security')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('o_rp_sec_hero', page.text)
        self.assertIn('o_portal_security_body', page.text)

    def test_tenant_overdue_page(self):
        if not hasattr(self.env['account.move'], 'get_portal_last_transaction'):
            self.skipTest("account_payment is not installed")
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.tenant.id, 'rent_lease_id': self.lease.id,
            'invoice_date': date.today() - timedelta(days=40), 'invoice_date_due': date.today() - timedelta(days=10),
            'invoice_line_ids': [Command.create({'name': "Rent", 'quantity': 1, 'price_unit': 1600})],
        })
        invoice.action_post()
        self.authenticate('rent_tenant', 'rent_tenant')
        page = self.url_open('/my/invoices/overdue')
        self.assertEqual(page.status_code, 200)
        for marker in ('o_rp_overdue_hero', invoice.name, '10 days late', 'Total to pay', 'o_rp_pay_card'):
            self.assertIn(marker, page.text)

        # A partly paid invoice: the online payment is for what is still due, not the invoice total.
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids).create({'amount': 1000})._create_payments()
        self.assertEqual(invoice.amount_residual, 600)
        self.env.ref('payment.payment_provider_demo').sudo().write({'active': True, 'is_published': True})
        page = self.url_open('/my/invoices/overdue')
        self.assertIn('o_rp_payment_form', page.text)
        overdue = self.env['account.move'].search([
            ('partner_id', '=', self.tenant.id), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
            ('payment_state', 'not in', ('in_payment', 'paid', 'reversed')), ('invoice_date_due', '<', date.today())])
        amount = re.search(r'data-amount="([0-9.]+)"', page.text)
        self.assertTrue(amount, "The payment form is rendered with an amount.")
        self.assertEqual(float(amount.group(1)), sum(overdue.mapped('amount_residual')))
        self.assertLess(float(amount.group(1)), sum(overdue.mapped('amount_total')))

    def test_tenant_sign_out(self):
        self.authenticate('rent_tenant', 'rent_tenant')
        page = self.url_open('/my/rent')
        self.assertIn('action="/web/session/logout?redirect=/web/login"', page.text)
        csrf = page.text.split('class="o_rp_logout"')[1].split('name="csrf_token" value="')[1].split('"')[0]
        response = self.url_open('/web/session/logout?redirect=/web/login', data={'csrf_token': csrf})
        self.assertEqual(response.status_code, 200)
        self.assertIn('/web/login', response.url)
        self.assertNotIn('/my/rent', self.url_open('/my/rent').url, "Signed out: the dashboard asks to log in.")
