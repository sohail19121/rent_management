import io
import uuid

from datetime import timedelta

import qrcode

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import BinaryBytes

RUNNING_LEASE_STATES = ('active', 'expiring')


class RentUnit(models.Model):
    _name = 'rent.unit'
    _description = "Rental Unit"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'property_id, floor, name'
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    property_id = fields.Many2one(
        'rent.property', string="Property", required=True, ondelete='restrict', index=True,
        tracking=True, check_company=True)
    company_id = fields.Many2one(related='property_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    floor = fields.Char()
    unit_type = fields.Selection([
        ('flat', "Flat"),
        ('room', "Room"),
        ('shop', "Shop"),
        ('office', "Office"),
        ('warehouse', "Warehouse"),
    ], required=True, default='flat')
    area_sqft = fields.Float(string="Area (sq ft)")
    bedrooms = fields.Integer()
    furnishing = fields.Selection([
        ('unfurnished', "Unfurnished"),
        ('semi', "Semi-Furnished"),
        ('full', "Fully Furnished"),
    ], default='unfurnished')
    base_rent = fields.Monetary(tracking=True)
    deposit_amount = fields.Monetary(string="Security Deposit")
    maintenance_charge = fields.Monetary()
    meter_number = fields.Char(string="Electricity Meter No.", tracking=True)
    meter_qr_token = fields.Char(
        compute='_compute_meter_qr_token', store=True, readonly=True, precompute=True, copy=False,
        groups='rent_management.group_rent_user',
        help="Secret part of the meter QR link. Regenerate it to invalidate printed labels.")
    meter_qr_url = fields.Char(string="Meter Reading Link", compute='_compute_meter_qr')
    meter_qr_image = fields.Binary(string="Meter QR Code", compute='_compute_meter_qr')
    under_maintenance = fields.Boolean(
        tracking=True, help="Check to take the unit off the market while it is being repaired.")
    state = fields.Selection([
        ('vacant', "Vacant"),
        ('reserved', "Reserved"),
        ('occupied', "Occupied"),
        ('under_maintenance', "Under Maintenance"),
    ], compute='_compute_lease_info', store=True, tracking=True, string="Status")
    current_lease_id = fields.Many2one('rent.lease', compute='_compute_lease_info', store=True, string="Current Lease")
    current_tenant_id = fields.Many2one(
        'res.partner', compute='_compute_lease_info', store=True, string="Current Tenant")
    lease_ids = fields.One2many('rent.lease', 'unit_id', string="Leases")
    maintenance_request_ids = fields.One2many('rent.maintenance.request', 'unit_id', string="Maintenance Requests")
    image = fields.Image(max_width=1024, max_height=1024)
    color = fields.Integer(compute='_compute_color')
    active = fields.Boolean(default=True)

    _meter_qr_token_uniq = models.Constraint('UNIQUE (meter_qr_token)', "The meter QR code must be unique.")
    _name_property_uniq = models.Constraint(
        'UNIQUE (name, property_id)', "A unit with this name already exists in the property.")

    @api.depends('under_maintenance', 'lease_ids.state')
    def _compute_lease_info(self):
        for unit in self:
            running = unit.lease_ids.filtered(lambda lease: lease.state in RUNNING_LEASE_STATES)[:1]
            confirmed = unit.lease_ids.filtered(lambda lease: lease.state == 'confirmed')[:1]
            unit.current_lease_id = running or confirmed
            unit.current_tenant_id = (running or confirmed).tenant_id
            if unit.under_maintenance:
                unit.state = 'under_maintenance'
            elif running:
                unit.state = 'occupied'
            elif confirmed:
                unit.state = 'reserved'
            else:
                unit.state = 'vacant'

    @api.depends()
    def _compute_meter_qr_token(self):
        for unit in self:
            if not unit.meter_qr_token:
                unit.meter_qr_token = uuid.uuid4().hex

    @api.depends('meter_qr_token')
    @api.depends_context('uid')
    def _compute_meter_qr(self):
        for unit in self:
            token = unit.sudo().meter_qr_token
            if not token:
                unit.meter_qr_url = unit.meter_qr_image = False
                continue
            unit.meter_qr_url = f"{unit.get_base_url()}/rent/meter/{token}"
            unit.meter_qr_image = BinaryBytes(self._make_qr_png(unit.meter_qr_url))

    @api.model
    def _make_qr_png(self, data):
        # qrcode + Pillow (Odoo requirements) rather than ir.actions.report.barcode(), whose PNG
        # output needs the reportlab renderPM backend that pip installations often lack.
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        buffer = io.BytesIO()
        qr.make_image(fill_color='black', back_color='white').save(buffer, format='PNG')
        return buffer.getvalue()

    @api.depends('state')
    def _compute_color(self):
        colors = {'vacant': 10, 'reserved': 3, 'occupied': 4, 'under_maintenance': 1}
        for unit in self:
            unit.color = colors.get(unit.state, 0)

    @api.depends('name', 'property_id.name')
    def _compute_display_name(self):
        for unit in self:
            unit.display_name = f"{unit.property_id.name} / {unit.name}" if unit.property_id else unit.name

    def action_regenerate_meter_qr(self):
        """Issue a new QR link, e.g. when a label is lost: previously printed labels stop working."""
        for unit in self:
            unit.sudo().meter_qr_token = uuid.uuid4().hex
            unit.message_post(body=self.env._("Meter QR code regenerated: print and stick the new label."))
        return True

    def _get_metered_lease(self):
        self.ensure_one()
        lease = self.current_lease_id
        if lease.state in RUNNING_LEASE_STATES and lease.electricity_billing == 'metered':
            return lease
        return self.env['rent.lease']

    def _get_meter_entry(self):
        """What the QR reading page pre-fills: the reading to enter this month, or the one to create."""
        self.ensure_one()
        lease = self._get_metered_lease()
        if not lease:
            running = self.current_lease_id
            return {
                'lease': lease,
                # A running lease exists but electricity is not billed by meter: say so on the QR page.
                'unmetered_lease': running if running.state in RUNNING_LEASE_STATES else self.env['rent.lease'],
            }
        reading = lease.electricity_reading_ids.filtered(lambda r: r.state == 'draft').sorted('period_start')[:1]
        if reading:
            return {
                'lease': lease,
                'reading': reading,
                'period_start': reading.period_start,
                'period_end': reading.period_end,
                'previous_reading': reading.previous_reading,
                'rate': reading.rate,
            }
        today = fields.Date.context_today(self)
        last_end = lease._get_last_reading_end()
        period_start = last_end + timedelta(days=1) if last_end else lease.start_date
        return {
            'lease': lease,
            'reading': self.env['rent.electricity.reading'],
            'period_start': min(period_start, today),
            'period_end': today,
            'previous_reading': lease._get_last_meter_reading(),
            'rate': lease.electricity_rate,
        }

    def _save_meter_reading(self, current_reading, rate, apply_rate_to_lease=False, photo=None):
        """Record a reading taken on site (QR page): fill this month's reading, or create it, and confirm it."""
        self.ensure_one()
        entry = self._get_meter_entry()
        lease = entry['lease']
        if not lease:
            raise UserError(self.env._("Unit %s has no running lease billed by meter.", self.display_name))
        if current_reading < entry['previous_reading']:
            raise UserError(self.env._(
                "The reading (%(current)s) cannot be lower than the previous one (%(previous)s).",
                current=current_reading, previous=entry['previous_reading']))
        if rate < 0:
            raise UserError(self.env._("The rate cannot be negative."))
        vals = {
            'current_reading': current_reading,
            'rate': rate,
            'reading_date': fields.Date.context_today(self),
        }
        if photo:
            vals['meter_photo'] = photo
        reading = entry['reading']
        if reading:
            reading.write(vals)
        else:
            reading = self.env['rent.electricity.reading'].create({
                'lease_id': lease.id,
                'period_start': entry['period_start'],
                'period_end': entry['period_end'],
                'previous_reading': entry['previous_reading'],
                **vals,
            })
        reading.action_confirm()
        if apply_rate_to_lease and rate != lease.electricity_rate:
            lease.electricity_rate = rate
        return reading

    def action_view_leases(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('rent_management.rent_lease_action')
        action['domain'] = [('unit_id', '=', self.id)]
        action['context'] = {'default_unit_id': self.id}
        return action
