from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rent_income_account_id = fields.Many2one(related='company_id.rent_income_account_id', readonly=False)
    rent_deposit_account_id = fields.Many2one(related='company_id.rent_deposit_account_id', readonly=False)
    rent_journal_id = fields.Many2one(related='company_id.rent_journal_id', readonly=False)
    rent_late_fee_product_id = fields.Many2one(related='company_id.rent_late_fee_product_id', readonly=False)
    rent_maintenance_product_id = fields.Many2one(related='company_id.rent_maintenance_product_id', readonly=False)
    rent_invoice_advance_days = fields.Integer(related='company_id.rent_invoice_advance_days', readonly=False)
    rent_reminder_days_before = fields.Integer(related='company_id.rent_reminder_days_before', readonly=False)
    rent_send_overdue_notice = fields.Boolean(related='company_id.rent_send_overdue_notice', readonly=False)
    rent_electricity_rate = fields.Float(related='company_id.rent_electricity_rate', readonly=False)
    rent_expiry_notice_days = fields.Integer(related='company_id.rent_expiry_notice_days', readonly=False)
