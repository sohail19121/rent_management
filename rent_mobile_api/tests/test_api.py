import base64
import json

from datetime import date, timedelta

from odoo.tests import HttpCase, new_test_user, tagged

API = '/rent/api/v1'
# 1x1 PNG
PNG = base64.b64encode(base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')).decode()


@tagged('post_install', '-at_install')
class TestRentMobileApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(cls.env, 'rm_admin', groups='rent_management.group_rent_admin')
        cls.manager = new_test_user(cls.env, 'rm_manager', groups='rent_management.group_rent_user')
        cls.other_manager = new_test_user(cls.env, 'rm_other', groups='rent_management.group_rent_user')
        cls.tenant_partner = cls.env['res.partner'].create({
            'name': 'Api Tenant', 'email': 'api.tenant@example.com', 'is_tenant': True})
        cls.tenant_user = new_test_user(cls.env, 'rm_tenant', groups='base.group_portal',
                                        partner_id=cls.tenant_partner.id)
        cls.property = cls.env['rent.property'].create({'name': 'Api Tower', 'manager_id': cls.manager.id})
        cls.other_property = cls.env['rent.property'].create({'name': 'Other', 'manager_id': cls.other_manager.id})
        cls.unit = cls.env['rent.unit'].create({
            'name': 'A-101', 'property_id': cls.property.id, 'base_rent': 10000, 'deposit_amount': 20000,
            'meter_number': 'M-1'})
        cls.lease = cls.env['rent.lease'].create({
            'tenant_id': cls.tenant_partner.id, 'unit_id': cls.unit.id, 'rent_amount': 10000,
            'deposit_amount': 20000, 'start_date': date.today() - timedelta(days=40),
            'end_date': date.today() + timedelta(days=300), 'electricity_billing': 'metered',
            'electricity_rate': 8})
        cls.lease.action_confirm()
        cls.lease.action_activate()
        if not cls.env.company.rent_deposit_account_id:
            cls.env.company.rent_deposit_account_id = cls.env['account.account'].search([
                ('account_type', '=', 'liability_current'), ('company_ids', 'in', cls.env.company.id)], limit=1)

    def _call(self, method, path, token=None, body=None, status=200):
        headers = {'Content-Type': 'application/json', 'X-Odoo-Database': self.env.cr.dbname}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        response = self.url_open(f'{API}{path}', data=json.dumps(body) if body is not None else None,
                                 headers=headers, method=method)
        self.assertEqual(response.status_code, status, response.text)
        if response.headers.get('Content-Type', '').startswith('application/json'):
            return response.json()
        return response

    def _login(self, login):
        return self._call('POST', '/auth/login', body={'login': login, 'password': login})

    def test_login(self):
        self._call('POST', '/auth/login', body={'login': 'rm_admin', 'password': 'wrong'}, status=401)
        data = self._login('rm_admin')
        self.assertEqual(data['user']['role'], 'admin')
        self.assertEqual(self._call('GET', '/me', data['token'])['login'], 'rm_admin')
        self.assertEqual(self._login('rm_tenant')['user']['role'], 'tenant')
        self.assertEqual(self._login('rm_manager')['user']['role'], 'manager')
        self._call('GET', '/me', 'not-a-token', status=401)
        self._call('POST', '/auth/logout', data['token'])
        self._call('GET', '/me', data['token'], status=401)

    def test_staff_flow(self):
        token = self._login('rm_admin')['token']
        dashboard = self._call('GET', '/dashboard', token)
        self.assertTrue(dashboard['sections'])
        self._call('GET', '/meta', token)
        tenant = self._call('POST', '/tenants', token, {'name': 'New Tenant', 'email': 'new.tenant@example.com'})
        unit = self._call('POST', '/units', token, {
            'name': 'B-1', 'property_id': self.property.id, 'base_rent': 5000, 'deposit_amount': 1000,
            'unit_type': 'flat', 'image': PNG})
        self.assertTrue(unit['image_url'])
        self.url_open(unit['image_url'], headers={'Authorization': f'Bearer {token}'}).raise_for_status()
        lease = self._call('POST', '/leases', token, {
            'tenant_id': tenant['id'], 'unit_id': unit['id'], 'start_date': str(date.today())})
        self.assertEqual(lease['rent_amount'], 5000)
        self.assertIn('confirm', lease['actions'])
        lease = self._call('POST', f"/leases/{lease['id']}/action/confirm", token)['lease']
        lease = self._call('POST', f"/leases/{lease['id']}/action/activate", token)['lease']
        self.assertEqual(lease['state'], 'active')
        result = self._call('POST', f"/leases/{lease['id']}/action/deposit_invoice", token)
        invoice_id = result['res_ids'][0]
        invoice = self._call('GET', f'/invoices/{invoice_id}', token)
        self.assertTrue(invoice['can_register_payment'])
        invoice = self._call('POST', f'/invoices/{invoice_id}/payment', token, {})
        self.assertEqual(invoice['status'], 'paid')
        pdf = self._call('GET', f"/leases/{lease['id']}/agreement", token)
        self.assertEqual(pdf.headers['Content-Type'], 'application/pdf')
        preview = self._call('POST', f"/leases/{lease['id']}/moveout/preview", token, {'damage_charges': 100})
        self.assertEqual(preview['refund_amount'], 900)
        lease = self._call('POST', f"/leases/{lease['id']}/moveout", token, {'damage_charges': 100})['lease']
        self.assertEqual(lease['state'], 'terminated')
        self._call('POST', '/leases/1/action/unlink', token, status=404)
        self._call('POST', f"/tenants/{tenant['id']}/invite", token)
        self.assertTrue(self.env['res.users'].search([('login', '=', 'new.tenant@example.com')]))

    def test_manager_rules(self):
        token = self._login('rm_manager')['token']
        ids = [p['id'] for p in self._call('GET', '/properties', token)['items']]
        self.assertIn(self.property.id, ids)
        self.assertNotIn(self.other_property.id, ids)
        self._call('GET', f'/properties/{self.other_property.id}', token, status=403)
        self._call('GET', '/invoices', token, status=403)
        self._call('POST', f'/leases/{self.lease.id}/action/generate_invoice', token, status=403)
        # Meter reading by scanning the QR label.
        entry = self._call('POST', '/meter/scan', token, {'code': self.unit.meter_qr_url})
        self.assertEqual(entry['lease']['id'], self.lease.id)
        reading = self._call('POST', f'/units/{self.unit.id}/meter', token,
                             {'current_reading': 120, 'rate': 8, 'photo': PNG})
        self.assertEqual(reading['state'], 'confirmed')
        self.assertEqual(reading['consumption'], 120)
        request = self._call('POST', '/maintenance', token, {
            'unit_id': self.unit.id, 'category': 'plumbing', 'description': 'Leak'})
        request = self._call('POST', f"/maintenance/{request['id']}/action/start", token)
        self.assertEqual(request['state'], 'in_progress')
        self._call('POST', '/units', token, {'name': 'X', 'property_id': self.other_property.id}, status=403)

    def test_tenant_flow(self):
        token = self._login('rm_tenant')['token']
        dashboard = self._call('GET', '/dashboard', token)
        self.assertEqual(dashboard['lease']['id'], self.lease.id)
        self.assertEqual([l['id'] for l in self._call('GET', '/leases', token)['items']], [self.lease.id])
        self._call('GET', '/properties', token, status=403)
        self._call('POST', f'/leases/{self.lease.id}/action/confirm', token, status=403)
        request = self._call('POST', '/maintenance', token, {
            'lease_id': self.lease.id, 'category': 'electrical', 'priority': '2',
            'description': 'No power', 'photos': [PNG]})
        self.assertEqual(request['tenant']['id'], self.tenant_partner.id)
        self.assertEqual(len(request['photos']), 1)
        self.url_open(request['photos'][0], headers={'Authorization': f'Bearer {token}'}).raise_for_status()
        self._call('POST', f"/messages/rent.maintenance.request/{request['id']}", token, {'body': 'Please hurry'})
        self.assertTrue(self._call('GET', f"/messages/rent.maintenance.request/{request['id']}", token)['items'])
        self._call('GET', f'/leases/{self.lease.id}/agreement', token)
        other = self.env['rent.lease'].create({
            'tenant_id': self.env['res.partner'].create({'name': 'Someone'}).id, 'unit_id': self.unit.id,
            'rent_amount': 1, 'start_date': date.today() + timedelta(days=400),
            'end_date': date.today() + timedelta(days=700)})
        other.action_confirm()
        self._call('GET', f'/leases/{other.id}', token, status=404)
        self._call('PUT', '/me', token, {'phone': '+911234567890'})
        self.assertEqual(self.tenant_partner.phone, '+911234567890')

    def test_app_endpoints(self):
        token = self._login('rm_admin')['token']
        self.assertIn('lease_state', self._call('GET', '/meta', token)['selections'])
        for kind in ('properties', 'units', 'vacant_units', 'tenants', 'owners', 'vendors', 'users', 'amenities',
                     'countries', 'states', 'running_leases', 'metered_leases', 'payment_journals'):
            self._call('GET', f'/options/{kind}?search=a', token)
        self._call('GET', '/options/nope', token, status=404)
        settings = self._call('PUT', '/settings', token, {'rent_invoice_advance_days': 7})
        self.assertEqual(settings['rent_invoice_advance_days'], 7)
        self._call('GET', '/activities', token)
        for period in ('last_month', 'this_year', 'last_12_months'):
            self._call('GET', f'/dashboard?period={period}', token)
        for status in ('to_pay', 'overdue', 'paid', 'credit'):
            self._call('GET', f'/invoices?status={status}', token)
        self._call('GET', '/units?state=vacant', token)
        self._call('GET', f'/units/{self.unit.id}', token)
        self._call('GET', f'/properties/{self.property.id}', token)
        self._call('GET', f'/tenants/{self.tenant_partner.id}', token)
        self._call('GET', '/tenants?search=Api', token)
        self._call('GET', '/maintenance?state=open&mine=1', token)
        # Draft reading edited from the app, then confirmed and invoiced.
        reading = self.env['rent.electricity.reading'].create({
            'lease_id': self.lease.id, 'period_start': date.today() - timedelta(days=30),
            'period_end': date.today() - timedelta(days=1)})
        data = self._call('PUT', f'/readings/{reading.id}', token, {'current_reading': '55', 'meter_photo': PNG})
        self.assertEqual(data['consumption'], 55)
        self.assertTrue(data['photo_url'])
        self._call('POST', f'/readings/{reading.id}/action/confirm', token)
        result = self._call('POST', '/readings/invoice', token, {'ids': [reading.id]})
        self.assertEqual(result['res_model'], 'account.move')
        self._call('GET', f"/invoices/{result['res_ids'][0]}/pdf", token)
        self.assertEqual(self._call('GET', f'/readings?state=invoiced&lease_id={self.lease.id}', token)['total'], 1)
        self._call('PUT', '/me', token, {'city': 'Pune'})
        me = self._call('GET', '/me', token)
        self.assertEqual(me['city'], 'Pune')
        tenant_token = self._login('rm_tenant')['token']
        self._call('GET', '/settings', tenant_token, status=403)
        self._call('GET', '/options/tenants', tenant_token, status=403)
        readings = self._call('GET', '/readings', tenant_token)['items']
        self.assertTrue(readings)
        for item in readings:
            self.assertEqual(item['lease']['id'], self.lease.id)
            self.assertIn(item['state'], ('confirmed', 'invoiced'))
        self._call('GET', '/invoices', tenant_token)
        self._call('GET', '/activities', tenant_token)
