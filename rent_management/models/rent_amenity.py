from odoo import fields, models


class RentAmenity(models.Model):
    _name = 'rent.amenity'
    _description = "Property Amenity"
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    icon = fields.Char(help="Odoo UI icon name, e.g. 'wifi' or 'local_parking'.")
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('UNIQUE (name)', "An amenity with this name already exists.")
