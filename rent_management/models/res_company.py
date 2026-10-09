from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    rent_income_account_id = fields.Many2one(
        'account.account', string="Rent Income Account",
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        help="Income account used on rent invoice lines. Defaults to the product income account.")
    rent_deposit_account_id = fields.Many2one(
        'account.account', string="Security Deposit Account",
        domain="[('account_type', 'in', ('liability_current', 'liability_non_current'))]",
        help="Liability account on which security deposits are collected and refunded.")
    rent_journal_id = fields.Many2one(
        'account.journal', string="Rent Journal", domain="[('type', '=', 'sale')]",
        help="Sales journal used for rent invoices. Defaults to the first sales journal.")
    rent_late_fee_product_id = fields.Many2one('product.product', string="Late Fee Product")
    rent_maintenance_product_id = fields.Many2one('product.product', string="Maintenance Charge Product")
    rent_invoice_advance_days = fields.Integer(
        string="Invoice Days in Advance", default=5,
        help="Rent invoices are generated this many days before the billing date (their due date).")
    rent_reminder_days_before = fields.Integer(
        string="Reminder Days Before Due", default=3,
        help="A payment reminder is emailed this many days before the due date of a rent invoice.")
    rent_send_overdue_notice = fields.Boolean(string="Send Overdue Notices", default=True)
    rent_electricity_rate = fields.Float(
        string="Electricity Rate per kWh", default=8.0, digits=(16, 4),
        help="Default electricity rate of new metered leases.")
    rent_expiry_notice_days = fields.Integer(string="Lease Expiry Notice (days)", default=30)
