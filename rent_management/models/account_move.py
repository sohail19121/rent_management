from odoo import fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    rent_lease_id = fields.Many2one(
        'rent.lease', string="Lease", index='btree_not_null', copy=False, readonly=True, ondelete='restrict')
    rent_property_id = fields.Many2one(
        related='rent_lease_id.property_id', store=True, string="Rented Property")
    rent_invoice_type = fields.Selection([
        ('rent', "Rent"),
        ('deposit', "Security Deposit"),
        ('deposit_refund', "Deposit Refund"),
        ('late_fee', "Late Fee"),
        ('maintenance', "Maintenance"),
        ('damage', "Damage Charges"),
        ('electricity', "Electricity"),
    ], copy=False, readonly=True)
    rent_late_fee_applied = fields.Boolean(copy=False, readonly=True)
    rent_late_fee_invoice_id = fields.Many2one('account.move', string="Late Fee Invoice", copy=False, readonly=True)
    rent_reminder_sent = fields.Boolean(copy=False, readonly=True)
    rent_overdue_notice_sent = fields.Boolean(copy=False, readonly=True)

    def unlink(self):
        self._rent_release()
        return super().unlink()

    def button_cancel(self):
        res = super().button_cancel()
        self._rent_release()
        return res

    def button_draft(self):
        if any(move.state == 'cancel' and move.rent_lease_id and move.rent_invoice_type in ('rent', 'electricity')
               for move in self):
            # Cancelling released its meter readings and billing period: re-posting it could bill them twice.
            raise UserError(self.env._(
                "A cancelled lease invoice cannot be reset to draft. Generate a new one from the lease instead."))
        return super().button_draft()

    def _rent_release(self):
        """Undo what generating these lease invoices did, when they are cancelled or deleted:
        their meter readings become billable again, and the lease billing date moves back
        if they were the latest rent invoice."""
        moves = self.filtered('rent_lease_id')
        if not moves:
            return
        readings = self.env['rent.electricity.reading'].sudo().search([('invoice_id', 'in', moves.ids)])
        for reading in readings:
            reading.message_post(body=self.env._(
                "Invoice %s was cancelled or deleted: the reading will be billed again.", reading.invoice_id.name))
        readings.write({'state': 'confirmed', 'invoice_id': False})
        for move in moves.filtered(lambda m: m.rent_invoice_type == 'rent' and m.invoice_date_due):
            lease = move.rent_lease_id.sudo()
            period = move.invoice_date_due
            if lease.next_invoice_date and lease._get_next_invoice_date(period) == lease.next_invoice_date:
                lease.next_invoice_date = period
                lease.message_post(body=self.env._(
                    "Rent invoice %(invoice)s was cancelled or deleted: the period starting %(date)s will be invoiced again.",
                    invoice=move.name, date=period))
