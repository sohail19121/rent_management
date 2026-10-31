from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.fields import Domain
from odoo.http import request

from odoo import fields
from odoo.addons.account.controllers.portal import PortalAccount
from odoo.addons.portal.controllers.portal import pager as portal_pager

MAX_PHOTOS = 5
MAX_PHOTO_SIZE = 10 * 1024 * 1024


class RentPortal(PortalAccount):
    # Subclass of the accounting portal (itself a CustomerPortal) so that the invoice routes
    # overridden below are always reached, whatever the load order of account_payment.

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
    # Tenant dashboard: the tenant's home page on the portal
    # ------------------------------------------------------------

    def _rent_is_tenant(self):
        return bool(request.env['rent.lease'].search_count(self._rent_lease_domain(), limit=1))

    @http.route()
    def home(self, **kw):
        # Tenants land on their rent dashboard; '/my?all=1' still shows the standard portal home.
        if not kw.get('all') and not request.env.user._is_internal() and self._rent_is_tenant():
            return request.redirect('/my/rent')
        return super().home(**kw)

    def _rent_shell_values(self, lease_id=None, **values):
        """Values of the tenant pages' shell (sidebar, header) plus the page's own values."""
        shell = self._prepare_portal_layout_values()
        if not request.env.user._is_public() and self._rent_is_tenant():
            shell.update(request.env.user.partner_id._rent_portal_dashboard(lease_id=lease_id))
            shell['rent_shell'] = True
        shell.update(values)
        return shell

    @http.route(['/my/rent'], type='http', auth='user', website=True)
    def portal_rent_dashboard(self, lease_id=None, **kw):
        if not self._rent_is_tenant():
            return request.redirect('/my?all=1')
        try:
            lease_id = int(lease_id) if lease_id else None
        except ValueError:
            lease_id = None
        values = self._rent_shell_values(lease_id=lease_id, page_name='rent_dashboard', no_breadcrumbs=True,
                                         rent_active='dashboard')
        return request.render('rent_management.portal_rent_dashboard', values)

    # ------------------------------------------------------------
    # Leases
    # ------------------------------------------------------------

    @http.route(['/my/leases', '/my/leases/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_leases(self, page=1, **kw):
        Lease = request.env['rent.lease']
        domain = self._rent_lease_domain()
        pager = portal_pager(
            url='/my/leases', total=Lease.search_count(domain), page=page, step=self._items_per_page)
        leases = Lease.search(domain, limit=self._items_per_page, offset=pager['offset']).sudo()
        order = {'active': 0, 'expiring': 0, 'confirmed': 1}
        leases = leases.sorted(lambda lease: (order.get(lease.state, 2), -lease.start_date.toordinal()))
        values = self._rent_shell_values(rent_active='leases')
        running = leases.filtered(lambda lease: lease.state in ('active', 'expiring'))
        values.update({
            'lease_cards': [(lease, lease._rent_portal_lease_values()) for lease in leases],
            'running_count': len(running),
            'monthly_rent_total': sum(running.mapped('rent_amount')),
            'next_end': running.sorted('end_date')[:1],
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
        shell = self._rent_shell_values(lease_id=lease_sudo.id, rent_active='leases')
        shell.update(lease_sudo._rent_portal_lease_values())
        shell.update(lease=lease_sudo, page_name='rent_lease')
        values = self._get_page_view_values(lease_sudo, access_token, shell, 'my_leases_history', False, **kw)
        return request.render('rent_management.portal_lease_page', values)

    @http.route(['/my/leases/<int:lease_id>/agreement'], type='http', auth='public', website=True)
    def portal_lease_agreement(self, lease_id, access_token=None, **kw):
        try:
            lease_sudo = self._document_check_access('rent.lease', lease_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        # Always the current agreement; an uploaded signed copy has its own link.
        return self._show_report(
            model=lease_sudo, report_type='pdf',
            report_ref='rent_management.action_report_lease_agreement', download=kw.get('download', True) != '0')

    @http.route(['/my/leases/<int:lease_id>/signed-copy'], type='http', auth='public', website=True)
    def portal_lease_signed_copy(self, lease_id, access_token=None, **kw):
        """The signed agreement uploaded on the lease (scan, e-signed PDF...)."""
        try:
            lease_sudo = self._document_check_access('rent.lease', lease_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        attachment = lease_sudo.agreement_attachment_id
        if not attachment:
            return request.redirect(f'/my/leases/{lease_id}/agreement')
        return request.env['ir.binary']._get_stream_from(attachment).get_response(as_attachment=True)

    # ------------------------------------------------------------
    # Rent invoices: the list is ours, the detail page and payment are the standard invoice portal.
    # ------------------------------------------------------------

    INVOICE_FILTERS = ('all', 'to_pay', 'overdue', 'paid', 'credit')

    def _rent_tenant_invoice_domain(self, filterby='all'):
        """All posted customer invoices and credit notes of the tenant, optionally filtered."""
        today = fields.Date.context_today(request.env.user)
        domain = Domain('partner_id', 'child_of', self._rent_partner().id) & Domain('state', '=', 'posted') \
            & Domain('move_type', 'in', ('out_invoice', 'out_refund'))
        unpaid = Domain('move_type', '=', 'out_invoice') & Domain('payment_state', 'in', ('not_paid', 'partial'))
        return domain & {
            'all': Domain.TRUE,
            'to_pay': unpaid & (Domain('invoice_date_due', '>=', today) | Domain('invoice_date_due', '=', False)),
            'overdue': unpaid & Domain('invoice_date_due', '<', today),
            'paid': Domain('move_type', '=', 'out_invoice') & Domain('payment_state', 'in', ('paid', 'in_payment', 'reversed')),
            'credit': Domain('move_type', '=', 'out_refund'),
        }[filterby]

    @http.route(['/my/rent-invoices', '/my/rent-invoices/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_rent_invoices(self, page=1, filterby='all', search='', **kw):
        Move = request.env['account.move']
        filterby = filterby if filterby in self.INVOICE_FILTERS else 'all'
        search = (search or '').strip()
        domain = self._rent_tenant_invoice_domain(filterby)
        if search:
            domain &= Domain('name', 'ilike', search) | Domain('invoice_origin', 'ilike', search) \
                | Domain('ref', 'ilike', search)
        url_args = {k: v for k, v in (('filterby', filterby), ('search', search)) if v and v != 'all'}
        pager = portal_pager(url='/my/rent-invoices', url_args=url_args, total=Move.search_count(domain),
                             page=page, step=self._items_per_page)
        invoices = Move.search(domain, order='invoice_date desc, id desc',
                               limit=self._items_per_page, offset=pager['offset'])
        request.session['my_invoices_history'] = invoices.ids[:100]

        # Invoices grouped by month of issue.
        groups = []
        for invoice in invoices:
            label = invoice.invoice_date.strftime('%B %Y') if invoice.invoice_date else request.env._("Undated")
            if not groups or groups[-1][0] != label:
                groups.append((label, []))
            groups[-1][1].append(invoice)

        all_invoices = Move.search(self._rent_tenant_invoice_domain()).sudo()
        today = fields.Date.context_today(request.env.user)
        unpaid = all_invoices.filtered(
            lambda m: m.move_type == 'out_invoice' and m.payment_state in ('not_paid', 'partial'))
        overdue = unpaid.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < today)
        payments = request.env['rent.property'].sudo()._dashboard_payments(
            all_invoices.filtered(lambda m: m.move_type == 'out_invoice'))
        values = self._rent_shell_values(rent_active='invoices')
        values.update({
            'invoice_groups': groups,
            'invoice_total': len(invoices),
            'filterby': filterby,
            'search': search,
            'filter_tabs': [
                (key, label, Move.search_count(self._rent_tenant_invoice_domain(key)))
                for key, label in (
                    ('all', request.env._("All")), ('to_pay', request.env._("To pay")),
                    ('overdue', request.env._("Overdue")), ('paid', request.env._("Paid")),
                    ('credit', request.env._("Credit notes")))
            ],
            'outstanding_amount': sum(unpaid.mapped('amount_residual')),
            'outstanding_count': len(unpaid),
            'overdue_total': sum(overdue.mapped('amount_residual')),
            'overdue_count': len(overdue),
            'paid_year_total': sum(p['amount'] for p in payments if p['date'].year == today.year),
            'can_pay_overdue': bool(overdue) and 'account_payment' in request.env.registry._init_modules,
            'page_name': 'rent_invoice',
            'pager': pager,
            'default_url': '/my/rent-invoices',
            'today': today,
        })
        return request.render('rent_management.portal_my_rent_invoices', values)

    # ------------------------------------------------------------
    # Standard invoice pages, in the tenant design
    # ------------------------------------------------------------

    @http.route(['/my/invoices/<int:invoice_id>/modern-pdf'], type='http', auth='public', website=True)
    def portal_rent_invoice_pdf(self, invoice_id, access_token=None, download=False, **kw):
        """The invoice as a PDF in the modern layout (same access rules as the invoice page)."""
        try:
            invoice_sudo = self._document_check_access('account.move', invoice_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        return self._show_report(model=invoice_sudo, report_type='pdf',
                                 report_ref='rent_management.action_report_rent_invoice', download=download)

    @http.route()
    def portal_my_invoices(self, *args, **kw):
        if not request.env.user._is_internal() and self._rent_is_tenant():
            return request.redirect('/my/rent-invoices')
        return super().portal_my_invoices(*args, **kw)

    @http.route(['/my/invoices/overdue'], type='http', auth='public', methods=['GET'], website=True, sitemap=False)
    def portal_my_overdue_invoices(self, access_token=None, **kw):
        # The route comes with account_payment, which is optional.
        parent = getattr(super(), 'portal_my_overdue_invoices', None)
        if not parent:
            return request.redirect('/my/rent-invoices')
        response = parent(access_token=access_token, **kw)
        if (getattr(response, 'template', None) and not request.env.user._is_public()
                and not request.env.user._is_internal() and self._rent_is_tenant()):
            invoices = request.env['account.move'].search(
                self._get_overdue_invoices_domain(), order='invoice_date_due asc, id asc')
            qcontext = response.qcontext
            today = fields.Date.context_today(request.env.user)
            for key, value in self._rent_shell_values(rent_active='invoices').items():
                qcontext.setdefault(key, value)
            residual = sum(invoices.mapped('amount_residual'))
            qcontext.update({
                # The standard page charges the invoices' full totals, even when they are partly paid:
                # tenants pay what they still owe, as shown on their page.
                'amount': residual,
                'overdue_invoices': invoices,
                'overdue_residual': residual,
                'overdue_oldest_days': (today - invoices[0].invoice_date_due).days if invoices else 0,
                'overdue_bank': (invoices.sudo().partner_bank_id
                                 or invoices.sudo().company_id.partner_id.bank_ids)[:1],
                'rent_can_pay_online': bool(qcontext.get('payment_methods_sudo') or qcontext.get('tokens_sudo')),
            })
            response.template = 'rent_management.portal_tenant_overdue'
        return response

    @http.route()
    def portal_my_invoice_detail(self, invoice_id, access_token=None, report_type=None, download=False, **kw):
        response = super().portal_my_invoice_detail(
            invoice_id, access_token=access_token, report_type=report_type, download=download, **kw)
        # Same page values as the standard invoice page (payment providers, amounts, installments...),
        # rendered with the tenant design when a logged-in tenant looks at their own invoice.
        if getattr(response, 'template', None) != 'account.portal_invoice_page':
            return response
        invoice = response.qcontext.get('invoice')
        partner = request.env.user.partner_id.commercial_partner_id
        if (invoice and not request.env.user._is_public() and self._rent_is_tenant()
                and invoice.partner_id.commercial_partner_id == partner):
            for key, value in self._rent_shell_values(rent_active='invoices').items():
                response.qcontext.setdefault(key, value)
            response.qcontext['invoice_payments'] = (invoice.sudo().invoice_payments_widget or {}).get('content', [])
            # Online payment (Pay now, payment form) comes with account_payment, which is optional.
            response.qcontext['rent_online_payment'] = hasattr(invoice, '_has_to_be_paid')
            response.template = 'rent_management.portal_tenant_invoice'
        return response

    # ------------------------------------------------------------
    # Account details and addresses
    # ------------------------------------------------------------

    def _rent_tenant_page(self, response, template, rent_active, **values):
        """Render a standard portal page with the tenant design, keeping its own values."""
        if (getattr(response, 'template', None) and not request.env.user._is_internal()
                and self._rent_is_tenant()):
            for key, value in self._rent_shell_values(rent_active=rent_active, **values).items():
                response.qcontext.setdefault(key, value)
            response.template = template
        return response

    @http.route()
    def account(self, **kwargs):
        return self._rent_tenant_page(
            super().account(**kwargs), 'rent_management.portal_tenant_account', 'account',
            rent_profile=request.env.user.partner_id._rent_portal_profile())

    @http.route()
    def my_addresses(self, **query_params):
        return self._rent_tenant_page(
            super().my_addresses(**query_params), 'rent_management.portal_tenant_addresses', 'addresses')

    @http.route()
    def portal_address(self, partner_id=None, address_type='billing', use_delivery_as_billing=False,
                       **query_params):
        return self._rent_tenant_page(
            super().portal_address(partner_id=partner_id, address_type=address_type,
                                   use_delivery_as_billing=use_delivery_as_billing, **query_params),
            'rent_management.portal_tenant_address_form', 'addresses')

    # ------------------------------------------------------------
    # Sign-in and security
    # ------------------------------------------------------------

    def _rent_security_values(self):
        """Security overview of the logged-in user; 2FA and passkeys are optional modules."""
        user = request.env.user
        has_totp = 'totp_enabled' in user._fields
        has_passkeys = 'auth_passkey_key_ids' in user._fields
        totp_on = has_totp and user.totp_enabled
        passkeys = user.auth_passkey_key_ids if has_passkeys else None
        checks = [True] + ([totp_on] if has_totp else []) + ([bool(passkeys)] if has_passkeys else [])
        score = sum(checks)
        level = 'strong' if score == len(checks) and score > 1 else 'good' if score > 1 else 'basic'
        return {
            'user': user,
            'has_totp': has_totp,
            'totp_on': totp_on,
            'trusted_devices': user.totp_trusted_device_ids if has_totp else None,
            'has_passkeys': has_passkeys,
            'passkeys': passkeys,
            'level': level,
            'pct': round(100 * score / len(checks)),
        }

    @http.route()
    def security(self, **post):
        return self._rent_tenant_page(
            super().security(**post), 'rent_management.portal_tenant_security', 'security',
            rent_security=self._rent_security_values())

    @http.route()
    def deactivate_account(self, validation, password, **post):
        return self._rent_tenant_page(
            super().deactivate_account(validation, password, **post), 'rent_management.portal_tenant_security',
            'security', rent_security=self._rent_security_values())

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
        values = self._rent_shell_values(rent_active='maintenance')
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
            self._rent_shell_values(maintenance_request=request_sudo, page_name='rent_maintenance',
                                    rent_active='maintenance'),
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
            priority = post.get('priority') if post.get('priority') in dict(Request._fields['priority'].selection) else '1'
            if not error:
                # Tenant, unit and lease come from the tenant's own lease, not from the form.
                maintenance = Request.sudo().create({
                    'lease_id': lease.id,
                    'unit_id': lease.unit_id.id,
                    'tenant_id': lease.tenant_id.id,
                    'category': category,
                    'priority': priority,
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
        values = self._rent_shell_values(rent_active='report')
        values.update({
            'running_leases': leases,
            'categories': Request._fields['category']._description_selection(request.env),
            'priorities': Request._fields['priority']._description_selection(request.env),
            'recent_requests': Request.search(self._rent_maintenance_domain(), limit=5).sudo(),
            'page_name': 'rent_maintenance_new',
            'error': error,
            'post': post,
        })
        return request.render('rent_management.portal_maintenance_new', values)
