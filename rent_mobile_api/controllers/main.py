"""JSON API of the Rent Management mobile app.

Every endpoint lives under /rent/api/v1 and, except login, authenticates with a Bearer API key of
scope "rent_mobile" (issued by the login endpoint). Requests run as the key's user, so the access
rights and record rules of Rent Management apply as in the web client:

* staff (administrator, accountant, property manager) use their own environment;
* tenants (portal users) read their own records with sudo, always restricted to their partner,
  exactly like the tenant portal controllers do.
"""
import base64
import datetime
import functools
import json
import logging
import re

from odoo import Command, fields, http
from odoo.addons.base.models.res_users import INDEX_SIZE, KEY_CRYPT_CONTEXT
from odoo.exceptions import AccessDenied, AccessError, MissingError, UserError, ValidationError
from odoo.fields import Domain
from odoo.http import request
from odoo.tools import html2plaintext, plaintext2html

_logger = logging.getLogger(__name__)

API = '/rent/api/v1'
SCOPE = 'rent_mobile'
TOKEN_DAYS = 90
MAX_PHOTOS = 5
MAX_PHOTO_SIZE = 10 * 1024 * 1024
DEFAULT_LIMIT = 40
MAX_LIMIT = 200
RUNNING = ('active', 'expiring')

ROLE_GROUPS = (
    ('admin', 'rent_management.group_rent_admin'),
    ('accountant', 'rent_management.group_rent_accountant'),
    ('manager', 'rent_management.group_rent_user'),
)
STAFF = ('admin', 'accountant', 'manager')
BILLING = ('admin', 'accountant')


class ApiError(Exception):
    def __init__(self, message, status=400, code='error'):
        super().__init__(message)
        self.status = status
        self.code = code


# ----------------------------------------------------------------------------
# Generic helpers
# ----------------------------------------------------------------------------

def _json_default(value):
    if isinstance(value, datetime.datetime):
        return fields.Datetime.to_string(value)
    if isinstance(value, datetime.date):
        return fields.Date.to_string(value)
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _response(data, status=200):
    return request.make_response(
        json.dumps(data, default=_json_default),
        headers=[('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store')],
        status=status,
    )


def _body():
    data = request.httprequest.get_data(cache=True)
    if not data:
        return {}
    try:
        body = json.loads(data)
    except ValueError:
        raise ApiError(request.env._("The request body is not valid JSON."))
    if not isinstance(body, dict):
        raise ApiError(request.env._("The request body must be a JSON object."))
    return body


def api_route(routes, methods=('GET',), auth='bearer'):
    """Route returning JSON, with errors mapped to HTTP statuses and changes rolled back on error."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                with request.env.cr.savepoint():
                    result = func(self, *args, **kwargs)
            except ApiError as error:
                return _response({'error': error.code, 'message': str(error)}, error.status)
            except AccessDenied as error:
                return _response({'error': 'access_denied', 'message': str(error.args[0] if error.args else '')
                                  or request.env._("Wrong login or password.")}, 401)
            except AccessError as error:
                return _response({'error': 'forbidden', 'message': error.args[0]}, 403)
            except MissingError as error:
                return _response({'error': 'not_found', 'message': error.args[0]}, 404)
            except (UserError, ValidationError) as error:
                return _response({'error': 'user_error', 'message': error.args[0]}, 400)
            if isinstance(result, http.Response) or hasattr(result, 'status_code'):
                return result
            return _response(result)
        routing = {'type': 'http', 'methods': list(methods), 'csrf': False, 'cors': '*', 'save_session': False}
        if auth == 'bearer':
            routing.update(auth='bearer', bearer_scope=SCOPE)
        else:
            routing.update(auth='public')
        return http.route(routes, **routing)(wrapper)
    return decorator


def _m2o(record):
    return {'id': record.id, 'name': record.display_name} if record else None


def _label(record, field_name):
    value = record[field_name]
    if not value:
        return ''
    return dict(record._fields[field_name]._description_selection(record.env)).get(value, value)


def _selection(model, field_name):
    field = request.env[model]._fields[field_name]
    return [{'value': value, 'label': label} for value, label in field._description_selection(request.env)]


def _text(html):
    return html2plaintext(html) if html else ''


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value, name):
    try:
        return float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        raise ApiError(request.env._("%s must be a number.", name))


def _image_url(record, field_name):
    if not record[field_name]:
        return None
    unique = (record.write_date or datetime.datetime.now()).strftime('%Y%m%d%H%M%S')
    return f"{API}/image/{record._name}/{record.id}/{field_name}?unique={unique}"


def _decode_image(data, name="photo"):
    """Base64 image from the app (optionally a data: URL) to raw bytes, size and type checked."""
    if not data:
        return None
    if isinstance(data, str) and data.startswith('data:'):
        data = data.split(',', 1)[-1]
    try:
        raw = base64.b64decode(data, validate=False)
    except (ValueError, TypeError):
        raise ApiError(request.env._("The %s is not a valid image.", name))
    if len(raw) > MAX_PHOTO_SIZE:
        raise ApiError(request.env._("The %s must be 10 MB at most.", name))
    if not (raw[:3] == b'\xff\xd8\xff' or raw[:8] == b'\x89PNG\r\n\x1a\n' or raw[8:12] == b'WEBP'
            or raw[4:12] in (b'ftypheic', b'ftypmif1', b'ftypheix')):
        raise ApiError(request.env._("The %s must be a JPEG, PNG, WEBP or HEIC image.", name))
    return raw


def _role(user=None):
    user = user or request.env.user
    for role, xmlid in ROLE_GROUPS:
        if user.has_group(xmlid):
            return role
    if user._is_portal():
        return 'tenant'
    return None


def _require(*roles):
    role = _role()
    if role not in roles:
        raise ApiError(request.env._("You are not allowed to do this from the app."), 403, 'forbidden')
    return role


def _tenant_partner():
    return request.env.user.partner_id.commercial_partner_id


def _paging(kw):
    limit = min(max(_int(kw.get('limit'), DEFAULT_LIMIT), 1), MAX_LIMIT)
    offset = max(_int(kw.get('offset'), 0), 0)
    return limit, offset


def _search(model, domain, kw, serializer, order=None):
    limit, offset = _paging(kw)
    Model = model
    total = Model.search_count(domain)
    records = Model.search(domain, limit=limit, offset=offset, order=order)
    return {'items': [serializer(record) for record in records], 'total': total, 'limit': limit, 'offset': offset}


def _search_domain(text, fields_list):
    text = (text or '').strip()
    if not text:
        return Domain.TRUE
    return Domain.OR([Domain(name, 'ilike', text) for name in fields_list])


def _tenant_domains(partner):
    return {
        'rent.lease': Domain('tenant_id', 'child_of', partner.id) & Domain('state', '!=', 'draft'),
        'rent.maintenance.request': Domain('tenant_id', 'child_of', partner.id),
        'rent.electricity.reading': Domain('tenant_id', 'child_of', partner.id)
        & Domain('state', 'in', ('confirmed', 'invoiced')),
        'account.move': Domain('partner_id', 'child_of', partner.id) & Domain('rent_lease_id', '!=', False)
        & Domain('state', '=', 'posted') & Domain('move_type', 'in', ('out_invoice', 'out_refund')),
    }


def _model(model):
    """Recordset to read `model` with: the user's own rights for staff, sudo restricted for tenants."""
    role = _role()
    if role in STAFF:
        return request.env[model], Domain.TRUE, role
    if role == 'tenant':
        domain = _tenant_domains(_tenant_partner()).get(model)
        if domain is None:
            raise ApiError(request.env._("Tenants cannot access this information."), 403, 'forbidden')
        return request.env[model].sudo(), domain, role
    raise ApiError(request.env._("Your user has no access to Rent Management."), 403, 'forbidden')


def _get(model, record_id, operation='read'):
    Model, domain, role = _model(model)
    if role == 'tenant':
        if operation != 'read':
            raise ApiError(request.env._("Tenants cannot change this record."), 403, 'forbidden')
        record = Model.search(domain & Domain('id', '=', record_id), limit=1)
        if not record:
            raise MissingError(request.env._("Record not found."))
        return record
    record = Model.browse(record_id).exists()
    if not record:
        raise MissingError(request.env._("Record not found."))
    record.check_access(operation)
    return record


def _vals(body, spec, model):
    """Values to write from the app payload. spec: field name -> kind (char, int, float, bool,
    date, m2o, m2m, html, image, selection)."""
    vals = {}
    Model = request.env[model]
    for name, kind in spec.items():
        if name not in body:
            continue
        value = body[name]
        if kind == 'm2o':
            vals[name] = _int(value) or False
        elif kind == 'm2m':
            vals[name] = [Command.set([_int(v) for v in (value or []) if _int(v)])]
        elif kind == 'float':
            vals[name] = _float(value or 0, Model._fields[name].string)
        elif kind == 'int':
            vals[name] = _int(value, 0)
        elif kind == 'bool':
            vals[name] = bool(value)
        elif kind == 'date':
            vals[name] = fields.Date.to_date(value) if value else False
        elif kind == 'html':
            vals[name] = plaintext2html(value) if value else False
        elif kind == 'image':
            raw = _decode_image(value, Model._fields[name].string) if value else None
            vals[name] = base64.b64encode(raw).decode() if raw else False
        elif kind == 'selection':
            allowed = dict(Model._fields[name]._description_selection(request.env))
            if value and value not in allowed:
                raise ApiError(request.env._("Invalid value for %s.", Model._fields[name].string))
            vals[name] = value or False
        else:
            vals[name] = (value or '').strip() if isinstance(value, str) else (value or False)
    return vals


