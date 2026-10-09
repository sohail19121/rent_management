from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_tenant = fields.Boolean(string="Tenant")
    is_owner = fields.Boolean(string="Property Owner")
    kyc_id_type = fields.Selection([
        ('aadhaar', "Aadhaar"),
        ('pan', "PAN"),
        ('passport', "Passport"),
        ('other', "Other"),
    ], string="ID Type", groups='rent_management.group_rent_user')
    kyc_id_number = fields.Char(string="ID Number", groups='rent_management.group_rent_user')
    kyc_verified = fields.Boolean(string="KYC Verified", groups='rent_management.group_rent_user')
    kyc_document_ids = fields.Many2many(
        'ir.attachment', 'rent_partner_kyc_attachment_rel', 'partner_id', 'attachment_id',
        string="KYC Documents", groups='rent_management.group_rent_user')
    emergency_contact_name = fields.Char()
    emergency_contact_phone = fields.Char()
    lease_ids = fields.One2many(
        'rent.lease', 'tenant_id', string="Leases", groups='rent_management.group_rent_user')
    lease_count = fields.Integer(compute='_compute_lease_count', groups='rent_management.group_rent_user')
    rent_total_due = fields.Monetary(
        string="Rent Due", compute='_compute_rent_total_due', groups='rent_management.group_rent_user',
        help="Amount still to pay on posted rent invoices.")

    @api.depends('lease_ids')
    def _compute_lease_count(self):
        counts = dict(self.env['rent.lease']._read_group(
            [('tenant_id', 'in', self.ids)], ['tenant_id'], ['__count']))
        for partner in self:
            partner.lease_count = counts.get(partner, 0)

    def _compute_rent_total_due(self):
        dues = dict(self.env['account.move'].sudo()._read_group(
            [
                ('partner_id', 'in', self.ids),
                ('rent_lease_id', '!=', False),
                ('state', '=', 'posted'),
                ('move_type', '=', 'out_invoice'),
                ('payment_state', 'in', ('not_paid', 'partial')),
            ],
            ['partner_id'], ['amount_residual_signed:sum'],
        ))
        for partner in self:
            partner.rent_total_due = dues.get(partner, 0.0)

    def action_view_leases(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('rent_management.rent_lease_action')
        action['domain'] = [('tenant_id', '=', self.id)]
        action['context'] = {'default_tenant_id': self.id}
        return action
