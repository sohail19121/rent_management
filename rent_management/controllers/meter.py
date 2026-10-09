from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.tools import BinaryBytes

MAX_PHOTO_SIZE = 10 * 1024 * 1024


class RentMeterController(http.Controller):

    def _parse_float(self, value):
        try:
            return float((value or '').replace(',', '.'))
        except ValueError:
            return None

    @http.route('/rent/meter/<string:token>', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def meter_reading(self, token, **post):
        """Page opened by scanning the QR label of a meter with a phone: enter the reading on the spot."""
        values = {'error': None, 'saved_reading': None, 'post': post}
        if not request.env.user.has_group('rent_management.group_rent_user'):
            return request.render('rent_management.meter_reading_page', {**values, 'unit': None, 'forbidden': True})
        # Read with the user's own rights: managers only reach the meters of their properties.
        unit = request.env['rent.unit'].search([('meter_qr_token', '=', token)], limit=1)
        if not unit:
            return request.render('rent_management.meter_reading_page', {**values, 'unit': None, 'forbidden': False})

        if request.httprequest.method == 'POST':
            current = self._parse_float(post.get('current_reading'))
            rate = self._parse_float(post.get('rate'))
            photo = request.httprequest.files.get('photo')
            photo_data = None
            if photo and photo.filename:
                content = photo.read(MAX_PHOTO_SIZE + 1)
                if len(content) > MAX_PHOTO_SIZE or not (photo.mimetype or '').startswith('image/'):
                    values['error'] = request.env._("The photo must be an image of 10 MB at most.")
                else:
                    photo_data = BinaryBytes(content)
            if current is None or rate is None:
                values['error'] = request.env._("Enter the current reading and the rate as numbers.")
            if not values['error']:
                try:
                    with request.env.cr.savepoint():
                        values['saved_reading'] = unit._save_meter_reading(
                            current, rate, apply_rate_to_lease=bool(post.get('apply_rate')), photo=photo_data)
                    values['post'] = {}
                except (UserError, ValidationError) as error:
                    values['error'] = error.args[0]

        values.update(unit=unit, entry=unit._get_meter_entry(), forbidden=False)
        return request.render('rent_management.meter_reading_page', values)