def _action_result(result):
    """Turn what an Odoo button returns into ids the app can open."""
    if isinstance(result, dict):
        model = result.get('res_model')
        if result.get('res_id'):
            return {'ok': True, 'res_model': model, 'res_ids': [result['res_id']]}
        for leaf in result.get('domain') or []:
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3 and leaf[0] == 'id' and leaf[1] == 'in':
                return {'ok': True, 'res_model': model, 'res_ids': list(leaf[2])}
    return {'ok': True}


def _pdf(report_ref, records, filename):
    pdf, _report_type = request.env['ir.actions.report'].sudo()._render_qweb_pdf(report_ref, records.ids)
    safe = re.sub(r'[^\w\- .]', '_', filename)
    return request.make_response(pdf, headers=[
        ('Content-Type', 'application/pdf'),
        ('Content-Length', len(pdf)),
        ('Content-Disposition', f'attachment; filename="{safe}.pdf"'),
    ])


# ----------------------------------------------------------------------------
# Serializers
# ----------------------------------------------------------------------------

def _money(record, amount):
    return {'amount': amount, 'currency': record.currency_id.name, 'symbol': record.currency_id.symbol,
            'position': record.currency_id.position}


def ser_property(prop, detail=False):
    data = {
        'id': prop.id, 'name': prop.name, 'code': prop.code,
        'property_type': prop.property_type, 'property_type_label': _label(prop, 'property_type'),
        'city': prop.city or '', 'manager': _m2o(prop.manager_id), 'owner': _m2o(prop.owner_id),
        'unit_count': prop.unit_count, 'occupied_count': prop.occupied_count, 'vacant_count': prop.vacant_count,
        'occupancy_rate': round(prop.occupancy_rate, 1), 'image_url': _image_url(prop, 'image'),
        'currency': prop.currency_id.name,
    }
    if detail:
        data.update({
            'street': prop.street or '', 'street2': prop.street2 or '', 'zip': prop.zip or '',
            'state': _m2o(prop.state_id), 'country': _m2o(prop.country_id),
            'amenities': [_m2o(a) for a in prop.amenity_ids], 'notes': _text(prop.notes),
            'units': [ser_unit(u) for u in prop.unit_ids],
        })
    return data


def ser_unit(unit, detail=False):
    data = {
        'id': unit.id, 'name': unit.name, 'display_name': unit.display_name,
        'property': _m2o(unit.property_id), 'floor': unit.floor or '',
        'unit_type': unit.unit_type, 'unit_type_label': _label(unit, 'unit_type'),
        'state': unit.state, 'state_label': _label(unit, 'state'),
        'base_rent': unit.base_rent, 'bedrooms': unit.bedrooms, 'area_sqft': unit.area_sqft,
        'current_tenant': _m2o(unit.current_tenant_id), 'image_url': _image_url(unit, 'image'),
        'currency': unit.currency_id.name,
    }
    if detail:
        lease_model = unit.env['rent.lease']
        data.update({
            'furnishing': unit.furnishing, 'furnishing_label': _label(unit, 'furnishing'),
            'deposit_amount': unit.deposit_amount, 'maintenance_charge': unit.maintenance_charge,
            'meter_number': unit.meter_number or '', 'under_maintenance': unit.under_maintenance,
            'current_lease': _m2o(unit.current_lease_id),
            'meter_qr_url': unit.meter_qr_url or '',
            'leases': [ser_lease(lease) for lease in lease_model.search([('unit_id', '=', unit.id)], limit=20)],
            'maintenance': [ser_maintenance(r) for r in unit.env['rent.maintenance.request'].search(
                [('unit_id', '=', unit.id)], limit=10)],
        })
    return data


def ser_tenant(partner, detail=False):
    data = {
        'id': partner.id, 'name': partner.name, 'email': partner.email or '', 'phone': partner.phone or '',
        'city': partner.city or '', 'image_url': _image_url(partner, 'image_128'),
        'kyc_verified': partner.kyc_verified, 'lease_count': partner.lease_count,
        'rent_total_due': partner.rent_total_due,
        'has_app_access': bool(partner.sudo().user_ids.filtered(lambda u: u.active)),
    }
    if detail:
        data.update({
            'street': partner.street or '', 'street2': partner.street2 or '', 'zip': partner.zip or '',
            'state': _m2o(partner.state_id), 'country': _m2o(partner.country_id),
            'kyc_id_type': partner.kyc_id_type or '', 'kyc_id_type_label': _label(partner, 'kyc_id_type'),
            'kyc_id_number': partner.kyc_id_number or '',
            'emergency_contact_name': partner.emergency_contact_name or '',
            'emergency_contact_phone': partner.emergency_contact_phone or '',
            'leases': [ser_lease(lease) for lease in partner.lease_ids],
        })
    return data


def _lease_actions(lease, role):
    if role == 'tenant':
        return ['agreement_pdf'] + (['moveout_pdf'] if lease.state == 'terminated' else [])
    billing = role in BILLING
    state = lease.state
    actions = ['agreement_pdf']
    if state == 'draft':
        actions += ['edit', 'confirm', 'cancel', 'delete']
    elif state == 'confirmed':
        actions += ['edit', 'activate', 'cancel']
    elif state in RUNNING:
        actions += ['edit', 'renew', 'moveout']
        if billing:
            actions.append('generate_invoice')
    elif state == 'expired':
        actions += ['renew', 'moveout']
    elif state == 'cancelled':
        actions += ['draft', 'delete']
    elif state == 'terminated':
        actions.append('moveout_pdf')
    if state in ('confirmed',) + RUNNING:
        actions.append('request_signature')
        if not lease.signed:
            actions.append('mark_signed')
    if billing and state in ('confirmed',) + RUNNING and lease.deposit_amount and \
            (not lease.deposit_invoice_id or lease.deposit_invoice_id.state == 'cancel'):
        actions.append('deposit_invoice')
    return actions


def ser_lease(lease, detail=False, role=None):
    data = {
        'id': lease.id, 'name': lease.name, 'state': lease.state, 'state_label': _label(lease, 'state'),
        'tenant': _m2o(lease.tenant_id), 'unit': _m2o(lease.unit_id), 'property': _m2o(lease.property_id),
        'start_date': lease.start_date, 'end_date': lease.end_date, 'rent_amount': lease.rent_amount,
        'amount_due': lease.amount_due, 'deposit_status': lease.deposit_status or '',
        'deposit_status_label': _label(lease, 'deposit_status'), 'signed': lease.signed,
        'currency': lease.currency_id.name,
    }
    if detail:
        sudo = lease.sudo()
        portal = sudo._rent_portal_lease_values()
        data.update({
            'manager': _m2o(sudo.manager_id), 'duration_months': lease.duration_months,
            'notice_period_days': lease.notice_period_days, 'renewed_from': _m2o(lease.renewed_from_id),
            'maintenance_charge': lease.maintenance_charge, 'billing_day': lease.billing_day,
            'billing_frequency': lease.billing_frequency, 'billing_frequency_label': _label(lease, 'billing_frequency'),
            'next_invoice_date': lease.next_invoice_date, 'late_fee_type': lease.late_fee_type or '',
            'late_fee_value': lease.late_fee_value, 'grace_days': lease.grace_days,
            'escalation_percent': lease.escalation_percent, 'escalation_every_months': lease.escalation_every_months,
            'next_escalation_date': lease.next_escalation_date,
            'electricity_billing': lease.electricity_billing,
            'electricity_billing_label': _label(lease, 'electricity_billing'),
            'electricity_rate': lease.electricity_rate, 'electricity_fixed_amount': lease.electricity_fixed_amount,
            'electricity_opening_reading': lease.electricity_opening_reading,
            'deposit_amount': lease.deposit_amount, 'deposit_refunded_amount': lease.deposit_refunded_amount,
            'deposit_invoice': _m2o(sudo.deposit_invoice_id), 'deposit_refund': _m2o(sudo.deposit_refund_id),
            'moveout_date': lease.moveout_date, 'moveout_damage_charges': lease.moveout_damage_charges,
            'moveout_unpaid_dues': lease.moveout_unpaid_dues,
            'moveout_electricity_charges': lease.moveout_electricity_charges,
            'moveout_deduction_note': lease.moveout_deduction_note or '',
            'notes': _text(lease.notes),
            'progress': portal['progress'], 'days_left': portal['days_left'],
            'monthly_total': portal['monthly_total'], 'timeline': portal['timeline'],
            'invoices': [ser_invoice(m) for m in portal['lease_invoices'][:20]],
            'maintenance': [ser_maintenance(r) for r in sudo.maintenance_request_ids[:10]],
            'readings': [ser_reading(r) for r in sudo.electricity_reading_ids.filtered(
                lambda r: role != 'tenant' or r.state in ('confirmed', 'invoiced'))[:12]],
            'actions': _lease_actions(lease, role),
        })
    return data


