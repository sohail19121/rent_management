from dateutil.relativedelta import relativedelta

from odoo import fields, models

RUNNING_STATES = ('active', 'expiring')
FREQUENCY_MONTHS = {'monthly': 1, 'quarterly': 3, 'yearly': 12}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _rent_portal_leases(self):
        """Leases of this tenant shown on the portal, the running ones first."""
        self.ensure_one()
        leases = self.env['rent.lease'].sudo().search([
            ('tenant_id', 'child_of', self.commercial_partner_id.id),
            ('state', '!=', 'draft'),
        ], order='start_date desc')
        order = {'active': 0, 'expiring': 0, 'confirmed': 1}
        return leases.sorted(lambda lease: (order.get(lease.state, 2), -lease.start_date.toordinal()))

    def _rent_portal_profile(self):
        """Profile summary of the account details page: completeness checklist and tenant facts."""
        self.ensure_one()
        _ = self.env._
        partner = self.sudo()
        tenant = partner.commercial_partner_id
        leases = self._rent_portal_leases()
        checks = [
            {'label': _("Name and email"), 'done': bool(partner.name and partner.email), 'icon': 'badge'},
            {'label': _("Phone number"), 'done': bool(partner.phone), 'icon': 'phone'},
            {'label': _("Full address"), 'icon': 'location_on',
             'done': bool(partner.street and partner.city and partner.zip and partner.country_id)},
            {'label': _("Profile photo"), 'done': bool(partner.image_1920), 'icon': 'photo_camera'},
            {'label': _("ID verified"), 'done': tenant.kyc_verified, 'icon': 'verified',
             'hint': _("Checked by your property manager")},
            {'label': _("Emergency contact"), 'done': bool(tenant.emergency_contact_phone), 'icon': 'emergency',
             'hint': _("Ask your property manager to add it")},
        ]
        done = sum(check['done'] for check in checks)
        return {
            'checks': checks,
            'done': done,
            'pct': round(100 * done / len(checks)),
            'tenant_since': min(leases.mapped('start_date'), default=False),
            'kyc_type': dict(tenant._fields['kyc_id_type']._description_selection(self.env)).get(tenant.kyc_id_type),
            'kyc_verified': tenant.kyc_verified,
            'emergency_name': tenant.emergency_contact_name,
            'emergency_phone': tenant.emergency_contact_phone,
        }

    def _rent_portal_dashboard(self, lease_id=None):
        """Everything the tenant dashboard shows, for this portal partner.

        Records are read with sudo but always restricted to the tenant's own leases and invoices;
        the caller must pass the partner of the logged-in user.
        """
        self.ensure_one()
        _ = self.env._
        partner = self.commercial_partner_id.sudo()
        today = fields.Date.context_today(self)
        leases = self._rent_portal_leases()
        lease = leases.filtered(lambda lease: lease.id == lease_id)[:1] or leases[:1]
        running = lease.state in RUNNING_STATES

        invoices = self.env['account.move'].sudo().search([
            ('partner_id', 'child_of', partner.id),
            ('rent_lease_id', 'in', leases.ids),
            ('state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
        ], order='invoice_date desc, id desc')
        unpaid = invoices.filtered(
            lambda m: m.move_type == 'out_invoice' and m.payment_state in ('not_paid', 'partial'))
        overdue = unpaid.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < today)
        oldest_unpaid = unpaid.sorted(lambda m: m.invoice_date_due or today)[:1]
        payments = self.env['rent.property'].sudo()._dashboard_payments(
            invoices.filtered(lambda m: m.move_type == 'out_invoice'))
        paid_this_year = sum(p['amount'] for p in payments if p['date'].year == today.year)

        # Next payment: the next unpaid invoice of this lease, else an estimate of the next rent invoice.
        next_invoice = unpaid.filtered(lambda m: m.rent_lease_id == lease).sorted('invoice_date_due')[:1]
        next_payment = False
        if next_invoice:
            next_payment = {'date': next_invoice.invoice_date_due, 'amount': next_invoice.amount_residual,
                            'estimate': False, 'invoice': next_invoice}
        elif running and lease.next_invoice_date and lease.next_invoice_date <= lease.end_date:
            months = FREQUENCY_MONTHS[lease.billing_frequency]
            fixed_electricity = lease.electricity_fixed_amount if lease.electricity_billing == 'fixed' else 0.0
            next_payment = {
                'date': lease.next_invoice_date,
                'amount': months * (lease.rent_amount + lease.maintenance_charge + fixed_electricity),
                'estimate': True,
                'invoice': False,
            }

        readings = lease.electricity_reading_ids.filtered(lambda r: r.state in ('confirmed', 'invoiced')) \
            .sorted('period_start')
        chart_readings = readings[-6:]
        max_kwh = max(chart_readings.mapped('consumption') or [0]) or 1

        requests = self.env['rent.maintenance.request'].sudo().search(
            [('tenant_id', 'child_of', partner.id)], order='create_date desc')
        open_requests = requests.filtered(lambda r: r.state in ('new', 'in_progress'))

        lease_days = (lease.end_date - lease.start_date).days if lease else 0
        elapsed = min(max((today - lease.start_date).days, 0), lease_days) if lease else 0

        alerts = []
        if overdue:
            alerts.append({
                'level': 'danger', 'icon': 'warning',
                'title': _("Payment overdue"),
                'text': _("%(count)s invoice(s) past due. Please pay to avoid late fees.", count=len(overdue)),
                'amount': sum(overdue.mapped('amount_residual')),
                'url': overdue.sorted('invoice_date_due')[0].get_portal_url(), 'cta': _("Pay now"),
            })
        if lease.state == 'expiring' or (running and 0 <= (lease.end_date - today).days <= 60):
            alerts.append({
                'level': 'warning', 'icon': 'event_upcoming',
                'title': _("Your lease ends soon"),
                'text': _("Lease %(name)s ends on %(date)s. Contact your property manager to renew.",
                          name=lease.name, date=lease.end_date),
                'url': False, 'cta': False,
            })
        if lease.deposit_amount and lease.deposit_status == 'pending' and lease.deposit_invoice_id.state == 'posted':
            alerts.append({
                'level': 'info', 'icon': 'account_balance',
                'title': _("Security deposit pending"),
                'text': _("Your security deposit has not been received yet."),
                'url': lease.deposit_invoice_id.get_portal_url(), 'cta': _("Pay deposit"),
            })

        # Payment trend: money received per month over the last 6 months.
        months = [today.replace(day=1) - relativedelta(months=offset) for offset in range(5, -1, -1)]
        paid_by_month = dict.fromkeys(months, 0.0)
        for payment in payments:
            month = payment['date'].replace(day=1)
            if month in paid_by_month:
                paid_by_month[month] += payment['amount']
        trend_values = [paid_by_month[month] for month in months]
        # The current month has only just started: compare the last two complete months.
        trend_delta = None
        if trend_values[-3]:
            trend_delta = round(100.0 * (trend_values[-2] - trend_values[-3]) / trend_values[-3], 1)
        trend_delta_label = self.env._("%(month)s vs %(previous)s",
                                       month=months[-2].strftime('%b'), previous=months[-3].strftime('%b'))

        # Invoice status, for the donut: paid / to pay / overdue.
        customer_invoices = invoices.filtered(lambda m: m.move_type == 'out_invoice')
        status_counts = {
            'paid': len(customer_invoices - unpaid),
            'to_pay': len(unpaid - overdue),
            'overdue': len(overdue),
        }
        total_invoices = sum(status_counts.values())

        id_number = partner.kyc_id_number or ''
        return {
            'trend': self._rent_portal_trend_chart(months, trend_values, partner.currency_id or self.env.company.currency_id),
            'trend_delta': trend_delta,
            'trend_delta_label': trend_delta_label,
            'status_counts': status_counts,
            'total_invoices': total_invoices,
            'paid_pct': round(100.0 * status_counts['paid'] / total_invoices) if total_invoices else 0,
            'donut': self._rent_portal_donut(status_counts),
            'unpaid_count': len(unpaid),
            'reading_count': len(readings),
            'partner': partner,
            'user_partner': self.sudo(),
            'leases': leases,
            'lease': lease,
            'running': running,
            'unit': lease.unit_id,
            'property': lease.property_id,
            'manager': lease.manager_id.partner_id,
            'currency': lease.currency_id or self.env.company.currency_id,
            'amount_due': sum(unpaid.mapped('amount_residual')),
            'overdue_amount': sum(overdue.mapped('amount_residual')),
            'pay_invoice': oldest_unpaid,
            'next_payment': next_payment,
            'paid_this_year': paid_this_year,
            'invoices': invoices[:6],
            'invoice_count': len(invoices),
            'payments': sorted(payments, key=lambda p: p['date'], reverse=True)[:5],
            'readings': readings.sorted('period_start', reverse=True)[:6],
            'chart_readings': chart_readings,
            'max_kwh': max_kwh,
            'last_reading': readings[-1:],
            'requests': (open_requests | requests)[:5],
            'open_request_count': len(open_requests),
            'lease_progress': round(100.0 * elapsed / lease_days) if lease_days else 0,
            'days_left': (lease.end_date - today).days if lease else 0,
            'months_left': relativedelta(lease.end_date, today).months + 12 * relativedelta(lease.end_date, today).years
            if lease and lease.end_date > today else 0,
            'alerts': alerts,
            'kyc_id_type': dict(partner._fields['kyc_id_type']._description_selection(self.env)).get(partner.kyc_id_type, ''),
            'kyc_id_masked': ('•' * max(len(id_number) - 4, 0) + id_number[-4:]) if id_number else '',
            'today': today,
        }

    def _rent_portal_trend_chart(self, months, values, currency):
        """Geometry of the 6-month payment trend (an SVG drawn by the portal template)."""
        width, height, left, bottom, top = 600, 210, 46, 176, 16
        top_value = max(values) or 1
        # Round the axis maximum up to a "nice" number so the gridlines read well.
        magnitude = 10 ** (len(str(int(top_value))) - 1)
        axis_max = next(step * magnitude for step in (1, 2, 2.5, 5, 10) if step * magnitude >= top_value)
        step_x = (width - left - 16) / (len(values) - 1)

        def y(value):
            return bottom - (bottom - top) * value / axis_max

        def compact(value):
            symbol = currency.symbol or ''
            if value >= 1_000_000:
                return f"{symbol}{value / 1_000_000:.1f}M".replace('.0M', 'M')
            if value >= 1000:
                return f"{symbol}{value / 1000:.1f}k".replace('.0k', 'k')
            return f"{symbol}{value:.0f}"

        points = [{
            'x': round(left + i * step_x, 1),
            'y': round(y(value), 1),
            'label': month.strftime('%b'),
            'title': f"{month.strftime('%B %Y')}: {currency.format(value)}",
            'value': compact(value),
        } for i, (month, value) in enumerate(zip(months, values))]
        line = ' '.join(f"{'L' if i else 'M'}{p['x']},{p['y']}" for i, p in enumerate(points))
        return {
            'width': width,
            'height': height,
            'points': points,
            'line': line,
            'area': f"{line} L{points[-1]['x']},{bottom} L{points[0]['x']},{bottom} Z",
            'gridlines': [{'y': round(y(axis_max * f), 1), 'label': compact(axis_max * f)} for f in (0, 0.5, 1)],
            'bottom': bottom,
            'left': left,
            'has_data': any(values),
        }

    def _rent_portal_donut(self, counts):
        """Stroke segments of the invoice-status donut, with a 2px gap between segments."""
        radius = 40
        circumference = 2 * 3.14159265 * radius
        total = sum(counts.values())
        segments = []
        offset = 0.0
        for key in ('paid', 'to_pay', 'overdue'):
            if not counts[key]:
                continue
            length = circumference * counts[key] / total
            gap = 2.5 if len([v for v in counts.values() if v]) > 1 else 0
            segments.append({
                'key': key,
                'dash': f"{max(length - gap, 0.1):.2f} {circumference:.2f}",
                'offset': f"{-offset:.2f}",
            })
            offset += length
        return {'radius': radius, 'segments': segments}



