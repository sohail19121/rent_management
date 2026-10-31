{
    'name': 'Rent Management Mobile API',
    'version': '20.0.1.0.0',
    'category': 'Services/Rent Management',
    'summary': 'REST API used by the Rent Management mobile app (same database, same access rights)',
    'description': """
        Rent Management Mobile API
        ==========================
        JSON endpoints under /rent/api/v1 for the Rent Management mobile app.

        * Login with the Odoo login and password: the app receives a personal API key
          (scope "rent_mobile") and sends it as a Bearer token.
        * Every request runs as the logged-in user: record rules and access rights of
          Rent Management apply unchanged (administrator, accountant, property manager, tenant).
        * Select the database with the X-Odoo-Database header.
        """,
    'author': 'MOHD SOHAIL',
    'depends': ['rent_management'],
    'data': [],
    'installable': True,
    'license': 'LGPL-3',
}
