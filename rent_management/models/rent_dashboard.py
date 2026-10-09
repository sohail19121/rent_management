from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.fields import Domain

PERIODS = ('this_month', 'last_month', 'this_quarter', 'this_year', 'last_12_months')
PERIOD_MONTHS = {'this_month': 1, 'last_month': 1, 'this_quarter': 3, 'this_year': 12, 'last_12_months': 12}
INCOME_TYPES = ('out_invoice', 'out_refund')
DEPOSIT_TYPES = ('deposit', 'deposit_refund')


class RentProperty(models.Model):
    _inherit = 'rent.property'

    # ------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------

    @api.model
    def _rent_window_action(self, name, model, domain, views='list,form', res_id=False):
        action = {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'domain': domain,
            'views': [[False, view] for view in views.split(',')],
        }
        if res_id:
            action.update(res_id=res_id, views=[[False, 'form']])
        return action

    @api.model
    def _dashboard_period(self, period):
        today = fields.Date.context_today(self)
        if period == 'last_month':
            start = today.replace(day=1) - relativedelta(months=1)
            return start, today.replace(day=1) - timedelta(days=1)
        if period == 'this_quarter':
            start = today.replace(day=1, month=3 * ((today.month - 1) // 3) + 1)
            return start, start + relativedelta(months=3, days=-1)
        if period == 'this_year':
            return today.replace(month=1, day=1), today.replace(month=12, day=31)
        if period == 'last_12_months':
            start = today.replace(day=1) - relativedelta(months=11)
            return start, today
        start = today.replace(day=1)
        return start, start + relativedelta(months=1, days=-1)

    @api.model
    def get_dashboard_data(self, period='this_month', property_id=False):
        """Everything the owner dashboard shows, limited to the records the user may read.

        Accounting figures are read with sudo, restricted to the invoices of those leases, so a
        property manager sees the money of their properties without needing accounting rights.
        """
        period = period if period in PERIODS else 'this_month'
        date_from, date_to = self._dashboard_period(period)
        # The previous period of the same length, for the deltas ("vs last month").
        prev_from, prev_to = date_from - relativedelta(months=PERIOD_MONTHS[period]), date_from - timedelta(days=1)
        today = fields.Date.context_today(self)
        can_bill = self.env.user.has_group('rent_management.group_rent_accountant')

        properties = self.search([('id', '=', property_id)] if property_id else [])
        prop_domain = Domain('property_id', 'in', properties.ids)
        units = self.env['rent.unit'].search(prop_domain)
        leases = self.env['rent.lease'].search(prop_domain)
        running = leases.filtered(lambda lease: lease.state in ('active', 'expiring'))
        Move = self.env['account.move'].sudo()
        lease_moves = Domain('rent_lease_id', 'in', leases.ids) & Domain('state', '=', 'posted')
        income_moves = Move.search(
            lease_moves & Domain('move_type', 'in', INCOME_TYPES) & Domain('rent_invoice_type', 'not in', DEPOSIT_TYPES))
        open_invoices = Move.search(
            lease_moves & Domain('move_type', '=', 'out_invoice')
            & Domain('payment_state', 'in', ('not_paid', 'partial')))
        # Deposits are a liability, not income: they are reported under "Deposits Held" only.
        payments = self._dashboard_payments(income_moves.filtered(lambda m: m.move_type == 'out_invoice'))

        in_period = lambda date: date and date_from <= date <= date_to  # noqa: E731
        period_moves = income_moves.filtered(lambda m: in_period(m.invoice_date))
        period_payments = [p for p in payments if in_period(p['date'])]
        billed = sum(period_moves.mapped('amount_total_signed'))
        collected = sum(p['amount'] for p in period_payments)
        in_previous = lambda date: date and prev_from <= date <= prev_to  # noqa: E731
        prev_billed = sum(income_moves.filtered(lambda m: in_previous(m.invoice_date)).mapped('amount_total_signed'))
        prev_collected = sum(p['amount'] for p in payments if in_previous(p['date']))
        monthly = self._dashboard_monthly(income_moves, payments, units, today)
        overdue = open_invoices.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < today)
        expiring_domain = prop_domain & Domain('state', 'in', ('active', 'expiring')) \
            & Domain('end_date', '>=', today) & Domain('end_date', '<=', today + timedelta(days=60))
        Reading = self.env['rent.electricity.reading']
        Maintenance = self.env['rent.maintenance.request']
        open_maintenance_domain = prop_domain & Domain('state', 'in', ('new', 'in_progress'))
        billed_kwh = sum(Reading.sudo().search([('invoice_id', 'in', period_moves.ids)]).mapped('consumption'))
        electricity_lines = period_moves.invoice_line_ids.filtered(
            lambda line: line.product_id == self.env.ref('rent_management.product_electricity'))

        _ = self.env._
        act = self._rent_window_action
        invoice_act = act if can_bill else (lambda *args, **kwargs: False)
        occupied = units.filtered(lambda u: u.state == 'occupied')
        vacant = units.filtered(lambda u: u.state == 'vacant')

        def kpi(key, label, value, icon, action=False, fmt='int', variant='primary', hint='',
                placement='tile', previous=None, trend=None, up_is_good=True):
            """placement: 'hero' (the one headline figure), 'highlight' (large tile) or 'tile' (compact).
            previous: value of the previous period, for the delta. trend: last 12 months."""
            return {'key': key, 'label': label, 'value': value, 'icon': icon, 'action': action,
                    'format': fmt, 'variant': variant, 'hint': hint, 'placement': placement,
                    'previous': previous, 'trend': trend, 'up_is_good': up_is_good}

        sections = [
            {'title': _("Portfolio"), 'kpis': [
                kpi('properties', _("Properties"), len(properties), 'business',
                    act(_("Properties"), 'rent.property', [('id', 'in', properties.ids)], 'kanban,list,form')),
                kpi('units', _("Units"), len(units), 'home',
                    act(_("Units"), 'rent.unit', [('id', 'in', units.ids)], 'kanban,list,form'),
                    hint=_("%(occupied)s occupied, %(vacant)s vacant", occupied=len(occupied), vacant=len(vacant))),
                kpi('occupancy', _("Occupancy"), round(100.0 * len(occupied) / len(units), 1) if units else 0.0,
                    'pie_chart', act(_("Occupied Units"), 'rent.unit', [('id', 'in', occupied.ids)], 'kanban,list,form'),
                    fmt='percent', variant='success', placement='highlight',
                    hint=_("%(occupied)s of %(units)s units occupied", occupied=len(occupied), units=len(units))),
                kpi('vacant', _("Vacant Units"), len(vacant), 'key',
                    act(_("Vacant Units"), 'rent.unit', [('id', 'in', vacant.ids)], 'kanban,list,form'),
                    variant='warning' if vacant else 'success'),
                kpi('rent_roll', _("Monthly Rent Roll"), sum(running.mapped('rent_amount')), 'payments',
                    act(_("Running Leases"), 'rent.lease', [('id', 'in', running.ids)]), fmt='monetary',
                    hint=_("%s running leases", len(running))),
                kpi('deposits', _("Deposits Held"),
                    sum(leases.filtered(lambda lease: lease.deposit_status == 'received').mapped('deposit_amount')),
                    'account_balance', act(_("Leases with Deposit Received"), 'rent.lease',
                                           [('id', 'in', leases.ids), ('deposit_status', '=', 'received')]),
                    fmt='monetary'),
            ]},
            {'title': _("Money"), 'kpis': [
                kpi('billed', _("Billed"), billed, 'receipt_long',
                    invoice_act(_("Invoices of the Period"), 'account.move', [('id', 'in', period_moves.ids)]),
                    fmt='monetary', hint=_("Deposits excluded"), placement='highlight',
                    previous=prev_billed, trend=monthly['billed']),
                kpi('collected', _("Collected"), collected, 'payments',
                    invoice_act(_("Paid Invoices"), 'account.move',
                                [('id', 'in', list({p['invoice_id'] for p in period_payments}))]),
                    fmt='monetary', variant='success', hint=_("Payments received"), placement='hero',
                    previous=prev_collected, trend=monthly['collected']),
                kpi('collection_rate', _("Collection Rate"), round(100.0 * collected / billed, 1) if billed else 0.0,
                    'pie_chart', False, fmt='percent', placement='hero_meter',
                    variant='success' if not billed or collected >= billed * 0.9 else 'warning'),
                kpi('outstanding', _("Outstanding"), sum(open_invoices.mapped('amount_residual_signed')), 'schedule',
                    invoice_act(_("Unpaid Invoices"), 'account.move', [('id', 'in', open_invoices.ids)]),
                    fmt='monetary', variant='warning', placement='highlight', up_is_good=False,
                    hint=_("%s unpaid invoices", len(open_invoices))),
                kpi('overdue', _("Overdue"), sum(overdue.mapped('amount_residual_signed')), 'warning',
                    invoice_act(_("Overdue Invoices"), 'account.move', [('id', 'in', overdue.ids)]),
                    fmt='monetary', variant='danger' if overdue else 'success',
                    hint=_("%s invoices past due", len(overdue)), placement='highlight', up_is_good=False),
                kpi('electricity', _("Electricity Billed"), sum(electricity_lines.mapped('price_subtotal')), 'flash_on',
                    act(_("Electricity Readings"), 'rent.electricity.reading',
                        [('property_id', 'in', properties.ids), ('state', '=', 'invoiced')], 'list,form,pivot'),
                    fmt='monetary', hint=_("%s kWh metered", round(billed_kwh))),
            ]},
            {'title': _("Operations"), 'kpis': [
                kpi('expiring', _("Leases Ending in 60 Days"), self.env['rent.lease'].search_count(expiring_domain),
                    'event_upcoming', act(_("Leases Ending Soon"), 'rent.lease', list(expiring_domain)),
                    variant='warning'),
                kpi('draft_leases', _("Leases to Confirm"), len(leases.filtered(lambda lease: lease.state == 'draft')),
                    'contract', act(_("Draft Leases"), 'rent.lease', [('id', 'in', leases.ids), ('state', '=', 'draft')])),
                kpi('maintenance', _("Open Maintenance"), Maintenance.search_count(open_maintenance_domain), 'build',
                    act(_("Open Maintenance Requests"), 'rent.maintenance.request', list(open_maintenance_domain),
                        'kanban,list,form'), variant='warning'),
                kpi('readings_to_enter', _("Meter Readings to Enter"),
                    Reading.search_count(prop_domain & Domain('state', '=', 'draft')), 'flash_on',
                    act(_("Meter Readings to Enter"), 'rent.electricity.reading',
                        [('property_id', 'in', properties.ids), ('state', '=', 'draft')]), variant='warning'),
                kpi('readings_to_bill', _("Readings to Invoice"),
                    Reading.search_count(prop_domain & Domain('state', '=', 'confirmed')), 'receipt_long',
                    act(_("Meter Readings to Invoice"), 'rent.electricity.reading',
                        [('property_id', 'in', properties.ids), ('state', '=', 'confirmed')])),
            ]},
        ]

        return {
            'currency_id': self.env.company.currency_id.id,
            'can_bill': can_bill,
            'period': {'key': period, 'date_from': date_from, 'date_to': date_to,
                       'prev_from': prev_from, 'prev_to': prev_to},
            'billed': billed,
            'properties': [{'id': p.id, 'name': p.name} for p in self.search([])],
            'property_id': property_id or False,
            'sections': sections,
            'monthly': monthly,
            'income_mix': self._dashboard_income_mix(period_moves),
            'property_rows': self._dashboard_property_rows(properties, units, running, period_moves,
                                                           period_payments, open_invoices, open_maintenance_domain),
            'overdue_tenants': self._dashboard_overdue_tenants(overdue, today, can_bill),
            'expiring_leases': [{
                'id': lease.id, 'name': lease.name, 'tenant': lease.tenant_id.name, 'unit': lease.unit_id.display_name,
                'end_date': lease.end_date, 'days_left': (lease.end_date - today).days,
                'renewal': bool(lease.renewal_ids.filtered(lambda r: r.state != 'cancelled')),
            } for lease in self.env['rent.lease'].search(expiring_domain, order='end_date', limit=8)],
            'recent_payments': sorted(payments, key=lambda p: p['date'], reverse=True)[:8] if can_bill else [],
            'maintenance': [{
                'id': request.id, 'name': request.name, 'unit': request.unit_id.display_name,
                'category': dict(request._fields['category']._description_selection(self.env))[request.category],
                'priority': int(request.priority or 0), 'assigned': request.assigned_to.name or '',
                'age': (today - request.create_date.date()).days, 'state': request.state,
            } for request in Maintenance.search(open_maintenance_domain, order='priority desc, create_date', limit=8)],
            'readings_to_enter': [{
                'id': reading.id, 'unit': reading.unit_id.display_name, 'tenant': reading.tenant_id.name,
                'period': reading.name, 'previous': reading.previous_reading,
            } for reading in Reading.search(prop_domain & Domain('state', '=', 'draft'), order='period_start', limit=8)],
        }

    @api.model
    def _dashboard_payments(self, invoices):
        """Money actually received on these invoices: reconciliations with payments or bank lines.

        Deposits offset against invoices at move-out are not cash and are left out.
        """
        receivable = invoices.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable')
        result = []
        for partial in receivable.matched_credit_ids:
            source = partial.credit_move_id.move_id
            if not (source.origin_payment_id or source.statement_line_id):
                continue
            invoice = partial.debit_move_id.move_id
            result.append({
                'date': partial.max_date,
                'amount': partial.amount,
                'invoice_id': invoice.id,
                'invoice': invoice.name,
                'tenant': invoice.partner_id.name,
                'lease': invoice.rent_lease_id.name,
            })
        return result

    @api.model
    def _dashboard_monthly(self, income_moves, payments, units, today):
        """Last 12 months: billed vs collected, and electricity consumption."""
        months = [today.replace(day=1) - relativedelta(months=offset) for offset in range(11, -1, -1)]
        billed, collected = defaultdict(float), defaultdict(float)
        for move in income_moves:
            if move.invoice_date:
                billed[move.invoice_date.replace(day=1)] += move.amount_total_signed
        for payment in payments:
            collected[payment['date'].replace(day=1)] += payment['amount']
        kwh = defaultdict(float)
        readings = self.env['rent.electricity.reading'].search([
            ('unit_id', 'in', units.ids),
            ('state', 'in', ('confirmed', 'invoiced')),
            ('period_start', '>=', months[0]),
        ])
        for reading in readings:
            kwh[reading.period_start.replace(day=1)] += reading.consumption
        return {
            'labels': [month.strftime('%b %Y') for month in months],
            'billed': [round(billed[month], 2) for month in months],
            'collected': [round(collected[month], 2) for month in months],
            'kwh': [round(kwh[month], 2) for month in months],
        }

    @api.model
    def _dashboard_income_mix(self, period_moves):
        products = {
            self.env.ref('rent_management.product_rent'): self.env._("Rent"),
            self.env.ref('rent_management.product_electricity'): self.env._("Electricity"),
            self.env.ref('rent_management.product_maintenance_charge'): self.env._("Maintenance"),
            self.env.ref('rent_management.product_late_fee'): self.env._("Late Fees"),
        }
        totals = defaultdict(float)
        for line in period_moves.invoice_line_ids.filtered(lambda line: line.display_type == 'product'):
            label = products.get(line.product_id) or self.env._("Other")
            totals[label] -= line.balance  # income lines are credits
        order = [*products.values(), self.env._("Other")]
        return [{'label': label, 'value': round(totals[label], 2)} for label in order if totals.get(label)]

    @api.model
    def _dashboard_property_rows(self, properties, units, running, period_moves, period_payments, open_invoices,
                                 open_maintenance_domain):
        maintenance_counts = dict(self.env['rent.maintenance.request']._read_group(
            open_maintenance_domain, ['property_id'], ['__count']))
        move_property = {move.id: move.rent_property_id for move in period_moves | open_invoices}
        collected = defaultdict(float)
        for payment in period_payments:
            prop = move_property.get(payment['invoice_id']) \
                or self.env['account.move'].sudo().browse(payment['invoice_id']).rent_property_id
            collected[prop] += payment['amount']
        rows = []
        for prop in properties:
            prop_units = units.filtered(lambda u, p=prop: u.property_id == p)
            occupied = len(prop_units.filtered(lambda u: u.state == 'occupied'))
            rows.append({
                'id': prop.id,
                'name': prop.name,
                'city': prop.city or '',
                'units': len(prop_units),
                'occupied': occupied,
                'occupancy': round(100.0 * occupied / len(prop_units), 1) if prop_units else 0.0,
                'rent_roll': sum(running.filtered(lambda lease, p=prop: lease.property_id == p).mapped('rent_amount')),
                'billed': sum(period_moves.filtered(lambda m, p=prop: m.rent_property_id == p).mapped('amount_total_signed')),
                'collected': collected[prop],
                'outstanding': sum(open_invoices.filtered(lambda m, p=prop: m.rent_property_id == p)
                                   .mapped('amount_residual_signed')),
                'maintenance': maintenance_counts.get(prop, 0),
            })
        return sorted(rows, key=lambda row: row['rent_roll'], reverse=True)

    @api.model
    def _dashboard_overdue_tenants(self, overdue, today, can_bill):
        by_tenant = defaultdict(lambda: {'amount': 0.0, 'oldest': None, 'count': 0, 'invoice_ids': [], 'leases': set()})
        for invoice in overdue:
            row = by_tenant[invoice.partner_id]
            row['amount'] += invoice.amount_residual_signed
            row['count'] += 1
            row['invoice_ids'].append(invoice.id)
            row['leases'].add(invoice.rent_lease_id.name)
            if not row['oldest'] or invoice.invoice_date_due < row['oldest']:
                row['oldest'] = invoice.invoice_date_due
        rows = [{
            'partner_id': partner.id,
            'tenant': partner.name,
            'phone': partner.phone or '',
            'leases': ', '.join(sorted(row['leases'])),
            'amount': row['amount'],
            'count': row['count'],
            'days': (today - row['oldest']).days,
            'action': self._rent_window_action(
                self.env._("Overdue Invoices of %s", partner.name), 'account.move',
                [('id', 'in', row['invoice_ids'])]) if can_bill else False,
        } for partner, row in by_tenant.items()]
        return sorted(rows, key=lambda row: row['amount'], reverse=True)[:8]
