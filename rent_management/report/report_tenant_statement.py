from odoo import api, models


class ReportTenantStatement(models.AbstractModel):
    _name = 'report.rent_management.report_tenant_statement'
    _description = "Tenant Statement Report"

    def _get_statement_lines(self, partner):
        """Receivable journal items of the tenant, oldest first, with a running balance."""
        lines = self.env['account.move.line'].sudo().search([
            ('partner_id', 'child_of', partner.commercial_partner_id.id),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('company_id', 'in', self.env.companies.ids),
        ], order='date, move_id, id')
        balance = 0.0
        result = []
        for line in lines:
            balance += line.balance
            result.append({
                'date': line.date,
                'reference': line.move_id.name,
                'label': line.move_id.invoice_origin or line.name or line.move_id.ref or '',
                'debit': line.debit,
                'credit': line.credit,
                'balance': balance,
            })
        return result

    @api.model
    def _get_report_values(self, docids, data=None):
        partners = self.env['res.partner'].browse(docids)
        partners.check_access('read')
        return {
            'doc_ids': docids,
            'doc_model': 'res.partner',
            'docs': partners,
            'company': self.env.company,
            'statement_lines': {partner.id: self._get_statement_lines(partner) for partner in partners},
        }
