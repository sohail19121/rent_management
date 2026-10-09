from odoo import Command, api, fields, models
from odoo.exceptions import UserError


class RentMaintenanceRequest(models.Model):
    _name = 'rent.maintenance.request'
    _description = "Maintenance Request"
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, create_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string="Reference", readonly=True, copy=False, default=lambda self: self.env._("New"))
    unit_id = fields.Many2one('rent.unit', string="Unit", required=True, index=True, tracking=True, check_company=True)
    property_id = fields.Many2one(related='unit_id.property_id', store=True, string="Property")
    lease_id = fields.Many2one(
        'rent.lease', string="Lease", index=True, check_company=True,
        compute='_compute_lease_id', store=True, readonly=False)
    tenant_id = fields.Many2one(
        'res.partner', string="Tenant", index=True, compute='_compute_tenant_id', store=True, readonly=False)
    company_id = fields.Many2one(related='unit_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    category = fields.Selection([
        ('plumbing', "Plumbing"),
        ('electrical', "Electrical"),
        ('cleaning', "Cleaning"),
        ('appliance', "Appliance"),
        ('other', "Other"),
    ], required=True, default='other', tracking=True)
    priority = fields.Selection([
        ('0', "Low"),
        ('1', "Normal"),
        ('2', "High"),
        ('3', "Urgent"),
    ], default='1')
    description = fields.Html()
    image_ids = fields.Many2many(
        'ir.attachment', 'rent_maintenance_attachment_rel', 'request_id', 'attachment_id', string="Photos")
    assigned_to = fields.Many2one('res.users', string="Assigned To", tracking=True, domain="[('share', '=', False)]")
    vendor_id = fields.Many2one('res.partner', string="Vendor")
    cost = fields.Monetary(tracking=True)
    charge_to = fields.Selection([('owner', "Owner"), ('tenant', "Tenant")], default='owner', required=True)
    invoice_id = fields.Many2one('account.move', string="Tenant Invoice", readonly=True, copy=False)
    state = fields.Selection([
        ('new', "New"),
        ('in_progress', "In Progress"),
        ('done', "Done"),
        ('cancelled', "Cancelled"),
    ], default='new', required=True, tracking=True, string="Status", group_expand=True)
    kanban_state_color = fields.Integer(compute='_compute_kanban_state_color')

    @api.depends('unit_id')
    def _compute_lease_id(self):
        for request in self:
            if request.unit_id and request.lease_id.unit_id != request.unit_id:
                request.lease_id = request.unit_id.current_lease_id

    @api.depends('lease_id')
    def _compute_tenant_id(self):
        for request in self:
            if request.lease_id:
                request.tenant_id = request.lease_id.tenant_id

    @api.depends('priority')
    def _compute_kanban_state_color(self):
        for request in self:
            request.kanban_state_color = {'2': 2, '3': 1}.get(request.priority, 0)

    def _compute_access_url(self):
        super()._compute_access_url()
        for request in self:
            request.access_url = f'/my/maintenance/{request.id}'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == self.env._("New"):
                vals['name'] = self.env['ir.sequence'].next_by_code('rent.maintenance.request') or '/'
        requests = super().create(vals_list)
        for request in requests.filtered('assigned_to'):
            request.activity_schedule(
                'mail.mail_activity_data_todo', user_id=request.assigned_to.id,
                summary=self.env._("Maintenance: %s", request.name))
        return requests

    def action_start(self):
        self.write({'state': 'in_progress'})
        return True

    def action_done(self):
        for request in self:
            if request.state in ('done', 'cancelled'):
                raise UserError(self.env._("Request %s is already closed.", request.name))
        self.write({'state': 'done'})
        self.filtered(lambda r: r.charge_to == 'tenant' and r.cost and not r.invoice_id)._create_tenant_invoice()
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    def action_reset(self):
        self.write({'state': 'new'})
        return True

    def _create_tenant_invoice(self):
        """Recharge the cost of the repair to the tenant.

        Runs with sudo: closing a request is a manager action while invoicing
        belongs to accounting; the invoice content is fully derived from the request.
        """
        for request in self:
            if not request.tenant_id:
                raise UserError(self.env._("Set the tenant to charge on request %s.", request.name))
            lease = request.lease_id.sudo()
            product = request.company_id.rent_maintenance_product_id \
                or self.env.ref('rent_management.product_maintenance_charge')
            line = Command.create({
                'product_id': product.id,
                'name': self.env._("Repair %(ref)s (%(category)s)", ref=request.name,
                                   category=dict(request._fields['category'].selection)[request.category]),
                'quantity': 1,
                'price_unit': request.cost,
            })
            today = fields.Date.context_today(self)
            if lease:
                vals = lease._prepare_invoice_vals(today, 'maintenance', [line])
            else:
                vals = {
                    'move_type': 'out_invoice',
                    'partner_id': request.tenant_id.id,
                    'company_id': request.company_id.id,
                    'invoice_date': today,
                    'invoice_origin': request.name,
                    'rent_invoice_type': 'maintenance',
                    'invoice_line_ids': [line],
                }
            invoice = self.env['account.move'].sudo().create(vals)
            invoice.action_post()
            request.invoice_id = invoice
            request.message_post(body=self.env._("Tenant charged with %s.", invoice._get_html_link()))