class RentLease(models.Model):
    _inherit = 'rent.lease'

    def _rent_portal_lease_values(self):
        """What the tenant lease pages show about one lease (read with sudo by the caller)."""
        self.ensure_one()
        _ = self.env._
        today = fields.Date.context_today(self)
        total_days = max((self.end_date - self.start_date).days, 1)
        elapsed = min(max((today - self.start_date).days, 0), total_days)

        events = [(self.start_date, _("Move-in"), _("Your lease starts"), 'home')]
        if self.escalation_percent and self.escalation_every_months:
            step = self.start_date + relativedelta(months=self.escalation_every_months)
            while step < self.end_date:
                events.append((step, _("Rent increase"), _("+%s%% on the monthly rent", self.escalation_percent), 'arrow_upward'))
                step += relativedelta(months=self.escalation_every_months)
        if self.notice_period_days and self.state in ('active', 'expiring', 'confirmed'):
            notice = self.end_date - relativedelta(days=self.notice_period_days)
            if notice > self.start_date:
                events.append((notice, _("Notice period starts"), _("Tell us if you renew or move out"), 'notifications'))
        if self.moveout_date:
            events.append((self.moveout_date, _("Moved out"), _("Deposit settled"), 'logout'))
        else:
            events.append((self.end_date, _("Lease ends"), _("End of the current term"), 'event_upcoming'))
        for renewal in self.renewal_ids.filtered(lambda r: r.state != 'cancelled'):
            events.append((renewal.start_date, _("Renewal"), renewal.name, 'autorenew'))
        events.sort(key=lambda event: event[0])
        timeline, next_marked = [], False
        for date, title, text, icon in events:
            state = 'done' if date <= today else 'upcoming'
            if state == 'upcoming' and not next_marked:
                state, next_marked = 'next', True
            timeline.append({'date': date, 'title': title, 'text': text, 'icon': icon, 'state': state})

        invoices = self.invoice_ids.filtered(lambda m: m.state == 'posted').sorted(
            lambda m: (m.invoice_date or today, m.id), reverse=True)
        unpaid = invoices.filtered(
            lambda m: m.move_type == 'out_invoice' and m.payment_state in ('not_paid', 'partial'))
        readings = self.electricity_reading_ids.filtered(lambda r: r.state in ('confirmed', 'invoiced')).sorted('period_start')
        return {
            'progress': round(100.0 * elapsed / total_days),
            'days_left': max((self.end_date - today).days, 0),
            'months_total': self.duration_months,
            'timeline': timeline,
            'lease_invoices': invoices,
            'lease_unpaid': sum(unpaid.mapped('amount_residual')),
            'lease_pay_invoice': unpaid.sorted(lambda m: m.invoice_date_due or today)[:1],
            'last_reading': readings[-1:],
            'monthly_total': self.rent_amount + self.maintenance_charge
            + (self.electricity_fixed_amount if self.electricity_billing == 'fixed' else 0.0),
        }

    def _rent_agreement_values(self):
        """Values of the lease agreement PDF: brand colors, parties, escalation schedule, key dates."""
        self.ensure_one()
        lease = self.sudo()
        company = lease.company_id
        Move = self.env['account.move']
        brand = company.primary_color or '#714B67'
        invoice_like = Move._rent_tint
        hex_brand = brand.lstrip('#') if len(brand.lstrip('#')) == 6 else '714B67'
        r, g, b = (int(hex_brand[i:i + 2], 16) / 255 for i in (0, 2, 4))
        tenant = lease.tenant_id
        id_number = tenant.kyc_id_number or ''

        # Rent per period when the rent increases every N months.
        schedule = []
        if lease.escalation_percent and lease.escalation_every_months:
            # The current rent already includes the increases applied so far: go back to the original rent.
            applied = 0
            if lease.next_escalation_date:
                delta = relativedelta(lease.next_escalation_date, lease.start_date)
                applied = max(round((delta.years * 12 + delta.months) / lease.escalation_every_months) - 1, 0)
            rent = lease.rent_amount / (1 + lease.escalation_percent / 100.0) ** applied
            start = lease.start_date
            while start <= lease.end_date and len(schedule) < 12:
                end = min(start + relativedelta(months=lease.escalation_every_months, days=-1), lease.end_date)
                if schedule and (end - start).days < 28:
                    break  # a few days left at the very end of the lease: not a rent period of its own
                schedule.append({'start': start, 'end': end, 'rent': lease.currency_id.round(rent)})
                start = end + relativedelta(days=1)
                rent = rent * (1 + lease.escalation_percent / 100.0)

        portal = lease._rent_portal_lease_values()
        return {
            'brand': brand,
            'brand_text': '#ffffff' if (0.2126 * r + 0.7152 * g + 0.0722 * b) < 0.62 else '#1f1d24',
            'brand_soft': invoice_like(brand, 0.1),
            'brand_mid': invoice_like(brand, 0.22),
            'brand_faint': invoice_like(brand, 0.04),
            'landlord': lease.property_id.owner_id or company.partner_id,
            'tenant': tenant,
            'manager': lease.manager_id.partner_id,
            'id_type': dict(tenant._fields['kyc_id_type']._description_selection(self.env)).get(tenant.kyc_id_type, ''),
            'id_masked': ('•' * max(len(id_number) - 4, 0) + id_number[-4:]) if id_number else '',
            'kyc_verified': tenant.kyc_verified,
            'schedule': schedule,
            'timeline': portal['timeline'],
            'monthly_total': portal['monthly_total'],
            'deposit_months': round(lease.deposit_amount / lease.rent_amount, 1) if lease.rent_amount else 0,
            'kind': dict(lease.property_id._fields['property_type']._description_selection(self.env)).get(
                lease.property_id.property_type, ''),
            'today': fields.Date.context_today(self),
        }
