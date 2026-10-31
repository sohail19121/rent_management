# Rent Management for Odoo 20

A complete rent management system built as a native **Odoo 20** application, with a
dedicated **tenant portal**.

It covers the full rental cycle in one place: properties and units, tenants and KYC,
lease agreements, automatic rent invoicing, security deposits, electricity billing,
maintenance, move-out settlement and reporting. Billing runs on standard Odoo
Accounting, so every rent invoice, deposit and refund is a real journal entry.

Tenants get their own portal where they can see their lease, pay rent online, download
documents and report maintenance problems.

| | |
|---|---|
| Technical name | `rent_management` |
| Version | `20.0.1.0.0` |
| Odoo version | 20.0 |
| Category | Services / Rent Management |
| Depends on | `mail`, `portal`, `account`, `product`, `contacts` |
| License | LGPL-3 |
| Author | Mohd Sohail |

---

## Features

### Properties and units
- Properties with type, address, owner and assigned property manager.
- Units per property, with unit type, furnishing, amenities and occupancy status.
- The current lease and current tenant are shown on each unit.
- Units can be flagged as under maintenance.

### Tenants and owners
- Contacts can be marked as **Tenant** and/or **Property Owner**.
- KYC information on tenants (ID type, ID number, verification flag), plus an emergency contact.
- **Tenant Statement** PDF report per tenant.

### Lease agreements
- Lifecycle: **Draft → Confirmed → Active → Expiring → Expired**, plus **Terminated**, **Renewed** and **Cancelled**.
- Rent amount, maintenance charge, billing day and frequency (monthly, quarterly, yearly).
- Late fees, either a fixed amount or a percentage of the amount due, after a grace period.
- Automatic rent escalation (for example +5% every 12 months).
- Notice period and one-click renewal (the renewal is linked to the original lease).
- Lease agreement PDF, signature request and signed-copy upload.

### Billing and accounting
- Rent invoices are generated automatically, a configurable number of days before the due date.
- Payment reminders before the due date and overdue notices after it.
- Security deposits are invoiced to a **liability account** and refunded with a credit note at move-out. Deposit status is tracked: Pending, Received, Partially Refunded or Refunded.
- Branded rent invoice PDF and rent receipt.

### Electricity billing
Each lease chooses how electricity is charged:
- **Not charged / included in rent**
- **Fixed monthly amount**
- **Metered**: monthly readings are prepared automatically and invoiced from consumption × rate.

Every unit has a **QR label** for its meter. Staff scan it with a phone, which opens
`/rent/meter/<token>`, and enter the reading on the spot with an optional photo.

### Maintenance
- Requests by category (plumbing, electrical, cleaning, appliance, other) and priority (low to urgent).
- Workflow: **New → In Progress → Done** (or **Cancelled**).
- Requests can be assigned to a user or an outside vendor.
- The cost can be charged to the **owner** or **recharged to the tenant**. A tenant recharge creates an invoice automatically when the request is done.

### Move-out
- A move-out wizard calculates the settlement: damage charges, unpaid dues, electricity charges and the deposit refund.
- **Move-out Settlement** PDF, emailed to the tenant.

### Dashboard and reporting
- Backend dashboard for occupancy, rent collection, dues and maintenance.
- Analysis views for occupancy, rent collection and electricity consumption.

---

## Tenant portal

The portal is a full tenant workspace, not just a list of documents. When a tenant
logs in, they land directly on their rent dashboard.

| Page | URL | What the tenant can do |
|---|---|---|
| Login | `/web/login` | A branded rent login page |
| Dashboard | `/my/rent` | See current lease, amount due, overdue invoices, payments this year and quick actions |
| Leases | `/my/leases` | List of their leases with status and term |
| Lease detail | `/my/leases/<id>` | Lease terms, deposit, documents |
| Agreement | `/my/leases/<id>/agreement` | Download the lease agreement PDF |
| Signed copy | `/my/leases/<id>/signed-copy` | Download the signed agreement |
| Rent invoices | `/my/rent-invoices` | Filter invoices by paid or unpaid, open them and pay online |
| Invoice PDF | `/my/invoices/<id>/modern-pdf` | Download the branded rent invoice |
| Overdue | `/my/invoices/overdue` | See all overdue invoices and pay them together |
| Maintenance | `/my/maintenance` | Follow their maintenance requests |
| Report a problem | `/my/maintenance/new` | Create a request with category, description and photos |
| Account | `/my/account`, `/my/addresses`, `/my/security` | Profile, addresses, password and account security, in the same tenant layout |

