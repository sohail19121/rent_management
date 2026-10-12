import base64

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

    # ------------------------------------------------------------
    # Modern invoice PDF
    # ------------------------------------------------------------

    @staticmethod
    def _rent_tint(hex_color, ratio):
        """Mix a #rrggbb color with white (the PDF engine has no color-mix)."""
        hex_color = (hex_color or '#714B67').lstrip('#')
        if len(hex_color) != 6:
            hex_color = '714B67'
        rgb = [int(hex_color[i:i + 2], 16) for i in (0, 2, 4)]
        return '#%02x%02x%02x' % tuple(round(255 - (255 - c) * ratio) for c in rgb)

    def _rent_report_values(self):
        """Values of the modern invoice PDF: status, payments, colors and the pay-online QR code."""
        self.ensure_one()
        move = self.sudo()
        today = fields.Date.context_today(self)
        is_refund = move.move_type == 'out_refund'
        paid = move.currency_id.is_zero(move.amount_residual)
        if is_refund:
            status, label = 'refund', self.env._("Credit note")
        elif paid:
            status, label = 'paid', self.env._("Paid")
        elif move.invoice_date_due and move.invoice_date_due < today:
            status, label = 'overdue', self.env._("Overdue")
        elif move.payment_state == 'partial':
            status, label = 'partial', self.env._("Partly paid")
        else:
            status, label = 'due', self.env._("Due")
        brand = move.company_id.primary_color or '#714B67'
        qr = False
        if status in ('due', 'overdue', 'partial'):
            url = f"{move.get_base_url()}{move.get_portal_url()}"
            png = self.env['rent.unit']._make_qr_png(url)
            qr = 'data:image/png;base64,' + base64.b64encode(png).decode()
        hex_brand = (brand or '#714B67').lstrip('#')
        if len(hex_brand) != 6:
            hex_brand = '714B67'
        r, g, b = (int(hex_brand[i:i + 2], 16) / 255 for i in (0, 2, 4))
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        paid_amount = move.amount_total - move.amount_residual
        return {
            'status': status,
            'status_label': label,
            # Text on the brand color: white on dark brands, ink on light ones.
            'brand_text': '#ffffff' if luminance < 0.62 else '#1f1d24',
            'brand_faint': self._rent_tint(brand, 0.04),
            'paid_amount': paid_amount,
            'paid_pct': round(100.0 * paid_amount / move.amount_total) if move.amount_total else 0,
            'is_refund': is_refund,
            'paid': paid,
            'days': (move.invoice_date_due - today).days if move.invoice_date_due else 0,
            'payments': (move.invoice_payments_widget or {}).get('content', []),
            'lines': move.invoice_line_ids.filtered(lambda line: line.display_type in ('product', 'line_section', 'line_note')),
            'brand': brand,
            'brand_soft': self._rent_tint(brand, 0.1),
            'brand_mid': self._rent_tint(brand, 0.22),
            'pay_qr': qr,
            'lease': move.rent_lease_id,
        }

