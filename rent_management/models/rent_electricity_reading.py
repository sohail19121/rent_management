from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError


class RentElectricityReading(models.Model):
    _name = 'rent.electricity.reading'
    _description = "Electricity Meter Reading"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_start desc, property_id, unit_id'
    _check_company_auto = True

    name = fields.Char(compute='_compute_name', store=True)
    lease_id = fields.Many2one(
        'rent.lease', string="Lease", required=True, index=True, ondelete='restrict', check_company=True,
        domain="[('electricity_billing', '=', 'metered'), ('state', 'in', ('active', 'expiring', 'expired', 'terminated'))]")
    unit_id = fields.Many2one(related='lease_id.unit_id', store=True, index=True)
    property_id = fields.Many2one(related='lease_id.property_id', store=True, index=True)
    tenant_id = fields.Many2one(related='lease_id.tenant_id', store=True, index=True)
    company_id = fields.Many2one(related='lease_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    meter_number = fields.Char(related='unit_id.meter_number')
    period_start = fields.Date(required=True, tracking=True)
    period_end = fields.Date(required=True, tracking=True)
    reading_date = fields.Date(default=fields.Date.context_today, required=True)
    previous_reading = fields.Float(
        compute='_compute_previous_reading', store=True, readonly=False, precompute=True,
        digits=(16, 2), help="Last reading of this unit's meter, or the opening reading of the lease.")
    current_reading = fields.Float(digits=(16, 2), tracking=True)
    consumption = fields.Float(string="Units (kWh)", compute='_compute_amount', store=True, digits=(16, 2))
    rate = fields.Float(
        string="Rate per kWh", compute='_compute_rate', store=True, readonly=False, precompute=True, digits=(16, 4))
    fixed_charge = fields.Monetary(
        compute='_compute_fixed_charge', store=True, readonly=False, precompute=True,
        help="Fixed meter charge billed with the reading.")
    amount = fields.Monetary(compute='_compute_amount', store=True)
    meter_photo = fields.Image(max_width=1280, max_height=1280)
    state = fields.Selection([
        ('draft', "To Enter"),
        ('confirmed', "Confirmed"),
        ('invoiced', "Invoiced"),
        ('cancelled', "Cancelled"),
    ], default='draft', required=True, tracking=True, string="Status")
    invoice_id = fields.Many2one('account.move', string="Invoice", readonly=True, copy=False, index='btree_not_null')
    notes = fields.Text()

    @api.depends('unit_id.name', 'period_start')
    def _compute_name(self):
        for reading in self:
            period = reading.period_start.strftime('%b %Y') if reading.period_start else ''
            reading.name = f"{reading.unit_id.name or ''} - {period}"

    @api.depends('lease_id', 'period_start')
    def _compute_previous_reading(self):
        for reading in self:
            if reading.lease_id:
                reading.previous_reading = reading.lease_id._get_last_meter_reading(
                    before=reading.period_start, exclude=reading)
            else:
                reading.previous_reading = 0.0

    # Rate and fixed charge are computed separately: a shared compute is skipped entirely
    # when one of its fields is given at creation, leaving the other one at zero.
    @api.depends('lease_id')
    def _compute_rate(self):
        for reading in self:
            reading.rate = reading.lease_id.electricity_rate

    @api.depends('lease_id')
    def _compute_fixed_charge(self):
        for reading in self:
            reading.fixed_charge = reading.lease_id.electricity_fixed_amount

    @api.depends('previous_reading', 'current_reading', 'rate', 'fixed_charge')
    def _compute_amount(self):
        for reading in self:
            if not reading.current_reading:
                reading.consumption = reading.amount = 0.0
                continue
            consumption = max(reading.current_reading - reading.previous_reading, 0.0)
            reading.consumption = consumption
            currency = reading.currency_id or self.env.company.currency_id
            reading.amount = currency.round(consumption * reading.rate + reading.fixed_charge)

    @api.constrains('period_start', 'period_end')
    def _check_period(self):
        for reading in self:
            if reading.period_end < reading.period_start:
                raise ValidationError(self.env._("The period of reading %s ends before it starts.", reading.name))
            duplicate = self.search_count([
                ('id', '!=', reading.id),
                ('lease_id', '=', reading.lease_id.id),
                ('state', '!=', 'cancelled'),
                ('period_start', '<=', reading.period_end),
                ('period_end', '>=', reading.period_start),
            ], limit=1)
            if duplicate:
                raise ValidationError(self.env._(
                    "Lease %(lease)s already has a meter reading overlapping %(period)s.",
                    lease=reading.lease_id.name, period=reading.name))

    @api.constrains('previous_reading', 'current_reading', 'state')
    def _check_readings(self):
        for reading in self.filtered(lambda r: r.state in ('confirmed', 'invoiced')):
            if reading.current_reading < reading.previous_reading:
                raise ValidationError(self.env._(
                    "The current reading of %(name)s (%(current)s) is lower than the previous one (%(previous)s).",
                    name=reading.name, current=reading.current_reading, previous=reading.previous_reading))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_invoiced(self):
        if any(reading.state == 'invoiced' for reading in self):
            raise UserError(self.env._("Invoiced meter readings cannot be deleted."))

    def action_confirm(self):
        for reading in self:
            if reading.state != 'draft':
                raise UserError(self.env._("Only readings to enter can be confirmed."))
            if not reading.current_reading:
                raise UserError(self.env._("Enter the current meter reading of %s.", reading.name))
        self.write({'state': 'confirmed'})
        self.activity_feedback(['mail.mail_activity_data_todo'])
        return True

    def action_reset_draft(self):
        if any(reading.state == 'invoiced' for reading in self):
            raise UserError(self.env._("Invoiced meter readings cannot be reset."))
        self.write({'state': 'draft'})
        return True

    def action_cancel(self):
        if any(reading.state == 'invoiced' for reading in self):
            raise UserError(self.env._("Invoiced meter readings cannot be cancelled."))
        self.write({'state': 'cancelled'})
        self.activity_unlink(['mail.mail_activity_data_todo'])
        return True

    def action_create_invoice(self):
        """Invoice the selected confirmed readings now, one electricity invoice per lease."""
        readings = self.filtered(lambda r: r.state == 'confirmed')
        if not readings:
            raise UserError(self.env._("Select confirmed meter readings to invoice."))
        invoices = self.env['account.move']
        today = fields.Date.context_today(self)
        for lease, lease_readings in readings.grouped('lease_id').items():
            invoice = self.env['account.move'].create(lease._prepare_invoice_vals(
                today, 'electricity', lease_readings._prepare_invoice_lines()))
            invoice.action_post()
            lease_readings._mark_invoiced(invoice)
            invoices |= invoice
        return readings.lease_id[:1]._action_open_moves(invoices)

    def _prepare_invoice_lines(self):
        product = self.env.ref('rent_management.product_electricity')
        lines = []
        for reading in self.sorted('period_start'):
            lines.append(Command.create({
                'product_id': product.id,
                'name': self.env._(
                    "Electricity %(unit)s, %(start)s to %(end)s: %(previous)s to %(current)s (meter %(meter)s)",
                    unit=reading.unit_id.display_name, start=reading.period_start, end=reading.period_end,
                    previous=reading.previous_reading, current=reading.current_reading,
                    meter=reading.meter_number or "-"),
                'quantity': reading.consumption,
                'price_unit': reading.rate,
                'tax_ids': [Command.clear()],
            }))
            if reading.fixed_charge:
                lines.append(Command.create({
                    'product_id': product.id,
                    'name': self.env._("Electricity fixed charge, %s", reading.name),
                    'quantity': 1,
                    'price_unit': reading.fixed_charge,
                    'tax_ids': [Command.clear()],
                }))
        return lines

    def _mark_invoiced(self, invoice):
        self.write({'state': 'invoiced', 'invoice_id': invoice.id})