def ser_maintenance(req, detail=False, role=None):
    data = {
        'id': req.id, 'name': req.name, 'unit': _m2o(req.unit_id), 'property': _m2o(req.property_id),
        'tenant': _m2o(req.tenant_id), 'category': req.category, 'category_label': _label(req, 'category'),
        'priority': req.priority or '0', 'priority_label': _label(req, 'priority'),
        'state': req.state, 'state_label': _label(req, 'state'), 'assigned_to': _m2o(req.sudo().assigned_to),
        'create_date': req.create_date, 'cost': req.cost, 'currency': req.currency_id.name,
        'summary': _text(req.description)[:140],
    }
    if detail:
        sudo = req.sudo()
        actions = []
        if role in STAFF:
            actions = {
                'new': ['edit', 'start', 'done', 'cancel'],
                'in_progress': ['edit', 'done', 'cancel'],
                'done': [],
                'cancelled': ['reset'],
            }[req.state]
        data.update({
            'description': _text(req.description), 'lease': _m2o(req.lease_id),
            'vendor': _m2o(sudo.vendor_id), 'charge_to': req.charge_to, 'charge_to_label': _label(req, 'charge_to'),
            'invoice': _m2o(sudo.invoice_id),
            'photos': [f"{API}/attachment/{att.id}" for att in sudo.image_ids],
            'actions': actions,
        })
    return data


def ser_reading(reading, detail=False, role=None):
    data = {
        'id': reading.id, 'name': reading.name, 'unit': _m2o(reading.unit_id), 'property': _m2o(reading.property_id),
        'tenant': _m2o(reading.tenant_id), 'lease': _m2o(reading.lease_id),
        'period_start': reading.period_start, 'period_end': reading.period_end, 'reading_date': reading.reading_date,
        'previous_reading': reading.previous_reading, 'current_reading': reading.current_reading,
        'consumption': reading.consumption, 'rate': reading.rate, 'fixed_charge': reading.fixed_charge,
        'amount': reading.amount, 'state': reading.state, 'state_label': _label(reading, 'state'),
        'meter_number': reading.meter_number or '', 'currency': reading.currency_id.name,
    }
    if detail:
        actions = []
        if role in STAFF:
            actions = {
                'draft': ['edit', 'confirm', 'cancel'],
                'confirmed': ['reset_draft', 'cancel'] + (['invoice'] if role in BILLING else []),
                'invoiced': [],
                'cancelled': ['reset_draft'],
            }[reading.state]
        data.update({
            'notes': reading.notes or '', 'invoice': _m2o(reading.sudo().invoice_id),
            'photo_url': _image_url(reading, 'meter_photo'), 'actions': actions,
        })
    return data


def _invoice_status(move):
    today = fields.Date.context_today(move)
    if move.move_type == 'out_refund':
        return 'refund'
    if move.state != 'posted':
        return move.state
    if move.currency_id.is_zero(move.amount_residual):
        return 'paid'
    if move.invoice_date_due and move.invoice_date_due < today:
        return 'overdue'
    if move.payment_state == 'partial':
        return 'partial'
    return 'due'


def ser_invoice(move, detail=False, role=None):
    data = {
        'id': move.id, 'name': move.name, 'partner': _m2o(move.partner_id), 'lease': _m2o(move.rent_lease_id),
        'property': _m2o(move.rent_property_id), 'move_type': move.move_type,
        'invoice_type': move.rent_invoice_type or '', 'invoice_type_label': _label(move, 'rent_invoice_type'),
        'invoice_date': move.invoice_date, 'invoice_date_due': move.invoice_date_due,
        'amount_total': move.amount_total, 'amount_residual': move.amount_residual,
        'payment_state': move.payment_state, 'state': move.state, 'status': _invoice_status(move),
        'currency': move.currency_id.name,
    }
    if detail:
        sudo = move.sudo()
        data.update({
            'lines': [{
                'name': line.name or '', 'quantity': line.quantity, 'price_unit': line.price_unit,
                'subtotal': line.price_subtotal, 'display_type': line.display_type,
            } for line in sudo.invoice_line_ids.filtered(
                lambda l: l.display_type in ('product', 'line_section', 'line_note'))],
            'amount_untaxed': move.amount_untaxed, 'amount_tax': move.amount_tax,
            'payments': [{
                'date': p.get('date'), 'amount': p.get('amount'), 'journal': p.get('journal_name'),
                'ref': p.get('ref') or p.get('name') or '',
            } for p in (sudo.invoice_payments_widget or {}).get('content', [])],
            'pay_url': f"{sudo.get_base_url()}{sudo.get_portal_url()}"
            if move.move_type == 'out_invoice' and data['status'] in ('due', 'overdue', 'partial') else None,
            'can_register_payment': role in BILLING and move.move_type == 'out_invoice'
            and move.state == 'posted' and data['status'] in ('due', 'overdue', 'partial'),
        })
    return data


def ser_user(user):
    partner = user.partner_id
    role = _role(user)
    return {
        'id': user.id, 'name': user.name, 'login': user.login, 'email': partner.email or '',
        'phone': partner.phone or '', 'role': role, 'partner_id': partner.id,
        'image_url': _image_url(partner, 'image_128'),
        'company': {'id': user.company_id.id, 'name': user.company_id.name,
                    'currency': user.company_id.currency_id.name,
                    'symbol': user.company_id.currency_id.symbol,
                    'position': user.company_id.currency_id.position,
                    'color': user.company_id.primary_color or '#714B67'},
        'lang': user.lang, 'tz': user.tz or 'UTC',
    }


# ----------------------------------------------------------------------------
# Writable fields per model (staff)
# ----------------------------------------------------------------------------

PROPERTY_FIELDS = {
    'name': 'char', 'property_type': 'selection', 'owner_id': 'm2o', 'manager_id': 'm2o', 'street': 'char',
    'street2': 'char', 'city': 'char', 'state_id': 'm2o', 'zip': 'char', 'country_id': 'm2o',
    'amenity_ids': 'm2m', 'notes': 'html', 'image': 'image',
}
UNIT_FIELDS = {
    'name': 'char', 'property_id': 'm2o', 'floor': 'char', 'unit_type': 'selection', 'area_sqft': 'float',
    'bedrooms': 'int', 'furnishing': 'selection', 'base_rent': 'float', 'deposit_amount': 'float',
    'maintenance_charge': 'float', 'meter_number': 'char', 'under_maintenance': 'bool', 'image': 'image',
}
TENANT_FIELDS = {
    'name': 'char', 'email': 'char', 'phone': 'char', 'street': 'char', 'street2': 'char', 'city': 'char',
    'zip': 'char', 'state_id': 'm2o', 'country_id': 'm2o', 'kyc_id_type': 'selection', 'kyc_id_number': 'char',
    'kyc_verified': 'bool', 'emergency_contact_name': 'char', 'emergency_contact_phone': 'char',
    'image_1920': 'image',
}
LEASE_FIELDS = {
    'tenant_id': 'm2o', 'unit_id': 'm2o', 'start_date': 'date', 'end_date': 'date', 'notice_period_days': 'int',
    'rent_amount': 'float', 'maintenance_charge': 'float', 'billing_day': 'int', 'billing_frequency': 'selection',
    'late_fee_type': 'selection', 'late_fee_value': 'float', 'grace_days': 'int', 'escalation_percent': 'float',
    'escalation_every_months': 'int', 'electricity_billing': 'selection', 'electricity_rate': 'float',
    'electricity_fixed_amount': 'float', 'electricity_opening_reading': 'float', 'deposit_amount': 'float',
    'notes': 'html',
}
MAINTENANCE_FIELDS = {
    'unit_id': 'm2o', 'lease_id': 'm2o', 'tenant_id': 'm2o', 'category': 'selection', 'priority': 'selection',
    'description': 'html', 'assigned_to': 'm2o', 'vendor_id': 'm2o', 'cost': 'float', 'charge_to': 'selection',
}
READING_FIELDS = {
    'lease_id': 'm2o', 'period_start': 'date', 'period_end': 'date', 'reading_date': 'date',
    'previous_reading': 'float', 'current_reading': 'float', 'rate': 'float', 'fixed_charge': 'float',
    'notes': 'char', 'meter_photo': 'image',
}
PROFILE_FIELDS = {
    'name': 'char', 'email': 'char', 'phone': 'char', 'street': 'char', 'street2': 'char', 'city': 'char',
    'zip': 'char', 'state_id': 'm2o', 'country_id': 'm2o', 'image_1920': 'image',
}
SETTINGS_FIELDS = {
    'rent_invoice_advance_days': 'int', 'rent_reminder_days_before': 'int', 'rent_send_overdue_notice': 'bool',
    'rent_electricity_rate': 'float', 'rent_expiry_notice_days': 'int',
}

