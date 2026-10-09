from odoo import api, fields, models


class RentProperty(models.Model):
    _name = 'rent.property'
    _description = "Rental Property"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(readonly=True, copy=False, default=lambda self: self.env._("New"))
    property_type = fields.Selection([
        ('residential', "Residential"),
        ('commercial', "Commercial"),
        ('mixed', "Mixed Use"),
    ], required=True, default='residential', tracking=True)
    owner_id = fields.Many2one('res.partner', string="Owner", tracking=True, domain="[('is_owner', '=', True)]")
    manager_id = fields.Many2one(
        'res.users', string="Property Manager", tracking=True, default=lambda self: self.env.user,
        domain="[('share', '=', False)]")
    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one('res.country.state', string="State", domain="[('country_id', '=?', country_id)]")
    zip = fields.Char()
    country_id = fields.Many2one('res.country', string="Country")
    image = fields.Image(max_width=1024, max_height=1024)
    amenity_ids = fields.Many2many('rent.amenity', string="Amenities")
    unit_ids = fields.One2many('rent.unit', 'property_id', string="Units")
    lease_ids = fields.One2many('rent.lease', 'property_id', string="Leases")
    unit_count = fields.Integer(compute='_compute_occupancy', string="Unit Count")
    occupied_count = fields.Integer(compute='_compute_occupancy', string="Occupied")
    vacant_count = fields.Integer(compute='_compute_occupancy', string="Vacant")
    occupancy_rate = fields.Float(compute='_compute_occupancy', string="Occupancy (%)")
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    active = fields.Boolean(default=True)
    notes = fields.Html()

    _code_company_uniq = models.Constraint('UNIQUE (code, company_id)', "The property code must be unique per company.")

    @api.depends('unit_ids.state')
    def _compute_occupancy(self):
        for prop in self:
            units = prop.unit_ids
            prop.unit_count = len(units)
            prop.occupied_count = len(units.filtered(lambda u: u.state == 'occupied'))
            prop.vacant_count = len(units.filtered(lambda u: u.state == 'vacant'))
            prop.occupancy_rate = prop.unit_count and 100.0 * prop.occupied_count / prop.unit_count

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code') or vals['code'] == self.env._("New"):
                vals['code'] = self.env['ir.sequence'].next_by_code('rent.property') or '/'
        return super().create(vals_list)

    def action_view_units(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('rent_management.rent_unit_action')
        action['domain'] = [('property_id', '=', self.id)]
        action['context'] = {'default_property_id': self.id}
        return action

    def action_view_leases(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('rent_management.rent_lease_action')
        action['domain'] = [('property_id', '=', self.id)]
        action['context'] = {'search_default_running': 1}
        return action
