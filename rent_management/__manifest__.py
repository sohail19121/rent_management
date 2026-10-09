{
    'name': 'Rent Management',
    'version': '20.0.1.0.0',
    'category': 'Services/Rent Management',
    'summary': 'Properties, units, tenants, leases, rent billing, deposits and maintenance',
    'description': """
Rent Management
===============
* Properties and units with occupancy tracking
* Tenants with KYC information
* Lease agreements with automatic rent invoicing, reminders, late fees and escalation
* Security deposits posted on a liability account and refunded at move-out
* Maintenance requests, optionally recharged to the tenant
* Tenant portal: leases, rent invoices (online payment) and maintenance requests
* Dashboard, analysis views and PDF reports
""",
    'author': 'Cloud Science Labs',
    'depends': ['mail', 'portal', 'account', 'product', 'contacts'],
    'data': [
        'security/rent_security.xml',
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'data/product_data.xml',
        'report/rent_report_actions.xml',
        'report/report_lease_agreement.xml',
        'report/report_rent_receipt.xml',
        'report/report_tenant_statement.xml',
        'report/report_moveout_settlement.xml',
        'report/report_meter_qr_label.xml',
        'data/mail_template_data.xml',
        'data/ir_cron_data.xml',
        'data/portal_entry_data.xml',
        'wizard/rent_moveout_wizard_views.xml',
        'views/rent_amenity_views.xml',
        'views/rent_property_views.xml',
        'views/rent_unit_views.xml',
        'views/res_partner_views.xml',
        'views/rent_lease_views.xml',
        'views/rent_maintenance_request_views.xml',
        'views/rent_electricity_reading_views.xml',
        'views/account_move_views.xml',
        'views/rent_analysis_views.xml',
        'views/res_config_settings_views.xml',
        'views/rent_dashboard_views.xml',
        'views/rent_menus.xml',
        'views/rent_portal_templates.xml',
        'views/rent_meter_templates.xml',
    ],
    'demo': [
        'demo/rent_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'rent_management/static/src/dashboard/**/*',
            ('remove', 'rent_management/static/src/**/*.dark.scss'),
        ],
        'web.assets_web_dark': [
            'rent_management/static/src/**/*.dark.scss',
        ],
    },
    'application': True,
    'license': 'LGPL-3',
}
