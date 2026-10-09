from datetime import timedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError


class RentMoveoutWizard(models.TransientModel):
    _name = 'rent.moveout.wizard'
    _description = "Lease Move-out"

    lease_id = fields.Many2one('rent.lease', required=True, readonly=True)
    currency_id = fields.Many2one(related='lease_id.currency_id')
    tenant_id = fields.Many2one(related='lease_id.tenant_id')
    deposit_amount = fields.Monetary(related='lease_id.deposit_amount')
    moveout_date = fields.Date(required=True, default=fields.Date.context_today)
    damage_charges = fields.Monetary()
    unpaid_dues = fields.Monetary(compute='_compute_unpaid_dues')
    electricity_billing = fields.Selection(related='lease_id.electricity_billing')
    previous_meter_reading = fields.Float(compute='_compute_previous_meter_reading', digits=(16, 2))
    final_meter_reading = fields.Float(digits=(16, 2), help="Meter reading on the move-out day.")
    electricity_charges = fields.Monetary(
        compute='_compute_electricity_charges',
        help="Confirmed readings not invoiced yet, plus the consumption since the last reading.")
    deduction_note = fields.Text()
    refund_amount = fields.Monetary(compute='_compute_refund_amount')

    @api.depends('lease_id')
    def _compute_unpaid_dues(self):
        for wizard in self:
            wizard.unpaid_dues = sum(wizard.lease_id.sudo()._get_unpaid_invoices().mapped('amount_residual_signed'))

    @api.depends('lease_id')
    def _compute_previous_meter_reading(self):
        for wizard in self:
            wizard.previous_meter_reading = wizard.lease_id.sudo()._get_last_meter_reading() \
                if wizard.electricity_billing == 'metered' else 0.0

    @api.depends('lease_id', 'final_meter_reading', 'previous_meter_reading')
    def _compute_electricity_charges(self):
        for wizard in self:
            lease = wizard.lease_id.sudo()
            if lease.electricity_billing != 'metered':
                wizard.electricity_charges = 0.0
                continue
            pending = sum(lease._get_readings_to_invoice().mapped('amount'))
            if wizard.final_meter_reading > wizard.previous_meter_reading:
                consumption = wizard.final_meter_reading - wizard.previous_meter_reading
                pending += consumption * lease.electricity_rate
            wizard.electricity_charges = wizard.currency_id.round(pending) if wizard.currency_id else pending

    @api.depends('deposit_amount', 'damage_charges', 'unpaid_dues', 'electricity_charges')
    def _compute_refund_amount(self):
        for wizard in self:
            wizard.refund_amount = max(
                wizard.deposit_amount - wizard.damage_charges - wizard.unpaid_dues - wizard.electricity_charges, 0.0)

    def _invoice_final_electricity(self):
        """Record the move-out meter reading and invoice every electricity reading not billed yet."""
        lease = self.lease_id.sudo()
        if lease.electricity_billing != 'metered':
            return self.env['account.move']
        if self.final_meter_reading and self.final_meter_reading < self.previous_meter_reading:
            raise UserError(self.env._(
                "The final meter reading cannot be lower than the last reading (%s).", self.previous_meter_reading))
        lease.electricity_reading_ids.filtered(lambda r: r.state == 'draft').action_cancel()
        if self.final_meter_reading > self.previous_meter_reading:
            last_end = lease._get_last_reading_end()
            start = last_end + timedelta(days=1) if last_end else lease.start_date
            final = self.env['rent.electricity.reading'].sudo().create({
                'lease_id': lease.id,
                'period_start': min(start, self.moveout_date),
                'period_end': self.moveout_date,
                'reading_date': self.moveout_date,
                'previous_reading': self.previous_meter_reading,
                'current_reading': self.final_meter_reading,
                'fixed_charge': 0.0,
            })
            final.action_confirm()
        readings = lease._get_readings_to_invoice()
        if not readings:
            return self.env['account.move']
        invoice = self.env['account.move'].sudo().create(lease._prepare_invoice_vals(
            self.moveout_date, 'electricity', readings._prepare_invoice_lines(), invoice_date=self.moveout_date))
        invoice.action_post()
        readings._mark_invoiced(invoice)
        return invoice

    def action_confirm(self):
        self.ensure_one()
        lease = self.lease_id
        if self.damage_charges < 0:
            raise UserError(self.env._("Damage charges cannot be negative."))
        lease_sudo = lease.sudo()
        # Freeze the settlement figures before the final invoices change the open balance.
        unpaid_dues, electricity_charges, refund_amount = self.unpaid_dues, self.electricity_charges, self.refund_amount
        self._invoice_final_electricity()
        damage_invoice = self.env['account.move']
        if not self.currency_id.is_zero(self.damage_charges):
            product = lease.company_id.rent_maintenance_product_id \
                or self.env.ref('rent_management.product_maintenance_charge')
            damage_invoice = self.env['account.move'].sudo().create(lease_sudo._prepare_invoice_vals(
                self.moveout_date, 'damage', [Command.create({
                    'product_id': product.id,
                    'name': self.deduction_note or self.env._("Damage charges at move-out"),
                    'quantity': 1,
                    'price_unit': self.damage_charges,
                })], invoice_date=self.moveout_date))
            damage_invoice.action_post()

        credit_note = self.env['account.move']
        if lease.deposit_invoice_id.state == 'posted' and not self.currency_id.is_zero(self.deposit_amount):
            credit_note = lease_sudo._create_deposit_credit_note(self.moveout_date)
            # Offset the deposit against what the tenant still owes; the remainder is the refund to pay.
            lease_sudo._reconcile_with_open_invoices(credit_note)

        lease.write({
            'state': 'terminated',
            'moveout_date': self.moveout_date,
            'moveout_damage_charges': self.damage_charges,
            'moveout_unpaid_dues': unpaid_dues,
            'moveout_electricity_charges': electricity_charges,
            'moveout_deduction_note': self.deduction_note,
            'deposit_refunded_amount': refund_amount,
            'deposit_refund_id': credit_note.id,
            'deposit_settled': True,
        })
        template = self.env.ref('rent_management.mail_template_moveout_settlement', raise_if_not_found=False)
        if template and lease.tenant_id.email:
            lease.message_post_with_source(template, subtype_xmlid='mail.mt_comment', partner_ids=lease.tenant_id.ids)
        lease.message_post(body=self.env._(
            "Tenant moved out on %(date)s. Deposit refund: %(amount)s.",
            date=self.moveout_date, amount=refund_amount))
        if credit_note:
            return lease._action_open_moves(credit_note)
        return {'type': 'ir.actions.act_window_close'}
