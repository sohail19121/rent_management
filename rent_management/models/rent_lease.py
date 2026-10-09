import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)

FREQUENCY_MONTHS = {'monthly': 1, 'quarterly': 3, 'yearly': 12}
BLOCKING_STATES = ('confirmed', 'active', 'expiring')
RUNNING_STATES = ('active', 'expiring')


class RentLease(models.Model):
    _name = 'rent.lease'
    _description = "Lease Agreement"
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string="Reference", readonly=True, copy=False, default=lambda self: self.env._("New"))
    tenant_id = fields.Many2one(
        'res.partner', string="Tenant", required=True, tracking=True, index=True,
        domain="[('is_tenant', '=', True)]")
    unit_id = fields.Many2one(
        'rent.unit', string="Unit", required=True, tracking=True, index=True, ondelete='restrict',
        check_company=True)
    property_id = fields.Many2one(related='unit_id.property_id', store=True, index=True, string="Property")
    manager_id = fields.Many2one(related='property_id.manager_id', string="Property Manager")
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([
        ('draft', "Draft"),
        ('confirmed', "Confirmed"),
        ('active', "Active"),
        ('expiring', "Expiring"),
        ('expired', "Expired"),
        ('terminated', "Terminated"),
        ('renewed', "Renewed"),
        ('cancelled', "Cancelled"),
    ], default='draft', required=True, tracking=True, copy=False, string="Status")

    # Terms
    start_date = fields.Date(required=True, tracking=True, default=fields.Date.context_today)
    end_date = fields.Date(required=True, tracking=True)
    duration_months = fields.Integer(compute='_compute_duration_months', string="Duration (months)")
    notice_period_days = fields.Integer(default=30)
    renewed_from_id = fields.Many2one('rent.lease', string="Renewal Of", readonly=True, copy=False)
    renewal_ids = fields.One2many('rent.lease', 'renewed_from_id', string="Renewals")

    # Billing
    rent_amount = fields.Monetary(required=True, tracking=True)
    maintenance_charge = fields.Monetary()
    billing_day = fields.Integer(default=1, help="Day of the month on which rent is due (1-28).")
    billing_frequency = fields.Selection([
        ('monthly', "Monthly"),
        ('quarterly', "Quarterly"),
        ('yearly', "Yearly"),
    ], default='monthly', required=True)
    next_invoice_date = fields.Date(
        copy=False, tracking=True, help="Due date of the next rent invoice to generate.")
    late_fee_type = fields.Selection([('fixed', "Fixed Amount"), ('percent', "Percentage of Due")], default='fixed')
    late_fee_value = fields.Float()
    grace_days = fields.Integer(default=5, help="Days after the due date before a late fee is charged.")
    escalation_percent = fields.Float(string="Escalation (%)")
    escalation_every_months = fields.Integer(string="Escalate Every (months)", default=12)
    next_escalation_date = fields.Date(copy=False, tracking=True)

    # Electricity
    electricity_billing = fields.Selection([
        ('none', "Not Charged / Included in Rent"),
        ('fixed', "Fixed Monthly Amount"),
        ('metered', "Metered (Monthly Reading)"),
    ], default='none', required=True, tracking=True)
    electricity_rate = fields.Float(
        string="Rate per kWh", digits=(16, 4), tracking=True,
        default=lambda self: self.env.company.rent_electricity_rate)
    electricity_fixed_amount = fields.Monetary(
        string="Electricity Fixed Charge",
        help="Fixed lump sum per month, or fixed meter charge added to each metered reading.")
    electricity_opening_reading = fields.Float(
        string="Opening Meter Reading", digits=(16, 2), copy=False,
        help="Meter reading at move-in, used as the previous reading of the first month.")
    electricity_reading_ids = fields.One2many('rent.electricity.reading', 'lease_id', string="Meter Readings")
    electricity_reading_count = fields.Integer(compute='_compute_electricity_reading_count')

    # Deposit
    deposit_amount = fields.Monetary(tracking=True)
    deposit_invoice_id = fields.Many2one('account.move', string="Deposit Invoice", readonly=True, copy=False)
    deposit_refund_id = fields.Many2one('account.move', string="Deposit Credit Note", readonly=True, copy=False)
    deposit_refunded_amount = fields.Monetary(readonly=True, copy=False)
    deposit_settled = fields.Boolean(readonly=True, copy=False)
    deposit_status = fields.Selection([
        ('pending', "Pending"),
        ('received', "Received"),
        ('partially_refunded', "Partially Refunded"),
        ('refunded', "Refunded"),
    ], compute='_compute_deposit_status', store=True, tracking=True)

    # Move-out settlement
    moveout_date = fields.Date(readonly=True, copy=False)
    moveout_damage_charges = fields.Monetary(readonly=True, copy=False)
    moveout_unpaid_dues = fields.Monetary(readonly=True, copy=False)
    moveout_electricity_charges = fields.Monetary(readonly=True, copy=False)
    moveout_deduction_note = fields.Text(readonly=True, copy=False)

    # Documents
    agreement_attachment_id = fields.Many2one('ir.attachment', string="Signed Agreement", copy=False)
    signed = fields.Boolean(tracking=True, copy=False)
    notes = fields.Html()

    # Links
    invoice_ids = fields.One2many('account.move', 'rent_lease_id', string="Invoices")
    invoice_count = fields.Integer(compute='_compute_invoice_amounts', compute_sudo=True)
    amount_due = fields.Monetary(compute='_compute_invoice_amounts', compute_sudo=True)
    maintenance_request_ids = fields.One2many('rent.maintenance.request', 'lease_id', string="Maintenance Requests")
    maintenance_count = fields.Integer(compute='_compute_maintenance_count')

    _billing_day_range = models.Constraint(
        'CHECK (billing_day BETWEEN 1 AND 28)', "The billing day must be between 1 and 28.")
    _rent_amount_positive = models.Constraint('CHECK (rent_amount >= 0)', "The rent cannot be negative.")

    # ------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------

    @api.depends('start_date', 'end_date')
    def _compute_duration_months(self):
        for lease in self:
            if lease.start_date and lease.end_date and lease.end_date > lease.start_date:
                delta = relativedelta(lease.end_date + timedelta(days=1), lease.start_date)
                lease.duration_months = delta.years * 12 + delta.months
            else:
                lease.duration_months = 0

    @api.depends('deposit_amount', 'deposit_invoice_id.payment_state', 'deposit_refunded_amount', 'deposit_settled')
    def _compute_deposit_status(self):
        for lease in self:
            if lease.deposit_settled:
                fully = lease.currency_id.compare_amounts(lease.deposit_refunded_amount, lease.deposit_amount) >= 0
                lease.deposit_status = 'refunded' if fully else 'partially_refunded'
            elif lease.deposit_invoice_id.payment_state in ('paid', 'in_payment'):
                lease.deposit_status = 'received'
            else:
                lease.deposit_status = 'pending'

    @api.depends('invoice_ids.state', 'invoice_ids.amount_residual_signed')
    def _compute_invoice_amounts(self):
        for lease in self:
            invoices = lease.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice')
            lease.invoice_count = len(lease.invoice_ids)
            lease.amount_due = sum(invoices.filtered(lambda m: m.state == 'posted').mapped('amount_residual_signed'))

    @api.depends('maintenance_request_ids')
    def _compute_maintenance_count(self):
        for lease in self:
            lease.maintenance_count = len(lease.maintenance_request_ids)

    @api.depends('electricity_reading_ids')
    def _compute_electricity_reading_count(self):
        for lease in self:
            lease.electricity_reading_count = len(lease.electricity_reading_ids)

    def _compute_access_url(self):
        super()._compute_access_url()
        for lease in self:
            lease.access_url = f'/my/leases/{lease.id}'

    # ------------------------------------------------------------
    # Onchange / constraints
    # ------------------------------------------------------------

    @api.onchange('unit_id')
    def _onchange_unit_id(self):
        if self.unit_id:
            self.rent_amount = self.unit_id.base_rent
            self.deposit_amount = self.unit_id.deposit_amount
            self.maintenance_charge = self.unit_id.maintenance_charge
            if self.unit_id.meter_number and self.state == 'draft' and self.electricity_billing == 'none':
                self.electricity_billing = 'metered'

    @api.onchange('start_date')
    def _onchange_start_date(self):
        if self.start_date:
            self.billing_day = min(self.start_date.day, 28)
            if not self.end_date:
                self.end_date = self.start_date + relativedelta(years=1, days=-1)

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for lease in self:
            if lease.start_date and lease.end_date and lease.end_date <= lease.start_date:
                raise ValidationError(self.env._("The end date of lease %s must be after its start date.", lease.display_name))

    @api.constrains('unit_id', 'start_date', 'end_date', 'state')
    def _check_overlap(self):
        for lease in self.filtered(lambda lease: lease.state in BLOCKING_STATES):
            overlapping = self.sudo().search([
                ('id', '!=', lease.id),
                ('unit_id', '=', lease.unit_id.id),
                ('state', 'in', BLOCKING_STATES),
                ('start_date', '<=', lease.end_date),
                ('end_date', '>=', lease.start_date),
            ], limit=1)
            if overlapping:
                raise ValidationError(self.env._(
                    "Unit %(unit)s is already leased from %(start)s to %(end)s (%(lease)s).",
                    unit=lease.unit_id.display_name, start=overlapping.start_date,
                    end=overlapping.end_date, lease=overlapping.name))

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == self.env._("New"):
                start = fields.Date.to_date(vals.get('start_date')) or fields.Date.context_today(self)
                vals['name'] = self.env['ir.sequence'].with_context(
                    ir_sequence_date=fields.Date.to_string(start)).next_by_code('rent.lease') or '/'
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_running(self):
        if any(lease.state not in ('draft', 'cancelled') for lease in self):
            raise UserError(self.env._("Only draft or cancelled leases can be deleted."))

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def action_confirm(self):
        for lease in self:
            if lease.state != 'draft':
                raise UserError(self.env._("Only draft leases can be confirmed."))
        self.write({'state': 'confirmed'})
        template = self.env.ref('rent_management.mail_template_lease_confirmation', raise_if_not_found=False)
        for lease in self:
            if template and lease.tenant_id.email:
                lease.message_post_with_source(
                    template, subtype_xmlid='mail.mt_comment', partner_ids=lease.tenant_id.ids)
        return True

    def action_activate(self):
        today = fields.Date.context_today(self)
        for lease in self:
            if lease.state != 'confirmed':
                raise UserError(self.env._("Only confirmed leases can be activated."))
            if lease.unit_id.under_maintenance:
                raise UserError(self.env._("Unit %s is under maintenance.", lease.unit_id.display_name))
            vals = {'state': 'active'}
            if not lease.next_invoice_date:
                vals['next_invoice_date'] = lease._get_first_invoice_date()
            if lease.escalation_percent and lease.escalation_every_months and not lease.next_escalation_date:
                vals['next_escalation_date'] = lease.start_date + relativedelta(months=lease.escalation_every_months)
            lease.write(vals)
            previous = lease.renewed_from_id
            if previous and previous.state in RUNNING_STATES + ('expired',):
                previous.state = 'renewed'
            lease.message_post(body=self.env._("Tenant moved in on %s.", max(today, lease.start_date)))
        return True

    def action_cancel(self):
        for lease in self:
            if lease.state not in ('draft', 'confirmed'):
                raise UserError(self.env._("Only draft or confirmed leases can be cancelled."))
        self.write({'state': 'cancelled'})
        return True

    def action_draft(self):
        self.filtered(lambda lease: lease.state == 'cancelled').write({'state': 'draft'})
        return True

    def action_generate_invoice(self):
        self.ensure_one()
        if self.state not in RUNNING_STATES:
            raise UserError(self.env._("Rent can only be invoiced on active leases."))
        invoice = self._create_rent_invoices()
        return self._action_open_moves(invoice)

    def action_create_deposit_invoice(self):
        self.ensure_one()
        if self.deposit_invoice_id and self.deposit_invoice_id.state != 'cancel':
            raise UserError(self.env._("A deposit invoice already exists for this lease."))
        if not self.deposit_amount:
            raise UserError(self.env._("Set a deposit amount first."))
        product = self.env.ref('rent_management.product_security_deposit')
        invoice = self.env['account.move'].create(self._prepare_invoice_vals(
            fields.Date.context_today(self), 'deposit', [Command.create({
                'product_id': product.id,
                'name': self.env._("Security deposit - %s", self.name),
                'quantity': 1,
                'price_unit': self.deposit_amount,
                'account_id': self._get_deposit_account().id,
                'tax_ids': [Command.clear()],
            })]))
        invoice.action_post()
        self.deposit_invoice_id = invoice
        return self._action_open_moves(invoice)

    def action_renew(self):
        self.ensure_one()
        if self.state not in RUNNING_STATES + ('expired',):
            raise UserError(self.env._("Only active, expiring or expired leases can be renewed."))
        start = self.end_date + timedelta(days=1)
        months = self.duration_months or 12
        renewal = self.copy({
            'start_date': start,
            'end_date': start + relativedelta(months=months, days=-1),
            'renewed_from_id': self.id,
            'deposit_amount': 0.0,
            'billing_day': self.billing_day,
        })
        self.message_post(body=self.env._("Renewal %s created.", renewal._get_html_link()))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'rent.lease',
            'res_id': renewal.id,
            'view_mode': 'form',
            'views': [[False, 'form']],
        }

    def action_open_moveout_wizard(self):
        self.ensure_one()
        if self.state not in RUNNING_STATES + ('expired',):
            raise UserError(self.env._("Only running or expired leases can be terminated."))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Move-out"),
            'res_model': 'rent.moveout.wizard',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {'default_lease_id': self.id},
        }

    def action_request_signature(self):
        """E-sign stub: plug a provider here (Odoo Sign, DocuSign, ...)."""
        self.ensure_one()
        _logger.info("E-sign requested for lease %s (no provider configured).", self.name)
        self.message_post(body=self.env._("Signature requested from %s.", self.tenant_id.name))
        return True

    def action_mark_signed(self):
        self.write({'signed': True})
        return True

    def action_view_invoices(self):
        self.ensure_one()
        return self._action_open_moves(self.invoice_ids)

    def action_view_maintenance(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('rent_management.rent_maintenance_request_action')
        action['domain'] = [('lease_id', '=', self.id)]
        action['context'] = {
            'default_lease_id': self.id,
            'default_unit_id': self.unit_id.id,
            'default_tenant_id': self.tenant_id.id,
        }
        return action

    def _action_open_moves(self, moves):
        action = self.env['ir.actions.act_window']._for_xml_id('rent_management.rent_invoice_action')
        if len(moves) == 1:
            action.update({'views': [[False, 'form']], 'res_id': moves.id, 'view_mode': 'form'})
        else:
            action['domain'] = [('id', 'in', moves.ids)]
        return action

    # ------------------------------------------------------------
    # Billing helpers
    # ------------------------------------------------------------

    def _get_first_invoice_date(self):
        self.ensure_one()
        first = self.start_date.replace(day=self.billing_day)
        if first < self.start_date:
            first += relativedelta(months=1)
        return first if first <= self.end_date else self.start_date

    def _get_next_invoice_date(self, current):
        self.ensure_one()
        months = FREQUENCY_MONTHS[self.billing_frequency]
        return current + relativedelta(months=months, day=self.billing_day)

    def _get_rent_journal(self):
        self.ensure_one()
        journal = self.company_id.rent_journal_id
        if not journal:
            journal = self.env['account.journal'].search([
                *self.env['account.journal']._check_company_domain(self.company_id),
                ('type', '=', 'sale'),
            ], limit=1)
        if not journal:
            raise UserError(self.env._("No sales journal found for company %s.", self.company_id.name))
        return journal

    def _get_deposit_account(self):
        self.ensure_one()
        account = self.company_id.rent_deposit_account_id
        if not account:
            raise UserError(self.env._(
                "Configure the Security Deposit Account in Rent Management > Configuration > Settings."))
        return account

    def _prepare_invoice_vals(self, due_date, invoice_type, line_commands, invoice_date=None):
        self.ensure_one()
        return {
            'move_type': 'out_invoice',
            'partner_id': self.tenant_id.id,
            'company_id': self.company_id.id,
            'journal_id': self._get_rent_journal().id,
            'invoice_date': invoice_date or min(fields.Date.context_today(self), due_date),
            'invoice_date_due': due_date,
            'invoice_origin': self.name,
            'rent_lease_id': self.id,
            'rent_invoice_type': invoice_type,
            'invoice_line_ids': line_commands,
        }

    def _prepare_rent_invoice_lines(self, period_start):
        self.ensure_one()
        months = FREQUENCY_MONTHS[self.billing_frequency]
        period_end = min(period_start + relativedelta(months=months, days=-1), self.end_date)
        period = self.env._("%(start)s to %(end)s", start=period_start, end=period_end)
        income_account = self.company_id.rent_income_account_id
        rent_product = self.env.ref('rent_management.product_rent')
        lines = [Command.create({
            'product_id': rent_product.id,
            'name': self.env._("Rent %(unit)s - %(period)s", unit=self.unit_id.display_name, period=period),
            'quantity': months,
            'price_unit': self.rent_amount,
            **({'account_id': income_account.id} if income_account else {}),
        })]
        if self.electricity_billing == 'fixed' and self.electricity_fixed_amount:
            lines.append(Command.create({
                'product_id': self.env.ref('rent_management.product_electricity').id,
                'name': self.env._("Electricity (fixed) - %s", period),
                'quantity': months,
                'price_unit': self.electricity_fixed_amount,
                'tax_ids': [Command.clear()],
            }))
        if self.maintenance_charge:
            product = self.company_id.rent_maintenance_product_id \
                or self.env.ref('rent_management.product_maintenance_charge')
            lines.append(Command.create({
                'product_id': product.id,
                'name': self.env._("Maintenance charge - %s", period),
                'quantity': months,
                'price_unit': self.maintenance_charge,
            }))
        return lines

    def _create_rent_invoices(self):
        """Invoice the next rent period of each lease, post it and move the billing date forward."""
        invoices = self.env['account.move']
        template = self.env.ref('rent_management.mail_template_rent_invoice', raise_if_not_found=False)
        for lease in self:
            due_date = lease.next_invoice_date or lease._get_first_invoice_date()
            if due_date > lease.end_date:
                raise UserError(self.env._("Lease %s is fully invoiced.", lease.name))
            # Confirmed meter readings are billed in arrears with the next rent invoice.
            readings = lease._get_readings_to_invoice()
            invoice = self.env['account.move'].create(lease._prepare_invoice_vals(
                due_date, 'rent', lease._prepare_rent_invoice_lines(due_date) + readings._prepare_invoice_lines()))
            invoice.action_post()
            readings._mark_invoiced(invoice)
            lease.next_invoice_date = lease._get_next_invoice_date(due_date)
            invoices |= invoice
            if template and lease.tenant_id.email:
                invoice.message_post_with_source(
                    template, subtype_xmlid='mail.mt_comment', partner_ids=invoice.partner_id.ids)
        return invoices

    def _get_readings_to_invoice(self):
        self.ensure_one()
        return self.electricity_reading_ids.filtered(lambda r: r.state == 'confirmed')

    def _get_last_meter_reading(self, before=None, exclude=None):
        """Last confirmed reading of the unit's meter (whatever the lease), else the opening reading."""
        self.ensure_one()
        domain = [
            ('unit_id', '=', self.unit_id.id),
            ('state', 'in', ('confirmed', 'invoiced')),
        ]
        if before:
            domain.append(('period_start', '<', before))
        if exclude:
            domain.append(('id', 'not in', exclude.ids))
        last = self.env['rent.electricity.reading'].sudo().search(domain, order='period_end desc, id desc', limit=1)
        return last.current_reading if last else self.electricity_opening_reading

    def _get_last_reading_end(self):
        self.ensure_one()
        readings = self.electricity_reading_ids.filtered(lambda r: r.state != 'cancelled')
        return max(readings.mapped('period_end')) if readings else None

    def action_view_electricity(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('rent_management.rent_electricity_reading_action')
        action['domain'] = [('lease_id', '=', self.id)]
        action['context'] = {'default_lease_id': self.id, 'search_default_open': 0}
        return action

    def _get_unpaid_invoices(self):
        return self.invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
            and m.payment_state in ('not_paid', 'partial'))

    def _create_deposit_credit_note(self, date):
        """Return the security deposit: debit the deposit liability, credit the tenant receivable."""
        self.ensure_one()
        product = self.env.ref('rent_management.product_security_deposit')
        vals = self._prepare_invoice_vals(date, 'deposit_refund', [Command.create({
            'product_id': product.id,
            'name': self.env._("Security deposit refund - %s", self.name),
            'quantity': 1,
            'price_unit': self.deposit_amount,
            'account_id': self._get_deposit_account().id,
            'tax_ids': [Command.clear()],
        })], invoice_date=date)
        vals.update(move_type='out_refund', reversed_entry_id=self.deposit_invoice_id.id)
        vals.pop('invoice_date_due')
        credit_note = self.env['account.move'].create(vals)
        credit_note.action_post()
        return credit_note

    def _reconcile_with_open_invoices(self, credit_note):
        """Use the deposit credit note to pay the open invoices of the lease, oldest first."""
        self.ensure_one()
        for invoice in self._get_unpaid_invoices().sorted('invoice_date_due'):
            credit_line = credit_note.line_ids.filtered(
                lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled)
            if not credit_line:
                break
            debit_line = invoice.line_ids.filtered(
                lambda line: line.account_id == credit_line.account_id and not line.reconciled)
            (credit_line + debit_line).reconcile()

    # ------------------------------------------------------------
    # Integrations (stubs)
    # ------------------------------------------------------------

    @api.model
    def _send_whatsapp_message(self, partner, body):
        """Send a WhatsApp/SMS message to ``partner``.

        Stub: it only logs. Override to call a provider (Twilio, Meta Cloud API, ...).
        """
        _logger.info("WhatsApp to %s (%s): %s", partner.display_name, partner.phone or "no phone", body)
        return True

    # ------------------------------------------------------------
    # Crons
    # ------------------------------------------------------------

    @api.model
    def _cron_generate_invoices(self):
        today = fields.Date.context_today(self)
        for company in self.env['res.company'].search([]):
            limit_date = today + timedelta(days=company.rent_invoice_advance_days)
            leases = self.search([
                ('company_id', '=', company.id),
                ('state', 'in', RUNNING_STATES),
                ('next_invoice_date', '<=', limit_date),
            ])
            for lease in leases:
                try:
                    with self.env.cr.savepoint():
                        # Catch up on every missed period, but never invoice beyond the lease end.
                        while lease.next_invoice_date and lease.next_invoice_date <= min(limit_date, lease.end_date):
                            lease._create_rent_invoices()
                except UserError as error:
                    _logger.warning("Rent invoice not generated for lease %s: %s", lease.name, error)

    @api.model
    def _cron_send_reminders(self):
        today = fields.Date.context_today(self)
        Move = self.env['account.move']
        reminder = self.env.ref('rent_management.mail_template_payment_reminder', raise_if_not_found=False)
        overdue_template = self.env.ref('rent_management.mail_template_overdue_notice', raise_if_not_found=False)
        unpaid = Domain('rent_lease_id', '!=', False) & Domain('state', '=', 'posted') \
            & Domain('move_type', '=', 'out_invoice') & Domain('payment_state', 'in', ('not_paid', 'partial'))
        for company in self.env['res.company'].search([]):
            company_unpaid = unpaid & Domain('company_id', '=', company.id)
            upcoming = Move.search(company_unpaid & Domain('rent_reminder_sent', '=', False) & Domain(
                'invoice_date_due', '<=', today + timedelta(days=company.rent_reminder_days_before)) & Domain(
                'invoice_date_due', '>=', today))
            for invoice in upcoming:
                if reminder:
                    invoice.message_post_with_source(
                        reminder, subtype_xmlid='mail.mt_comment', partner_ids=invoice.partner_id.ids)
                self._send_whatsapp_message(invoice.partner_id, self.env._(
                    "Reminder: rent invoice %(name)s is due on %(date)s.",
                    name=invoice.name, date=invoice.invoice_date_due))
            upcoming.rent_reminder_sent = True
            if not company.rent_send_overdue_notice:
                continue
            overdue = Move.search(company_unpaid & Domain('rent_overdue_notice_sent', '=', False)
                                  & Domain('invoice_date_due', '<', today))
            for invoice in overdue:
                if overdue_template:
                    invoice.message_post_with_source(
                        overdue_template, subtype_xmlid='mail.mt_comment', partner_ids=invoice.partner_id.ids)
                self._send_whatsapp_message(invoice.partner_id, self.env._(
                    "Rent invoice %s is overdue. Please pay it as soon as possible.", invoice.name))
            overdue.rent_overdue_notice_sent = True

    @api.model
    def _cron_apply_late_fees(self):
        today = fields.Date.context_today(self)
        invoices = self.env['account.move'].search([
            ('rent_lease_id', '!=', False),
            ('rent_invoice_type', '=', 'rent'),
            ('rent_late_fee_applied', '=', False),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('invoice_date_due', '<', today),
        ])
        for invoice in invoices:
            lease = invoice.rent_lease_id
            if not lease.late_fee_value or invoice.invoice_date_due + timedelta(days=lease.grace_days) >= today:
                continue
            lease._create_late_fee_invoice(invoice)

    def _create_late_fee_invoice(self, invoice):
        self.ensure_one()
        if self.late_fee_type == 'percent':
            amount = invoice.amount_residual * self.late_fee_value / 100.0
        else:
            amount = self.late_fee_value
        amount = self.currency_id.round(amount)
        if self.currency_id.is_zero(amount):
            return self.env['account.move']
        product = self.company_id.rent_late_fee_product_id or self.env.ref('rent_management.product_late_fee')
        today = fields.Date.context_today(self)
        fee_invoice = self.env['account.move'].create(self._prepare_invoice_vals(today, 'late_fee', [Command.create({
            'product_id': product.id,
            'name': self.env._("Late fee on %s", invoice.name),
            'quantity': 1,
            'price_unit': amount,
        })]))
        fee_invoice.action_post()
        invoice.write({'rent_late_fee_applied': True, 'rent_late_fee_invoice_id': fee_invoice.id})
        self.message_post(body=self.env._(
            "Late fee %(fee)s charged for overdue invoice %(invoice)s.",
            fee=fee_invoice._get_html_link(), invoice=invoice._get_html_link()))
        return fee_invoice

    @api.model
    def _cron_lease_expiry(self):
        today = fields.Date.context_today(self)
        template = self.env.ref('rent_management.mail_template_lease_expiry', raise_if_not_found=False)
        for company in self.env['res.company'].search([]):
            expiring = self.search([
                ('company_id', '=', company.id),
                ('state', '=', 'active'),
                ('end_date', '>=', today),
                ('end_date', '<=', today + timedelta(days=company.rent_expiry_notice_days)),
            ])
            expiring.state = 'expiring'
            for lease in expiring:
                lease.activity_schedule(
                    'mail.mail_activity_data_todo',
                    date_deadline=lease.end_date - timedelta(days=min(lease.notice_period_days, 15)),
                    summary=self.env._("Lease ending: renew or plan move-out"),
                    user_id=(lease.manager_id or self.env.user).id,
                )
                if template and lease.tenant_id.email:
                    lease.message_post_with_source(
                        template, subtype_xmlid='mail.mt_comment', partner_ids=lease.tenant_id.ids)
                self._send_whatsapp_message(lease.tenant_id, self.env._(
                    "Your lease %(name)s ends on %(date)s.", name=lease.name, date=lease.end_date))

    @api.model
    def _cron_expire_leases(self):
        today = fields.Date.context_today(self)
        ended = self.search([('state', 'in', RUNNING_STATES), ('end_date', '<', today)])
        renewed = ended.filtered(lambda lease: lease.renewal_ids.filtered(lambda r: r.state in BLOCKING_STATES))
        renewed.state = 'renewed'
        (ended - renewed).state = 'expired'

    @api.model
    def _cron_prepare_electricity_readings(self):
        """Create the meter readings to enter for the month just ended, and ask the managers to fill them."""
        today = fields.Date.context_today(self)
        period_end = today.replace(day=1) - timedelta(days=1)
        month_start = period_end.replace(day=1)
        leases = self.search([
            ('electricity_billing', '=', 'metered'),
            ('state', 'in', RUNNING_STATES),
            ('start_date', '<=', period_end),
        ])
        Reading = self.env['rent.electricity.reading']
        existing = Reading.search([
            ('lease_id', 'in', leases.ids),
            ('state', '!=', 'cancelled'),
            ('period_end', '>=', month_start),
        ]).lease_id
        vals_list = []
        for lease in leases - existing:
            # Start right after the last reading so that a missed month is never skipped:
            # the meter is cumulative, one reading then covers the whole gap.
            last_end = lease._get_last_reading_end()
            start = last_end + timedelta(days=1) if last_end else max(month_start, lease.start_date)
            if start > period_end:
                continue
            vals_list.append({'lease_id': lease.id, 'period_start': start, 'period_end': period_end, 'reading_date': today})
        readings = Reading.create(vals_list)
        for reading in readings:
            reading.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=today + timedelta(days=3),
                summary=self.env._("Enter the electricity meter reading"),
                user_id=(reading.lease_id.manager_id or self.env.user).id,
            )
        return readings

    @api.model
    def _cron_apply_escalation(self):
        today = fields.Date.context_today(self)
        leases = self.search([
            ('state', 'in', RUNNING_STATES),
            ('escalation_percent', '>', 0),
            ('escalation_every_months', '>', 0),
            ('next_escalation_date', '<=', today),
        ])
        for lease in leases:
            old_rent = lease.rent_amount
            new_rent = lease.currency_id.round(old_rent * (1 + lease.escalation_percent / 100.0))
            lease.write({
                'rent_amount': new_rent,
                'next_escalation_date': lease.next_escalation_date + relativedelta(months=lease.escalation_every_months),
            })
            lease.message_post(body=self.env._(
                "Rent escalated by %(percent)s%% from %(old)s to %(new)s.",
                percent=lease.escalation_percent, old=old_rent, new=new_rent))