Notes:
- **Tenants only** get the rent dashboard. Other portal users still see the standard Odoo portal. A tenant can open the standard portal home with `/my?all=1`.
- The standard `/my/invoices` page sends tenants to `/my/rent-invoices`.
- **Online payment** needs the `account_payment` module and at least one active payment provider. Without them, tenants can still see and download their invoices.
- The portal home also shows three tiles: **Your Leases**, **Rent Invoices** and **Maintenance Requests**.

### Giving a tenant portal access
1. Create the tenant under **Rent Management → Tenants** (or any contact with **Tenant** ticked).
2. Open the contact, then choose **Action → Grant portal access**.
3. The tenant receives an invitation email, sets a password and lands on `/my/rent`.

---

## User roles

| Group | Access |
|---|---|
| **Property Manager** | Manages the properties assigned to them: units, leases, maintenance, meter readings |
| **Rent Accountant** | Everything a Property Manager can do, plus every lease, rent billing, deposits and payments |
| **Rent Administrator** | Full access, including configuration |
| **Portal (tenant)** | Only their own leases, invoices and maintenance requests |

Set the role under **Settings → Users → (user) → Rent Management**.

---

## Installation

1. Put the `rent_management` folder in a directory listed in your `addons_path`.
2. Restart Odoo and update the apps list (**Apps → Update Apps List**, with developer mode on).
3. Search for **Rent Management** and click **Install**.

From the command line:

```bash
./odoo-bin -c <your.conf> -d <database> -i rent_management
```

To upgrade after code changes:

```bash
./odoo-bin -c <your.conf> -d <database> -u rent_management
```

---

## Configuration

Go to **Rent Management → Configuration → Settings** and set:

| Setting | Purpose |
|---|---|
| Rent Income Account | Income account used on rent invoice lines |
| Security Deposit Account | Liability account that holds tenant deposits |
| Rent Journal | Sales journal for rent invoices |
| Late Fee Product | Product used on late fee lines |
| Maintenance Charge Product | Product used when maintenance is recharged to a tenant |
| Invoice Days in Advance | How many days before the due date rent invoices are created (default 5) |
| Reminder Days Before Due | When the payment reminder is sent (default 3) |
| Send Overdue Notices | Email tenants when an invoice becomes overdue |
| Electricity Rate per kWh | Default rate for metered electricity (default 8.0) |
| Lease Expiry Notice (days) | How many days before the end date a lease becomes *Expiring* (default 30) |

Then:
1. Create **Amenities** under Configuration (optional).
2. Create **Properties** and their **Units**.
3. Create **Tenants**.
4. Create a **Lease**, confirm it and activate it. Rent invoicing starts automatically.

---

## Automation

All scheduled actions run daily (**Settings → Technical → Scheduled Actions**):

| Scheduled action | What it does |
|---|---|
| Rent: Generate Rent Invoices | Creates the next rent invoice for every active lease |
| Rent: Payment Reminders and Overdue Notices | Emails reminders before the due date and notices after it |
| Rent: Apply Late Fees | Adds late fees once the grace period has passed |
| Rent: Lease Expiry Alerts | Moves leases to *Expiring* and notifies the tenant |
| Rent: Expire Ended Leases | Moves leases past their end date to *Expired*, or to *Renewed* when a renewal exists |
| Rent: Apply Rent Escalation | Raises rent on leases that have reached their escalation date |
| Rent: Prepare Monthly Electricity Readings | Creates the month's draft meter readings for metered leases |

### Email templates
Lease Confirmation, Rent Invoice, Payment Reminder, Overdue Notice, Lease Expiry Notice and Move-out Settlement.

### PDF reports
Lease Agreement, Rent Invoice, Rent Receipt, Tenant Statement, Move-out Settlement and Meter QR Label.

---

## Module structure

```
rent_management/
├── controllers/   portal.py (tenant portal), meter.py (QR meter reading page)
├── data/          sequences, products, mail templates, cron jobs, portal tiles
├── demo/          demo properties, units, tenants and leases
├── docs/          handbook.html (user handbook)
├── models/        property, unit, lease, maintenance, electricity reading,
│                  dashboard, portal helpers, partner / company / invoice extensions
├── report/        PDF report templates and the tenant statement report
├── security/      groups, record rules, access rights
├── static/src/    backend dashboard, portal styles and scripts, report styles
├── tests/         lease, dashboard, electricity, meter QR and portal UI tests
├── views/         backend views, menus, portal and login templates
└── wizard/        move-out wizard
```

A detailed user handbook is in [docs/handbook.html](docs/handbook.html).

---

## Running the tests

```bash
./odoo-bin -c <your.conf> -d <test_database> -i rent_management \
    --test-enable --test-tags /rent_management --stop-after-init
```

---

## License

LGPL-3. See the [GNU LGPL v3](https://www.gnu.org/licenses/lgpl-3.0.html).