LEASE_ACTIONS = {
    'confirm': 'action_confirm', 'activate': 'action_activate', 'cancel': 'action_cancel', 'draft': 'action_draft',
    'renew': 'action_renew', 'request_signature': 'action_request_signature', 'mark_signed': 'action_mark_signed',
    'generate_invoice': 'action_generate_invoice', 'deposit_invoice': 'action_create_deposit_invoice',
}
MAINTENANCE_ACTIONS = {'start': 'action_start', 'done': 'action_done', 'cancel': 'action_cancel', 'reset': 'action_reset'}
READING_ACTIONS = {'confirm': 'action_confirm', 'reset_draft': 'action_reset_draft', 'cancel': 'action_cancel',
                   'invoice': 'action_create_invoice'}
UNIT_ACTIONS = {'regenerate_meter_qr': 'action_regenerate_meter_qr'}
BILLING_ACTIONS = {'generate_invoice', 'deposit_invoice', 'invoice'}

MESSAGE_MODELS = ('rent.property', 'rent.unit', 'rent.lease', 'rent.maintenance.request',
                  'rent.electricity.reading', 'account.move', 'res.partner')
IMAGE_FIELDS = {
    'rent.property': ('image',), 'rent.unit': ('image',), 'res.partner': ('image_128', 'image_1920'),
    'rent.electricity.reading': ('meter_photo',),
}


