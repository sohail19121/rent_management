# Rent Manager mobile app

React Native (Expo SDK 58, TypeScript, Expo Router) app for the **Rent Management** Odoo module.
It talks to Odoo through the `rent_mobile_api` addon, so the app and the Odoo web client share
**the same database, the same records and the same access rights**.

## How it connects

```
Phone app ──HTTPS──▶ Odoo  /rent/api/v1/*  (rent_mobile_api)  ──▶  PostgreSQL (same DB as the web client)
```

* Login with the normal Odoo login and password. Odoo issues a personal API key
  (scope `rent_mobile`, valid 90 days), stored in the phone's secure storage.
  Users can revoke it in Odoo: *Preferences › Account Security › API Keys*.
* The database is chosen with the `X-Odoo-Database` header (field "Database" on the login screen).
* Two-factor authentication (TOTP) is supported.

## What each user sees

| Role (Odoo group) | Tabs | Can do |
|---|---|---|
| **Rent Administrator** | Dashboard, Invoices, Leases, Maintenance, More | Everything below + rent settings, archive properties/units |
| **Rent Accountant** | Dashboard, Invoices, Leases, Maintenance, More | Manager actions + rent/deposit invoices, register payments, invoice meter readings, email invoices, tenant statements |
| **Property Manager** | Dashboard, Properties, Leases, Maintenance, More | Their properties only: properties, units, tenants (KYC, app invitation), leases (create → confirm → activate → renew → move-out), maintenance (assign, start, done), meter readings (QR scan + photo) |
| **Tenant** (portal user) | Home, Payments, My Lease, Requests, Profile | Amount due & alerts, pay online (Odoo payment page), invoices/receipts PDF, lease & agreement PDF, report a problem with photos, chat on requests, electricity usage, profile, password |

## Run it (development)

```bash
cd rent_mobile_app
npm install            # .npmrc sets legacy-peer-deps
npx expo start         # scan the QR with a development build, or press "a" for an Android emulator
```

Server address on the login screen:

* Android emulator → `http://10.0.2.2:8090`
* Phone on the same Wi-Fi → `http://<your PC LAN IP>:8090` (e.g. `http://10.67.9.68:8090`)
* Production → your HTTPS Odoo URL

The app uses native modules (camera, secure store, date picker), so use a **development build**
rather than Expo Go:

```bash
npx eas-cli@latest build --profile development --platform android   # cloud build, no Android Studio needed
# or locally (needs JDK 17 + Android SDK):  npx expo run:android
```

## Release builds

```bash
npx eas-cli@latest build --platform android     # .aab for Play Store (add --profile preview for an .apk)
npx eas-cli@latest build --platform ios         # needs an Apple developer account
```

Use HTTPS in production. Cleartext HTTP is enabled only to test against a local server.

## Odoo side

1. Install the **Rent Management Mobile API** addon (`rent_mobile_api`) in the database.
2. Restart the Odoo server after updating the addon code.
3. Give tenants app access from the app (*Tenant › Give access to the tenant app*) or from Odoo's portal access wizard.

## Project layout

```
src/app/            screens (Expo Router: one file per route)
  (tabs)/           role-based tab bar: home, properties, leases, invoices, maintenance, more
  property/ unit/ tenant/ lease/ maintenance/ reading/ meter/ invoice/
src/components/     UI kit (cards, lists, forms, pickers, charts), chatter
src/lib/            API client, auth/session, formatting, theme, data hooks
```

Checks: `npx tsc --noEmit` and `npx eslint src`.
