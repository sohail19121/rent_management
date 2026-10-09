from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager

MAX_PHOTOS = 5
MAX_PHOTO_SIZE = 10 * 1024 * 1024


class RentPortal(CustomerPortal):

    def _rent_partner(self):
        return request.env.user.partner_id.commercial_partner_id

    def _rent_lease_domain(self):
        return Domain('tenant_id', 'child_of', self._rent_partner().id) & Domain('state', '!=', 'draft')

    def _rent_invoice_domain(self):
        return Domain('rent_lease_id', '!=', False) & Domain('state', '=', 'posted') \
            & Domain('move_type', 'in', ('out_invoice', 'out_refund')) \
            & Domain('partner_id', 'child_of', self._rent_partner().id)

    def _rent_maintenance_domain(self):
        return Domain('tenant_id', 'child_of', self._rent_partner().id)

    def _prepare_portal_counter_values(self, counter):
        if counter == 'rent_lease_count':
            return 'rent.lease', self._rent_lease_domain(), 'read'
        if counter == 'rent_invoice_count':
            return 'account.move', self._rent_invoice_domain(), 'read'
        if counter == 'rent_maintenance_count':
            return 'rent.maintenance.request', self._rent_maintenance_domain(), 'read'
        return super()._prepare_portal_counter_values(counter)

    # ------------------------------------------------------------
    # Leases
    # ------------------------------------------------------------

    @http.route(['/my/leases', '/my/leases/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_leases(self, page=1, **kw):
        Lease = request.env['rent.lease']
        domain = self._rent_lease_domain()
        pager = portal_pager(
            url='/my/leases', total=Lease.search_count(domain), page=page, step=self._items_per_page)
        leases = Lease.search(domain, limit=self._items_per_page, offset=pager['offset'])
        values = self._prepare_portal_layout_values()
        values.update({
            'leases': leases.sudo(),
            'page_name': 'rent_lease',
            'pager': pager,
            'default_url': '/my/leases',
        })
        return request.render('rent_management.portal_my_leases', values)

    @http.route(['/my/leases/<int:lease_id>'], type='http', auth='public', website=True)
    def portal_lease_page(self, lease_id, access_token=None, **kw):
        try:
            lease_sudo = self._document_check_access('rent.lease', lease_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        values = self._get_page_view_values(
            lease_sudo, access_token, {'lease': lease_sudo, 'page_name': 'rent_lease'},
            'my_leases_history', False, **kw)
        return request.render('rent_management.portal_lease_page', values)

    @http.route(['/my/leases/<int:lease_id>/agreement'], type='http', auth='public', website=True)
    def portal_lease_agreement(self, lease_id, access_token=None, **kw):
        try:
            lease_sudo = self._document_check_access('rent.lease', lease_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        attachment = lease_sudo.agreement_attachment_id
        if attachment:
            return request.env['ir.binary']._get_stream_from(attachment).get_response(as_attachment=True)
        return self._show_report(
            model=lease_sudo, report_type='pdf',
            report_ref='rent_management.action_report_lease_agreement', download=True)

    # ------------------------------------------------------------
    # Rent invoices: the list is ours, the detail page and payment are the standard invoice portal.
    # ------------------------------------------------------------

    @http.route(['/my/rent-invoices', '/my/rent-invoices/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_rent_invoices(self, page=1, **kw):
        Move = request.env['account.move']
        domain = self._rent_invoice_domain()
        pager = portal_pager(
            url='/my/rent-invoices', total=Move.search_count(domain), page=page, step=self._items_per_page)
        invoices = Move.search(
            domain, order='invoice_date desc, id desc', limit=self._items_per_page, offset=pager['offset'])
        request.session['my_invoices_history'] = invoices.ids[:100]
        values = self._prepare_portal_layout_values()
        values.update({
            'invoices': invoices,
            'page_name': 'rent_invoice',
            'pager': pager,
            'default_url': '/my/rent-invoices',
        })
        return request.render('rent_management.portal_my_rent_invoices', values)

    # ------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------

    @http.route(['/my/maintenance', '/my/maintenance/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_maintenance(self, page=1, **kw):
        Request = request.env['rent.maintenance.request']
        domain = self._rent_maintenance_domain()
        pager = portal_pager(
            url='/my/maintenance', total=Request.search_count(domain), page=page, step=self._items_per_page)
        requests_ = Request.search(domain, limit=self._items_per_page, offset=pager['offset'])
        values = self._prepare_portal_layout_values()
        values.update({
            'maintenance_requests': requests_.sudo(),
            'page_name': 'rent_maintenance',
            'pager': pager,
            'default_url': '/my/maintenance',
        })
        return request.render('rent_management.portal_my_maintenance', values)

    @http.route(['/my/maintenance/<int:request_id>'], type='http', auth='public', website=True)
    def portal_maintenance_page(self, request_id, access_token=None, **kw):
        try:
            request_sudo = self._document_check_access('rent.maintenance.request', request_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        values = self._get_page_view_values(
            request_sudo, access_token,
            {'maintenance_request': request_sudo, 'page_name': 'rent_maintenance'},
            'my_maintenance_history', False, **kw)
        return request.render('rent_management.portal_maintenance_page', values)

    def _rent_running_leases(self):
        return request.env['rent.lease'].search(
            self._rent_lease_domain() & Domain('state', 'in', ('active', 'expiring'))).sudo()

    @http.route(['/my/maintenance/new'], type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_maintenance_new(self, **post):
        leases = self._rent_running_leases()
        Request = request.env['rent.maintenance.request']
        error = None
        if request.httprequest.method == 'POST':
            lease = leases.filtered(lambda lease: str(lease.id) == post.get('lease_id'))
            category = post.get('category')
            if not lease:
                error = request.env._("Select one of your leases.")
            elif category not in dict(Request._fields['category'].selection):
                error = request.env._("Select a category.")
            elif not (post.get('description') or '').strip():
                error = request.env._("Describe the problem.")
            if not error:
                # Tenant, unit and lease come from the tenant's own lease, not from the form.
                maintenance = Request.sudo().create({
                    'lease_id': lease.id,
                    'unit_id': lease.unit_id.id,
                    'tenant_id': lease.tenant_id.id,
                    'category': category,
                    'priority': '1',
                    'description': post['description'],
                })
                maintenance.message_subscribe(partner_ids=request.env.user.partner_id.ids)
                photos = request.httprequest.files.getlist('photos')[:MAX_PHOTOS]
                attachments = request.env['ir.attachment'].sudo()
                for photo in photos:
                    content = photo.read(MAX_PHOTO_SIZE + 1)
                    if not content or len(content) > MAX_PHOTO_SIZE or not (photo.mimetype or '').startswith('image/'):
                        continue
                    attachments |= attachments.create({
                        'name': photo.filename,
                        'raw': content,
                        'res_model': 'rent.maintenance.request',
                        'res_id': maintenance.id,
                    })
                if attachments:
                    maintenance.image_ids = attachments
                return request.redirect(f'/my/maintenance/{maintenance.id}')
        values = self._prepare_portal_layout_values()
        values.update({
            'leases': leases,
            'categories': Request._fields['category']._description_selection(request.env),
            'page_name': 'rent_maintenance_new',
            'error': error,
            'post': post,
        })
        return request.render('rent_management.portal_maintenance_new', values)