class RentMobileApi(http.Controller):

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    @api_route(f'{API}/auth/login', methods=('POST',), auth='public')
    def login(self, **kw):
        body = _body()
        login = (body.get('login') or '').strip()
        password = body.get('password') or ''
        if not login or not password:
            raise ApiError(request.env._("Enter your login and password."), 400)
        Users = request.env['res.users'].sudo()
        auth_info = Users.authenticate(
            {'type': 'password', 'login': login, 'password': password}, {'interactive': True})
        user = Users.browse(auth_info['uid'])
        if auth_info.get('mfa') != 'skip' and user._mfa_type() == 'totp':
            code = re.sub(r'\s', '', str(body.get('totp') or ''))
            if not code:
                raise ApiError(request.env._("Enter the code of your authenticator app."), 401, 'totp_required')
            try:
                user.with_user(user)._check_credentials({'type': 'totp', 'token': int(code)}, {'interactive': True})
            except (AccessDenied, ValueError):
                raise ApiError(request.env._("Invalid authentication code."), 401, 'totp_invalid')
        if not _role(user):
            raise ApiError(request.env._("Your user has no access to Rent Management."), 403, 'forbidden')
        device = (body.get('device') or 'Mobile app')[:60]
        expiration = datetime.datetime.now() + datetime.timedelta(days=TOKEN_DAYS)
        token = request.env['res.users.apikeys'].with_user(user).sudo()._generate(
            SCOPE, f"Rent Mobile: {device}", expiration)
        return {'token': token, 'expires_at': expiration, 'user': ser_user(user.with_user(user))}

    @api_route(f'{API}/auth/logout', methods=('POST',))
    def logout(self, **kw):
        header = request.httprequest.headers.get('Authorization') or ''
        token = header.split(' ', 1)[-1].strip()
        Keys = request.env['res.users.apikeys'].sudo()
        keys = Keys.search([('user_id', '=', request.env.uid), ('scope', '=', SCOPE)])
        if token:
            request.env.cr.execute(
                "SELECT id, key FROM res_users_apikeys WHERE user_id = %s AND scope = %s AND index = %s",
                [request.env.uid, SCOPE, token[:INDEX_SIZE]])
            ids = [key_id for key_id, hashed in request.env.cr.fetchall() if KEY_CRYPT_CONTEXT.verify(token, hashed)]
            keys = Keys.browse(ids)
        keys.unlink()
        return {'ok': True}

    def me(self, **kw):
        return self._me()

    def _me(self):
        user = request.env.user
        data = ser_user(user)
        partner = user.partner_id.sudo()
        data.update({
            'street': partner.street or '', 'street2': partner.street2 or '', 'city': partner.city or '',
            'zip': partner.zip or '', 'state': _m2o(partner.state_id), 'country': _m2o(partner.country_id),
        })
        if data['role'] == 'tenant':
            data['profile'] = user.partner_id._rent_portal_profile()
        return data

    def me_update(self, **kw):
        vals = _vals(_body(), PROFILE_FIELDS, 'res.partner')
        if 'name' in vals and not vals['name']:
            raise ApiError(request.env._("Your name cannot be empty."))
        # Only the user's own contact: the portal user cannot write partners otherwise.
        request.env.user.partner_id.sudo().write(vals)
        return self._me()

    @api_route(f'{API}/me/password', methods=('POST',))
    def change_password(self, **kw):
        body = _body()
        new = body.get('new_password') or ''
        if len(new) < 8:
            raise ApiError(request.env._("The new password must have at least 8 characters."))
        request.env['res.users'].change_password(body.get('old_password') or '', new)
        return {'ok': True}

    # ------------------------------------------------------------------
    # Reference data
    # ------------------------------------------------------------------

    @api_route(f'{API}/meta', methods=('GET',))
    def meta(self, **kw):
        _model('rent.lease')
        return {
            'selections': {
                'property_type': _selection('rent.property', 'property_type'),
                'unit_type': _selection('rent.unit', 'unit_type'),
                'furnishing': _selection('rent.unit', 'furnishing'),
                'unit_state': _selection('rent.unit', 'state'),
                'lease_state': _selection('rent.lease', 'state'),
                'billing_frequency': _selection('rent.lease', 'billing_frequency'),
                'late_fee_type': _selection('rent.lease', 'late_fee_type'),
                'electricity_billing': _selection('rent.lease', 'electricity_billing'),
                'deposit_status': _selection('rent.lease', 'deposit_status'),
                'maintenance_category': _selection('rent.maintenance.request', 'category'),
                'maintenance_priority': _selection('rent.maintenance.request', 'priority'),
                'maintenance_state': _selection('rent.maintenance.request', 'state'),
                'charge_to': _selection('rent.maintenance.request', 'charge_to'),
                'reading_state': _selection('rent.electricity.reading', 'state'),
                'kyc_id_type': _selection('res.partner', 'kyc_id_type'),
                'invoice_type': _selection('account.move', 'rent_invoice_type'),
            },
            'company': ser_user(request.env.user)['company'],
        }

    @api_route(f'{API}/options/<string:kind>', methods=('GET',))
    def options(self, kind, **kw):
        """Choices of the pickers of the app forms (many2one fields)."""
        _require(*STAFF)
        env = request.env
        search = kw.get('search') or ''
        limit = min(_int(kw.get('limit'), 50), MAX_LIMIT)
        configs = {
            'properties': (env['rent.property'], Domain.TRUE),
            'units': (env['rent.unit'], Domain('property_id', '=', _int(kw.get('property_id')))
                      if kw.get('property_id') else Domain.TRUE),
            'vacant_units': (env['rent.unit'], Domain('state', '=', 'vacant')),
            'tenants': (env['res.partner'], Domain('is_tenant', '=', True)),
            'owners': (env['res.partner'], Domain('is_owner', '=', True)),
            'vendors': (env['res.partner'], Domain('is_company', '=', True) | Domain('supplier_rank', '>', 0)),
            'users': (env['res.users'], Domain('share', '=', False)),
            'amenities': (env['rent.amenity'], Domain.TRUE),
            'countries': (env['res.country'], Domain.TRUE),
            'states': (env['res.country.state'], Domain('country_id', '=', _int(kw.get('country_id')))
                       if kw.get('country_id') else Domain.TRUE),
            'running_leases': (env['rent.lease'], Domain('state', 'in', RUNNING)),
            'metered_leases': (env['rent.lease'], Domain('state', 'in', RUNNING + ('expired', 'terminated'))
                               & Domain('electricity_billing', '=', 'metered')),
            'payment_journals': (env['account.journal'], Domain('type', 'in', ('bank', 'cash'))),
        }
        if kind not in configs:
            raise MissingError(request.env._("Unknown list."))
        if kind == 'payment_journals':
            _require(*BILLING)
        Model, domain = configs[kind]
        domain &= Domain('display_name', 'ilike', search) if search else Domain.TRUE
        records = Model.search(domain, limit=limit)
        items = []
        for record in records:
            item = {'id': record.id, 'name': record.display_name}
            if Model._name == 'rent.unit':
                item.update(base_rent=record.base_rent, deposit_amount=record.deposit_amount,
                            maintenance_charge=record.maintenance_charge, has_meter=bool(record.meter_number),
                            state=record.state)
            elif Model._name == 'rent.lease':
                item.update(electricity_rate=record.electricity_rate, tenant=record.tenant_id.name)
            items.append(item)
        return {'items': items}

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    @api_route(f'{API}/dashboard', methods=('GET',))
    def dashboard(self, **kw):
        role = _role()
        if role in STAFF:
            data = request.env['rent.property'].get_dashboard_data(
                period=kw.get('period') or 'this_month', property_id=_int(kw.get('property_id')) or False)
            for section in data['sections']:
                for kpi in section['kpis']:
                    kpi.pop('action', None)
            for row in data['overdue_tenants']:
                row.pop('action', None)
            data['role'] = role
            return data
        if role == 'tenant':
            return self._tenant_dashboard(_int(kw.get('lease_id')))
        raise ApiError(request.env._("Your user has no access to Rent Management."), 403, 'forbidden')

    def _tenant_dashboard(self, lease_id):
        partner = request.env.user.partner_id
        values = partner._rent_portal_dashboard(lease_id=lease_id)
        values['payments_all'] = request.env['rent.property'].sudo()._dashboard_payments(
            request.env['account.move'].sudo().search(
                _tenant_domains(_tenant_partner())['account.move'] & Domain('move_type', '=', 'out_invoice')))
        lease = values['lease']
        next_payment = values['next_payment']
        if next_payment:
            next_payment = dict(next_payment, invoice=_m2o(next_payment['invoice']) if next_payment['invoice'] else None)
        for alert in values['alerts']:
            if alert.get('url'):
                alert['url'] = f"{lease.get_base_url()}{alert['url']}"
        pay = values['pay_invoice']
        return {
            'role': 'tenant',
            'currency': values['currency'].name,
            'leases': [ser_lease(l) for l in values['leases']],
            'lease': ser_lease(lease) if lease else None,
            'running': values['running'],
            'unit': _m2o(values['unit']), 'property': _m2o(values['property']),
            'manager': {'name': values['manager'].name, 'email': values['manager'].email or '',
                        'phone': values['manager'].phone or ''} if values['manager'] else None,
            'amount_due': values['amount_due'], 'overdue_amount': values['overdue_amount'],
            'pay_invoice': ser_invoice(pay, detail=True, role='tenant') if pay else None,
            'next_payment': next_payment, 'paid_this_year': values['paid_this_year'],
            'invoices': [ser_invoice(m) for m in values['invoices']],
            'payments': values['payments'],
            'readings': [ser_reading(r) for r in values['readings']],
            'requests': [ser_maintenance(r) for r in values['requests']],
            'open_request_count': values['open_request_count'],
            'lease_progress': values['lease_progress'], 'days_left': values['days_left'],
            'months_left': values['months_left'], 'alerts': values['alerts'],
            'status_counts': values['status_counts'], 'paid_pct': values['paid_pct'],
            'trend': self._tenant_trend(values['payments_all']),
        }

    def _tenant_trend(self, payments):
        """Money paid per month over the last 6 months."""
        today = fields.Date.context_today(request.env.user)
        months = [today.replace(day=1) - _relativedelta(months=offset) for offset in range(5, -1, -1)]
        totals = dict.fromkeys(months, 0.0)
        for payment in payments:
            month = payment['date'].replace(day=1)
            if month in totals:
                totals[month] += payment['amount']
        return [{'month': month.strftime('%b'), 'value': totals[month]} for month in months]

    @api_route(f'{API}/activities', methods=('GET',))
    def activities(self, **kw):
        """To-dos assigned to the user on rent records (staff), or the dashboard alerts (tenant)."""
        role = _role()
        if role == 'tenant':
            return {'items': request.env.user.partner_id._rent_portal_dashboard()['alerts'], 'kind': 'alerts'}
        _require(*STAFF)
        activities = request.env['mail.activity'].search([
            ('user_id', '=', request.env.uid),
            ('res_model', 'in', ['rent.lease', 'rent.maintenance.request', 'rent.electricity.reading',
                                 'rent.unit', 'rent.property']),
        ], order='date_deadline', limit=100)
        today = fields.Date.context_today(request.env.user)
        return {'kind': 'activities', 'items': [{
            'id': a.id, 'summary': a.summary or a.activity_type_id.name, 'note': _text(a.note),
            'res_model': a.res_model, 'res_id': a.res_id, 'res_name': a.res_name,
            'date_deadline': a.date_deadline, 'overdue': a.date_deadline < today,
        } for a in activities]}

    @api_route(f'{API}/activities/<int:activity_id>/done', methods=('POST',))
    def activity_done(self, activity_id, **kw):
        _require(*STAFF)
        activity = request.env['mail.activity'].browse(activity_id).exists()
        if not activity or activity.user_id != request.env.user:
            raise MissingError(request.env._("Activity not found."))
        activity.action_feedback(feedback=_body().get('feedback') or False)
        return {'ok': True}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def property_list(self, **kw):
        _require(*STAFF)
        domain = _search_domain(kw.get('search'), ['name', 'code', 'city'])
        return _search(request.env['rent.property'], domain, kw, ser_property)

    def property_get(self, record_id, **kw):
        _require(*STAFF)
        return ser_property(_get('rent.property', record_id), detail=True)

    def property_create(self, **kw):
        _require(*STAFF)
        prop = request.env['rent.property'].create(_vals(_body(), PROPERTY_FIELDS, 'rent.property'))
        return ser_property(prop, detail=True)

    def property_update(self, record_id, **kw):
        _require(*STAFF)
        prop = _get('rent.property', record_id, 'write')
        prop.write(_vals(_body(), PROPERTY_FIELDS, 'rent.property'))
        return ser_property(prop, detail=True)

    def property_archive(self, record_id, **kw):
        _require('admin')
        _get('rent.property', record_id, 'write').action_archive()
        return {'ok': True}

    # ------------------------------------------------------------------
    # Units
    # ------------------------------------------------------------------

    def unit_list(self, **kw):
        _require(*STAFF)
        domain = _search_domain(kw.get('search'), ['name', 'property_id.name', 'current_tenant_id.name'])
        if kw.get('state'):
            domain &= Domain('state', '=', kw['state'])
        if kw.get('property_id'):
            domain &= Domain('property_id', '=', _int(kw['property_id']))
        return _search(request.env['rent.unit'], domain, kw, ser_unit)

    def unit_get(self, record_id, **kw):
        _require(*STAFF)
        return ser_unit(_get('rent.unit', record_id), detail=True)

    def unit_create(self, **kw):
        _require(*STAFF)
        unit = request.env['rent.unit'].create(_vals(_body(), UNIT_FIELDS, 'rent.unit'))
        return ser_unit(unit, detail=True)

    def unit_update(self, record_id, **kw):
        _require(*STAFF)
        unit = _get('rent.unit', record_id, 'write')
        unit.write(_vals(_body(), UNIT_FIELDS, 'rent.unit'))
        return ser_unit(unit, detail=True)

    def unit_archive(self, record_id, **kw):
        _require('admin')
        _get('rent.unit', record_id, 'write').action_archive()
        return {'ok': True}

    @api_route(f'{API}/units/<int:record_id>/action/<string:action>', methods=('POST',))
    def unit_action(self, record_id, action, **kw):
        _require(*STAFF)
        if action not in UNIT_ACTIONS:
            raise MissingError(request.env._("Unknown action."))
        unit = _get('rent.unit', record_id, 'write')
        getattr(unit, UNIT_ACTIONS[action])()
        return ser_unit(unit, detail=True)

    @api_route(f'{API}/units/<int:record_id>/meter-label', methods=('GET',))
    def unit_meter_label(self, record_id, **kw):
        _require(*STAFF)
        unit = _get('rent.unit', record_id)
        return _pdf('rent_management.action_report_meter_qr_label', unit, f'Meter QR - {unit.display_name}')

    # ------------------------------------------------------------------
    # Meter readings by QR code / unit
    # ------------------------------------------------------------------

    def _meter_entry(self, unit):
        entry = unit._get_meter_entry()
        lease = entry['lease']
        result = {
            'unit': ser_unit(unit), 'meter_number': unit.meter_number or '',
            'lease': _m2o(lease), 'tenant': _m2o(lease.tenant_id),
            'unmetered_lease': _m2o(entry.get('unmetered_lease')) if entry.get('unmetered_lease') else None,
        }
        if lease:
            result.update({
                'reading_id': entry['reading'].id or None,
                'period_start': entry['period_start'], 'period_end': entry['period_end'],
                'previous_reading': entry['previous_reading'], 'rate': entry['rate'],
                'lease_rate': lease.electricity_rate,
            })
        return result

    def _unit_from_qr(self, code):
        # The QR label holds the reading URL: accept the URL or the bare token.
        token = (code or '').rstrip('/').rsplit('/', 1)[-1]
        unit = request.env['rent.unit'].search([('meter_qr_token', '=', token)], limit=1) if token else None
        if not unit:
            raise MissingError(request.env._("This QR code is not a meter of your properties."))
        return unit

    @api_route(f'{API}/meter/scan', methods=('POST',))
    def meter_scan(self, **kw):
        _require(*STAFF)
        return self._meter_entry(self._unit_from_qr(_body().get('code')))

    def meter_entry(self, record_id, **kw):
        _require(*STAFF)
        return self._meter_entry(_get('rent.unit', record_id))

    def meter_save(self, record_id, **kw):
        _require(*STAFF)
        unit = _get('rent.unit', record_id)
        body = _body()
        photo = _decode_image(body.get('photo'), request.env._("meter photo"))
        reading = unit._save_meter_reading(
            _float(body.get('current_reading'), request.env._("The reading")),
            _float(body.get('rate'), request.env._("The rate")),
            apply_rate_to_lease=bool(body.get('apply_rate')),
            photo=base64.b64encode(photo).decode() if photo else None,
        )
        return ser_reading(reading, detail=True, role=_role())

    # ------------------------------------------------------------------
    # Tenants
    # ------------------------------------------------------------------

    def tenant_list(self, **kw):
        _require(*STAFF)
        domain = Domain('is_tenant', '=', True) & _search_domain(kw.get('search'), ['name', 'email', 'phone'])
        return _search(request.env['res.partner'], domain, kw, ser_tenant)

    def tenant_get(self, record_id, **kw):
        _require(*STAFF)
        return ser_tenant(self._get_tenant(record_id), detail=True)

    def tenant_create(self, **kw):
        _require(*STAFF)
        vals = _vals(_body(), TENANT_FIELDS, 'res.partner')
        if not vals.get('name'):
            raise ApiError(request.env._("Enter the name of the tenant."))
        # Internal users may lack the "Contact Creation" right: tenants are created with sudo,
        # limited to the tenant fields, and always flagged as tenants.
        partner = request.env['res.partner'].sudo().create(dict(vals, is_tenant=True))
        partner.message_post(body=request.env._("Tenant created from the mobile app by %s.", request.env.user.name))
        return ser_tenant(partner.with_env(request.env), detail=True)

    def tenant_update(self, record_id, **kw):
        _require(*STAFF)
        partner = self._get_tenant(record_id)
        partner.sudo().write(_vals(_body(), TENANT_FIELDS, 'res.partner'))
        return ser_tenant(partner, detail=True)

    def _get_tenant(self, record_id):
        partner = _get('res.partner', record_id)
        if not partner.is_tenant:
            raise MissingError(request.env._("Tenant not found."))
        return partner

    @api_route(f'{API}/tenants/<int:record_id>/invite', methods=('POST',))
    def tenant_invite(self, record_id, **kw):
        """Give the tenant a portal login, so they can use the app; Odoo emails the invitation."""
        _require(*STAFF)
        partner = self._get_tenant(record_id)
        if not partner.email:
            raise ApiError(request.env._("Set the email of %s first: it is their login.", partner.name))
        Users = request.env['res.users'].sudo().with_context(active_test=False)
        user = Users.search([('partner_id', '=', partner.id)], limit=1)
        portal_group = request.env.ref('base.group_portal')
        if user and not user.share:
            raise ApiError(request.env._("%s is an internal user.", partner.name))
        if user:
            user.write({'active': True})
        else:
            if Users.search_count([('login', '=ilike', partner.email)]):
                raise ApiError(request.env._("Another user already has the login %s.", partner.email))
            user = Users.with_context(no_reset_password=True).create({
                'login': partner.email, 'partner_id': partner.id,
                'group_ids': [Command.set([portal_group.id])],
            })
        user.with_context(create_user=True).action_reset_password()
        partner.sudo().message_post(body=request.env._("Mobile app / portal invitation sent to %s.", partner.email))
        return ser_tenant(partner, detail=True)

    @api_route(f'{API}/tenants/<int:record_id>/statement', methods=('GET',))
    def tenant_statement(self, record_id, **kw):
        _require(*BILLING)
        partner = _get('res.partner', record_id)
        return _pdf('rent_management.action_report_tenant_statement', partner, f'Tenant Statement - {partner.name}')

    # ------------------------------------------------------------------
    # Leases
    # ------------------------------------------------------------------

    def lease_list(self, **kw):
        Model, domain, role = _model('rent.lease')
        domain &= _search_domain(kw.get('search'), ['name', 'tenant_id.name', 'unit_id.name', 'property_id.name'])
        if kw.get('state') == 'running':
            domain &= Domain('state', 'in', RUNNING)
        elif kw.get('state'):
            domain &= Domain('state', '=', kw['state'])
        for key in ('tenant_id', 'unit_id', 'property_id'):
            if kw.get(key):
                domain &= Domain(key, '=', _int(kw[key]))
        return _search(Model, domain, kw, ser_lease)

    def lease_get(self, record_id, **kw):
        return ser_lease(_get('rent.lease', record_id), detail=True, role=_role())

    def _lease_defaults(self, vals):
        """What the onchanges of the lease form fill in the web client."""
        unit = request.env['rent.unit'].browse(vals.get('unit_id')).exists() if vals.get('unit_id') else None
        if unit:
            vals.setdefault('rent_amount', unit.base_rent)
            vals.setdefault('deposit_amount', unit.deposit_amount)
            vals.setdefault('maintenance_charge', unit.maintenance_charge)
            if unit.meter_number:
                vals.setdefault('electricity_billing', 'metered')
        start = vals.get('start_date') or fields.Date.context_today(request.env.user)
        vals.setdefault('billing_day', min(start.day, 28))
        if not vals.get('end_date'):
            vals['end_date'] = start + datetime.timedelta(days=-1) + _relativedelta(years=1)
        return vals

    def lease_create(self, **kw):
        _require(*STAFF)
        vals = self._lease_defaults(_vals(_body(), LEASE_FIELDS, 'rent.lease'))
        lease = request.env['rent.lease'].create(vals)
        return ser_lease(lease, detail=True, role=_role())

    def lease_update(self, record_id, **kw):
        _require(*STAFF)
        lease = _get('rent.lease', record_id, 'write')
        lease.write(_vals(_body(), LEASE_FIELDS, 'rent.lease'))
        return ser_lease(lease, detail=True, role=_role())

    def lease_delete(self, record_id, **kw):
        _require(*STAFF)
        _get('rent.lease', record_id, 'unlink').unlink()
        return {'ok': True}

    @api_route(f'{API}/leases/<int:record_id>/action/<string:action>', methods=('POST',))
    def lease_action(self, record_id, action, **kw):
        role = _require(*STAFF)
        if action not in LEASE_ACTIONS:
            raise MissingError(request.env._("Unknown action."))
        if action in BILLING_ACTIONS and role not in BILLING:
            raise ApiError(request.env._("Only accountants can create invoices."), 403, 'forbidden')
        lease = _get('rent.lease', record_id, 'write')
        result = _action_result(getattr(lease, LEASE_ACTIONS[action])())
        result['lease'] = ser_lease(lease, detail=True, role=role)
        return result

    def _moveout_wizard(self, lease, body):
        vals = {'lease_id': lease.id}
        if body.get('moveout_date'):
            vals['moveout_date'] = fields.Date.to_date(body['moveout_date'])
        for name in ('damage_charges', 'final_meter_reading'):
            if body.get(name) not in (None, ''):
                vals[name] = _float(body[name], name)
        if body.get('deduction_note'):
            vals['deduction_note'] = body['deduction_note']
        return request.env['rent.moveout.wizard'].create(vals)

    @api_route(f'{API}/leases/<int:record_id>/moveout/preview', methods=('POST',))
    def moveout_preview(self, record_id, **kw):
        _require(*STAFF)
        lease = _get('rent.lease', record_id, 'write')
        if lease.state not in RUNNING + ('expired',):
            raise ApiError(request.env._("Only running or expired leases can be terminated."))
        wizard = self._moveout_wizard(lease, _body())
        return {
            'moveout_date': wizard.moveout_date, 'deposit_amount': wizard.deposit_amount,
            'damage_charges': wizard.damage_charges, 'unpaid_dues': wizard.unpaid_dues,
            'electricity_billing': wizard.electricity_billing,
            'previous_meter_reading': wizard.previous_meter_reading,
            'final_meter_reading': wizard.final_meter_reading,
            'electricity_charges': wizard.electricity_charges, 'refund_amount': wizard.refund_amount,
            'currency': lease.currency_id.name,
        }

    @api_route(f'{API}/leases/<int:record_id>/moveout', methods=('POST',))
    def moveout_confirm(self, record_id, **kw):
        role = _require(*STAFF)
        lease = _get('rent.lease', record_id, 'write')
        if lease.state not in RUNNING + ('expired',):
            raise ApiError(request.env._("Only running or expired leases can be terminated."))
        result = _action_result(self._moveout_wizard(lease, _body()).action_confirm())
        result['lease'] = ser_lease(lease, detail=True, role=role)
        return result

    @api_route(f'{API}/leases/<int:record_id>/agreement', methods=('GET',))
    def lease_agreement(self, record_id, **kw):
        lease = _get('rent.lease', record_id)
        return _pdf('rent_management.action_report_lease_agreement', lease, f'Lease Agreement - {lease.name}')

    @api_route(f'{API}/leases/<int:record_id>/settlement', methods=('GET',))
    def lease_settlement(self, record_id, **kw):
        lease = _get('rent.lease', record_id)
        if lease.state != 'terminated':
            raise ApiError(request.env._("The settlement exists once the tenant moved out."))
        return _pdf('rent_management.action_report_moveout_settlement', lease, f'Move-out Settlement - {lease.name}')

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def maintenance_list(self, **kw):
        Model, domain, role = _model('rent.maintenance.request')
        domain &= _search_domain(kw.get('search'), ['name', 'unit_id.name', 'tenant_id.name'])
        if kw.get('state') == 'open':
            domain &= Domain('state', 'in', ('new', 'in_progress'))
        elif kw.get('state'):
            domain &= Domain('state', '=', kw['state'])
        if kw.get('mine') and role in STAFF:
            domain &= Domain('assigned_to', '=', request.env.uid)
        for key in ('unit_id', 'lease_id', 'property_id'):
            if kw.get(key):
                domain &= Domain(key, '=', _int(kw[key]))
        return _search(Model, domain, kw, ser_maintenance)

    def maintenance_get(self, record_id, **kw):
        return ser_maintenance(_get('rent.maintenance.request', record_id), detail=True, role=_role())

    def _attach_photos(self, maintenance, photos):
        attachments = request.env['ir.attachment'].sudo()
        for index, photo in enumerate((photos or [])[:MAX_PHOTOS]):
            raw = _decode_image(photo, request.env._("photo"))
            if raw:
                attachments |= attachments.create({
                    'name': f'{maintenance.name}-{index + 1}.jpg', 'raw': raw,
                    'res_model': 'rent.maintenance.request', 'res_id': maintenance.id,
                })
        if attachments:
            maintenance.sudo().image_ids = [Command.link(a.id) for a in attachments]

    def maintenance_create(self, **kw):
        role = _role()
        body = _body()
        Request = request.env['rent.maintenance.request']
        if role == 'tenant':
            # Tenant, unit and lease come from the tenant's own running lease, not from the payload.
            lease = request.env['rent.lease'].sudo().search(
                _tenant_domains(_tenant_partner())['rent.lease'] & Domain('state', 'in', RUNNING)
                & Domain('id', '=', _int(body.get('lease_id'))), limit=1)
            if not lease:
                raise ApiError(request.env._("Select one of your running leases."))
            vals = _vals(body, {'category': 'selection', 'priority': 'selection', 'description': 'html'},
                         Request._name)
            if not (body.get('description') or '').strip():
                raise ApiError(request.env._("Describe the problem."))
            maintenance = Request.sudo().create(dict(
                vals, lease_id=lease.id, unit_id=lease.unit_id.id, tenant_id=lease.tenant_id.id))
            maintenance.message_subscribe(partner_ids=request.env.user.partner_id.ids)
        else:
            _require(*STAFF)
            maintenance = Request.create(_vals(body, MAINTENANCE_FIELDS, Request._name))
        self._attach_photos(maintenance, body.get('photos'))
        return ser_maintenance(maintenance, detail=True, role=role)

    def maintenance_update(self, record_id, **kw):
        role = _require(*STAFF)
        maintenance = _get('rent.maintenance.request', record_id, 'write')
        body = _body()
        maintenance.write(_vals(body, MAINTENANCE_FIELDS, maintenance._name))
        self._attach_photos(maintenance, body.get('photos'))
        return ser_maintenance(maintenance, detail=True, role=role)

    @api_route(f'{API}/maintenance/<int:record_id>/action/<string:action>', methods=('POST',))
    def maintenance_action(self, record_id, action, **kw):
        role = _require(*STAFF)
        if action not in MAINTENANCE_ACTIONS:
            raise MissingError(request.env._("Unknown action."))
        maintenance = _get('rent.maintenance.request', record_id, 'write')
        getattr(maintenance, MAINTENANCE_ACTIONS[action])()
        return ser_maintenance(maintenance, detail=True, role=role)

    # ------------------------------------------------------------------
    # Electricity readings
    # ------------------------------------------------------------------

    def reading_list(self, **kw):
        Model, domain, role = _model('rent.electricity.reading')
        domain &= _search_domain(kw.get('search'), ['name', 'unit_id.name', 'tenant_id.name', 'property_id.name'])
        if kw.get('state'):
            domain &= Domain('state', '=', kw['state'])
        for key in ('lease_id', 'unit_id', 'property_id'):
            if kw.get(key):
                domain &= Domain(key, '=', _int(kw[key]))
        return _search(Model, domain, kw, ser_reading)

    def reading_get(self, record_id, **kw):
        return ser_reading(_get('rent.electricity.reading', record_id), detail=True, role=_role())

    def reading_create(self, **kw):
        role = _require(*STAFF)
        reading = request.env['rent.electricity.reading'].create(
            _vals(_body(), READING_FIELDS, 'rent.electricity.reading'))
        return ser_reading(reading, detail=True, role=role)

    def reading_update(self, record_id, **kw):
        role = _require(*STAFF)
        reading = _get('rent.electricity.reading', record_id, 'write')
        reading.write(_vals(_body(), READING_FIELDS, reading._name))
        return ser_reading(reading, detail=True, role=role)

    @api_route(f'{API}/readings/<int:record_id>/action/<string:action>', methods=('POST',))
    def reading_action(self, record_id, action, **kw):
        role = _require(*STAFF)
        if action not in READING_ACTIONS:
            raise MissingError(request.env._("Unknown action."))
        if action in BILLING_ACTIONS and role not in BILLING:
            raise ApiError(request.env._("Only accountants can create invoices."), 403, 'forbidden')
        reading = _get('rent.electricity.reading', record_id, 'write')
        result = _action_result(getattr(reading, READING_ACTIONS[action])())
        result['reading'] = ser_reading(reading, detail=True, role=role)
        return result

    @api_route(f'{API}/readings/invoice', methods=('POST',))
    def readings_invoice(self, **kw):
        """Invoice several confirmed readings at once (one invoice per lease)."""
        _require(*BILLING)
        ids = [_int(i) for i in (_body().get('ids') or []) if _int(i)]
        readings = request.env['rent.electricity.reading'].browse(ids).exists()
        readings.check_access('write')
        return _action_result(readings.action_create_invoice())

    # ------------------------------------------------------------------
    # Invoices and payments
    # ------------------------------------------------------------------

    @api_route(f'{API}/invoices', methods=('GET',))
    def invoice_list(self, **kw):
        Model, domain, role = _model('account.move')
        if role not in BILLING + ('tenant',):
            raise ApiError(request.env._("Only accountants can see invoices."), 403, 'forbidden')
        if role != 'tenant':
            domain &= Domain('rent_lease_id', '!=', False) & Domain('move_type', 'in', ('out_invoice', 'out_refund'))
        domain &= _search_domain(kw.get('search'), ['name', 'partner_id.name', 'rent_lease_id.name'])
        today = fields.Date.context_today(request.env.user)
        unpaid = Domain('move_type', '=', 'out_invoice') & Domain('state', '=', 'posted') \
            & Domain('payment_state', 'in', ('not_paid', 'partial'))
        status = kw.get('status')
        if status == 'to_pay':
            domain &= unpaid
        elif status == 'overdue':
            domain &= unpaid & Domain('invoice_date_due', '<', today)
        elif status == 'paid':
            domain &= Domain('move_type', '=', 'out_invoice') & Domain('payment_state', 'in', ('paid', 'in_payment'))
        elif status == 'draft':
            domain &= Domain('state', '=', 'draft')
        elif status == 'credit':
            domain &= Domain('move_type', '=', 'out_refund')
        if kw.get('invoice_type'):
            domain &= Domain('rent_invoice_type', '=', kw['invoice_type'])
        if kw.get('lease_id'):
            domain &= Domain('rent_lease_id', '=', _int(kw['lease_id']))
        return _search(Model, domain, kw, ser_invoice, order='invoice_date desc, id desc')

    def _get_invoice(self, record_id, operation='read'):
        role = _role()
        if role not in BILLING + ('tenant',):
            raise ApiError(request.env._("Only accountants can see invoices."), 403, 'forbidden')
        move = _get('account.move', record_id, operation)
        if not move.rent_lease_id and role != 'tenant':
            raise MissingError(request.env._("This is not a rent invoice."))
        return move, role

    @api_route(f'{API}/invoices/<int:record_id>', methods=('GET',))
    def invoice_get(self, record_id, **kw):
        move, role = self._get_invoice(record_id)
        return ser_invoice(move, detail=True, role=role)

    @api_route(f'{API}/invoices/<int:record_id>/pdf', methods=('GET',))
    def invoice_pdf(self, record_id, **kw):
        move, _role_name = self._get_invoice(record_id)
        return _pdf('rent_management.action_report_rent_invoice', move, move.name or 'Invoice')

    @api_route(f'{API}/invoices/<int:record_id>/receipt', methods=('GET',))
    def invoice_receipt(self, record_id, **kw):
        move, _role_name = self._get_invoice(record_id)
        return _pdf('rent_management.action_report_rent_receipt', move, f'Rent Receipt - {move.name}')

    @api_route(f'{API}/invoices/<int:record_id>/payment', methods=('POST',))
    def invoice_register_payment(self, record_id, **kw):
        """Record a payment received for the invoice (cash, bank transfer, UPI...)."""
        move, role = self._get_invoice(record_id, 'write')
        if role not in BILLING:
            raise ApiError(request.env._("Only accountants can register payments."), 403, 'forbidden')
        body = _body()
        vals = {}
        if body.get('amount') not in (None, ''):
            vals['amount'] = _float(body['amount'], request.env._("The amount"))
            if vals['amount'] <= 0:
                raise ApiError(request.env._("The amount must be positive."))
        if body.get('journal_id'):
            vals['journal_id'] = _int(body['journal_id'])
        if body.get('payment_date'):
            vals['payment_date'] = fields.Date.to_date(body['payment_date'])
        if body.get('memo'):
            vals['communication'] = body['memo']
        wizard = request.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=move.ids).create(vals)
        wizard._create_payments()
        return ser_invoice(move, detail=True, role=role)

    @api_route(f'{API}/invoices/<int:record_id>/send', methods=('POST',))
    def invoice_send(self, record_id, **kw):
        """Email the invoice to the tenant with the standard invoice template."""
        move, role = self._get_invoice(record_id, 'write')
        if role not in BILLING:
            raise ApiError(request.env._("Only accountants can send invoices."), 403, 'forbidden')
        if not move.partner_id.email:
            raise ApiError(request.env._("%s has no email address.", move.partner_id.name))
        template = request.env.ref('account.email_template_edi_invoice', raise_if_not_found=False)
        if not template:
            raise ApiError(request.env._("The invoice email template is missing."))
        move.message_post_with_source(template, subtype_xmlid='mail.mt_comment', partner_ids=move.partner_id.ids)
        move.sudo().is_move_sent = True
        return {'ok': True}

    # ------------------------------------------------------------------
    # Chatter
    # ------------------------------------------------------------------

    def messages(self, model, record_id, **kw):
        if model not in MESSAGE_MODELS:
            raise MissingError(request.env._("Unknown document."))
        record = _get(model, record_id)
        domain = [('model', '=', model), ('res_id', '=', record.id), ('message_type', 'in', ('comment', 'email'))]
        if _role() == 'tenant':
            domain += [('subtype_id.internal', '=', False)]
        messages = request.env['mail.message'].sudo().search(domain, limit=50)
        return {'items': [{
            'id': m.id, 'body': _text(m.body), 'date': m.date, 'author': m.author_id.name or m.email_from or '',
            'mine': m.author_id == request.env.user.partner_id,
            'attachments': [{'id': a.id, 'name': a.name, 'url': f"{API}/attachment/{a.id}"} for a in m.attachment_ids],
        } for m in messages if m.body]}

    def message_post(self, model, record_id, **kw):
        if model not in MESSAGE_MODELS:
            raise MissingError(request.env._("Unknown document."))
        record = _get(model, record_id)
        text = (_body().get('body') or '').strip()
        if not text:
            raise ApiError(request.env._("Write a message."))
        if _role() == 'tenant':
            record = record.sudo().with_context(mail_create_nosubscribe=False)
        record.message_post(body=plaintext2html(text), message_type='comment', subtype_xmlid='mail.mt_comment',
                            author_id=request.env.user.partner_id.id)
        return {'ok': True}

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    @api_route(f'{API}/image/<string:model>/<int:record_id>/<string:field>', methods=('GET',))
    def image(self, model, record_id, field, **kw):
        if field not in IMAGE_FIELDS.get(model, ()):
            raise MissingError(request.env._("Unknown image."))
        if model == 'res.partner':
            # Tenants see their own photo only; staff, the contacts they may read.
            record = request.env['res.partner'].browse(record_id).exists()
            allowed = record == request.env.user.partner_id if _role() == 'tenant' \
                else bool(record) and record.has_access('read')
            if not allowed:
                raise MissingError(request.env._("Image not found."))
            record = record.sudo()
        else:
            record = _get(model, record_id).sudo()
        return request.env['ir.binary']._get_image_stream_from(record, field).get_response(
            max_age=3600, immutable=bool(kw.get('unique')))

    @api_route(f'{API}/attachment/<int:attachment_id>', methods=('GET',))
    def attachment(self, attachment_id, **kw):
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if not attachment or attachment.res_model not in MESSAGE_MODELS or not attachment.res_id:
            raise MissingError(request.env._("File not found."))
        _get(attachment.res_model, attachment.res_id)  # raises unless the user may read the document
        return request.env['ir.binary']._get_stream_from(attachment).get_response(max_age=3600)

    # ------------------------------------------------------------------
    # Settings (administrator)
    # ------------------------------------------------------------------

    def settings(self, **kw):
        _require('admin')
        return self._settings()

    def _settings(self):
        company = request.env.company
        data = {name: company[name] for name in SETTINGS_FIELDS}
        data.update({
            'rent_income_account': _m2o(company.rent_income_account_id),
            'rent_deposit_account': _m2o(company.rent_deposit_account_id),
            'rent_journal': _m2o(company.rent_journal_id),
            'company': company.name,
        })
        return data

    def settings_update(self, **kw):
        _require('admin')
        # Rent Administrators own the rent configuration even without the Settings right:
        # sudo, but only for these rent fields of the current company.
        request.env.company.sudo().write(_vals(_body(), SETTINGS_FIELDS, 'res.company'))
        return self._settings()


    # ------------------------------------------------------------------
    # Paths serving several methods: one route each, so that the CORS preflight
    # (answered from the first matching route) lists all of their methods.
    # ------------------------------------------------------------------

    def _by_method(self, handlers, **kw):
        return handlers[request.httprequest.method](**kw)

    @api_route(f'{API}/me', methods=('GET', 'PUT'))
    def route_me(self, **kw):
        return self._by_method({'GET': self.me, 'PUT': self.me_update}, **kw)

    @api_route(f'{API}/properties', methods=('GET', 'POST'))
    def route_properties(self, **kw):
        return self._by_method({'GET': self.property_list, 'POST': self.property_create}, **kw)

    @api_route(f'{API}/properties/<int:record_id>', methods=('GET', 'PUT', 'DELETE'))
    def route_properties_record_id(self, **kw):
        return self._by_method({'GET': self.property_get, 'PUT': self.property_update, 'DELETE': self.property_archive}, **kw)

    @api_route(f'{API}/units', methods=('GET', 'POST'))
    def route_units(self, **kw):
        return self._by_method({'GET': self.unit_list, 'POST': self.unit_create}, **kw)

    @api_route(f'{API}/units/<int:record_id>', methods=('GET', 'PUT', 'DELETE'))
    def route_units_record_id(self, **kw):
        return self._by_method({'GET': self.unit_get, 'PUT': self.unit_update, 'DELETE': self.unit_archive}, **kw)

    @api_route(f'{API}/units/<int:record_id>/meter', methods=('GET', 'POST'))
    def route_units_record_id_meter(self, **kw):
        return self._by_method({'GET': self.meter_entry, 'POST': self.meter_save}, **kw)

    @api_route(f'{API}/tenants', methods=('GET', 'POST'))
    def route_tenants(self, **kw):
        return self._by_method({'GET': self.tenant_list, 'POST': self.tenant_create}, **kw)

    @api_route(f'{API}/tenants/<int:record_id>', methods=('GET', 'PUT'))
    def route_tenants_record_id(self, **kw):
        return self._by_method({'GET': self.tenant_get, 'PUT': self.tenant_update}, **kw)

    @api_route(f'{API}/leases', methods=('GET', 'POST'))
    def route_leases(self, **kw):
        return self._by_method({'GET': self.lease_list, 'POST': self.lease_create}, **kw)

    @api_route(f'{API}/leases/<int:record_id>', methods=('GET', 'PUT', 'DELETE'))
    def route_leases_record_id(self, **kw):
        return self._by_method({'GET': self.lease_get, 'PUT': self.lease_update, 'DELETE': self.lease_delete}, **kw)

    @api_route(f'{API}/maintenance', methods=('GET', 'POST'))
    def route_maintenance(self, **kw):
        return self._by_method({'GET': self.maintenance_list, 'POST': self.maintenance_create}, **kw)

    @api_route(f'{API}/maintenance/<int:record_id>', methods=('GET', 'PUT'))
    def route_maintenance_record_id(self, **kw):
        return self._by_method({'GET': self.maintenance_get, 'PUT': self.maintenance_update}, **kw)

    @api_route(f'{API}/readings', methods=('GET', 'POST'))
    def route_readings(self, **kw):
        return self._by_method({'GET': self.reading_list, 'POST': self.reading_create}, **kw)

    @api_route(f'{API}/readings/<int:record_id>', methods=('GET', 'PUT'))
    def route_readings_record_id(self, **kw):
        return self._by_method({'GET': self.reading_get, 'PUT': self.reading_update}, **kw)

    @api_route(f'{API}/messages/<string:model>/<int:record_id>', methods=('GET', 'POST'))
    def route_messages_model_record_id(self, **kw):
        return self._by_method({'GET': self.messages, 'POST': self.message_post}, **kw)

    @api_route(f'{API}/settings', methods=('GET', 'PUT'))
    def route_settings(self, **kw):
        return self._by_method({'GET': self.settings, 'PUT': self.settings_update}, **kw)


def _relativedelta(**kwargs):
    from dateutil.relativedelta import relativedelta  # noqa: PLC0415
    return relativedelta(**kwargs)
