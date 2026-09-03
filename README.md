# Repair-Hub

[![Test](https://github.com/aon082910/repair-hub/actions/workflows/test.yml/badge.svg)](https://github.com/aon082910/repair-hub/actions/workflows/test.yml)

A self-hosted repair-reference and shop-management app: vehicles, repair
guides (steps + photos), wiring diagrams, a diagnostic trouble code (DTC)
lookup, and customer/work-order/invoice tracking. Runs entirely offline on
your own hardware (e.g. Unraid) via Docker.

## What this is (and isn't)

Repair-Hub is a **blank system you populate yourself**. It ships with:

- A preloaded reference table of ~140 **generic OBD-II DTC codes** (P0100,
  P0300, P0420, etc.) — these are SAE-standardized, publicly published
  definitions used by every generic scan tool, not proprietary content.
- Empty repair guide, wiring diagram, and shop-management tables, plus an
  admin UI and bulk-import tools so you can add your own content — guides you
  write, photos you take, diagrams you own the rights to, or manufacturer
  service info you're separately licensed to keep.

It does **not** scrape, mirror, or redistribute ALLDATA (or any other paid
provider's) content. If you have your own paid ALLDATA subscription, the
**vehicle detail page** lets you save a quick link to the matching ALLDATA
page (opens in your own logged-in browser tab) or attach a file you've
personally exported from your account — both are just pointers/uploads you
control, never automated fetching.

## Features

- **Sidebar layout with tabbed vehicle pages** (Repair Guides / Wiring
  Diagrams / Recalls & Complaints / ALLDATA), styled after shop-management
  tools like Mitchell1 Manager and ALLDATA's own catalog flow.
- **Year/Make/Model quick lookup** on the Vehicles page, populated from
  whatever makes/models you've already added.
- **Live NHTSA Recalls & Complaints tab** on every vehicle page — pulled at
  view-time from `api.nhtsa.gov` (free, public, no key required). Falls back
  gracefully to "unavailable" if the server has no internet access.
- **Free external guide search** (`Search Free Guides` in the sidebar) —
  queries iFixit's public, Creative-Commons-licensed guide API and links out
  to the source. Repair-Hub never copies or stores iFixit's content. This is
  the only external search wired in; paid/ToS-restricted sites (Mitchell1,
  Chilton, RepairPal, ALLDATA itself) are deliberately not searched.
- **Web-based bulk import** for repair guides (JSON) and DTC codes (CSV) at
  `/guides/import/` and `/diagnostics/import/` (staff accounts only) — no
  need to shell into the container. The CLI management commands still work
  too and share the same import logic.
- **Job-board work order view** (`/shop/work-orders/`) — columns by status,
  click a status dropdown on a work order to move it.
- **Customer status portal** — each work order gets a private, unguessable
  link (`Customer status link` field on the work order page) that shows a
  read-only, no-login status/invoice summary. Nothing internal (technician
  notes, diagnosis) is exposed on it.
- **Real customer login accounts** — from a customer's page, staff can click
  "Create Customer Login" to generate a username/password (shown once). The
  customer then signs in at `/login/` like anyone else and lands on their own
  dashboard listing their vehicles and service history — no access to any
  other customer's data or internal shop/reference pages (enforced server-side,
  not just hidden in the UI).
- **Favorites/bookmarks** — a ☆ Favorite button on repair guides, DTC codes,
  and vehicles; "My Favorites" in the sidebar lists everything you've starred.
- **Vehicle Specs tab** — live engine/transmission/fuel-economy data from the
  EPA's free public fueleconomy.gov API.
- **Reference Photos tab / search** — free-text search against Wikimedia
  Commons' CC-licensed photo library (generic component reference images,
  not vehicle-specific repair photos).
- **YouTube walkthrough links** on guide, DTC, and vehicle pages — a
  one-click search link (no API key, no embedding) to video walkthroughs
  for that repair.
- **Estimates with customer approval** — build an estimate (labor + parts),
  mark it sent, and share its private approval link. The customer approves
  or declines with no login required; staff then convert an approved estimate
  into a work order with one click (line items carry over automatically).
- **Appointment scheduling** — a week-view calendar (`/shop/appointments/`)
  grouped by day; "Start Work Order" on an appointment creates a work order
  pre-filled from it.
- **Maintenance reminders** — track service items per vehicle by due date
  and/or mileage (compared against the vehicle's most recent work-order
  odometer reading). Mark one done and, if it has a repeat interval, the next
  occurrence is created automatically. Due-soon items (within 30 days or
  1,000 miles) surface on both the staff and customer dashboards.
- **Global search** — one search box in the sidebar across vehicles, repair
  guides, DTC codes, customers, and work orders at once.
- **Backup** — "Download Backup" in the sidebar (staff) exports a JSON
  snapshot of all business data (not uploaded files) for quick portability.
  For real disaster recovery, use `scripts/backup.sh` (see Backups section
  below) — a safe SQLite hot-backup plus your media files in one tarball.
- **Mobile-friendlier layout** — tables scroll horizontally instead of
  breaking the page on narrow screens, and the sidebar collapses to a top
  bar under ~800px.
- **Technician accounts** — a third account tier. Techs can browse repair
  reference content (vehicles/guides/DTC/wiring) and view/update only their
  own assigned work orders (status, labor, parts) — no customer list, no
  financials, no other techs' jobs. Staff assign a technician to a work
  order from its detail page.
- **Parts inventory** — track part number, on-hand quantity, reorder point,
  cost, and default price. Adding a part to a work order can pull from
  inventory (auto-filling number/description/price) and decrements stock.
  Low-stock parts surface on the Reports page.
- **Digital vehicle inspections (DVI)** — start one from a work order to get
  a standard multi-point checklist (brakes, tires, fluids, battery, etc.);
  mark each item Good/Monitor/Needs Attention with notes and an optional
  photo. Share the read-only customer report link, or one click turns every
  flagged item into a new estimate.
- **PDF export** — download a formatted invoice (work order) or estimate as
  a PDF, including the customer's captured signature if they approved
  on-screen.
- **E-signature capture** — the estimate approval page includes a signature
  pad (plain HTML5 canvas, no external library); the signature is stored and
  shown on the estimate and its PDF.
- **Revenue reports** (`/shop/reports/`) — total revenue, completed-order
  count, average ticket, and work-order counts by status over a selectable
  date range, plus your most-used repair guides and any low-stock parts.
- **Activity log** — a lightweight audit trail of status changes on work
  orders/estimates and account creation, so you can see who did what.
- **QR service-history tags** — generate a QR code from a vehicle's page
  (button next to the YouTube link) that opens a public, read-only service
  history for that vehicle — print it and stick it on the car.
- **Light/dark theme toggle** — button at the bottom of the sidebar; saved
  per-browser via localStorage.

### Access model

Three account types share the same `/login/` page:
- **Staff accounts** (`is_staff=True`, created via `createsuperuser` or Admin)
  see the full app — reference data, shop management, imports, reports,
  Admin.
- **Technician accounts** (created by staff at `/shop/technicians/new/`) see
  repair reference content plus only their own assigned work orders.
- **Customer accounts** (created by staff from a customer's page) see only
  their own dashboard (`/shop/dashboard/`) with their vehicles and service
  history.

Every internal view is gated server-side by a decorator
(`staff_required` / `staff_or_technician_required`, in
`core/decorators.py`), so a customer or technician account hitting a URL
outside their tier gets a 403, not a redirect loop or a data leak. Work
order actions (view/update status/add labor/add parts) additionally check
that a technician is the one actually assigned to that job.

## Stack

Django 5, served by Gunicorn behind WhiteNoise for static files, backed by
SQLite. One container, one `/config` volume holding the database and
uploaded media — everything you need to back up lives in that one place.

## Running on Unraid

**Easiest: install from Community Applications.** Search "Repair-Hub" in the
**Apps** tab (once this template is listed) and click Install — every
setting below has a sane default; you only need to set a superuser
username/password on first run.

To add the template manually before it's indexed:
```bash
wget -O /boot/config/plugins/dockerMan/templates-user/my-repair-hub.xml \
  https://raw.githubusercontent.com/aon082910/AoN-Unraid-Apps/main/Repair-Hub/repair-hub.xml
```
Then **Docker → Add Container** and pick it from the template dropdown.

**Or run it directly:**
```bash
docker run -d --name repair-hub \
  -p 8080:8000 \
  -e PUID=99 -e PGID=100 -e TZ=Etc/UTC \
  -e DJANGO_SECRET_KEY="$(openssl rand -hex 32)" \
  -e DJANGO_SUPERUSER_USERNAME=admin \
  -e DJANGO_SUPERUSER_PASSWORD=change-me \
  -v /mnt/user/appdata/repair-hub:/config \
  allornothing/repair-hub:latest
```
Open `http://<your-unraid-ip>:8080/` and log in with that superuser.

The container automatically runs migrations, collects static files, and
seeds the generic DTC codes on every startup — safe to restart/update
anytime. `PUID`/`PGID` control who owns `/config` on the host (99/100 is
Unraid's built-in nobody/users).

### Data persistence

Everything lives under the one `/config` volume: `db.sqlite3` and
`media/` (uploaded photos, diagrams, ALLDATA attachments). Back that one
directory up and you've backed up the whole app.

### Building it yourself instead of pulling the image

```bash
git clone https://github.com/aon082910/repair-hub.git
cd repair-hub
cp .env.example .env && nano .env
docker compose up -d --build
```

## Backups

The sidebar's "Download Backup" button is a convenient JSON snapshot for
quick portability, but the reliable way to back up Repair-Hub is a safe
SQLite hot-backup plus the media directory — that's what `scripts/backup.sh`
does (run from a machine with Docker access to the container, e.g. the
Unraid terminal):

```bash
chmod +x scripts/backup.sh scripts/restore.sh   # once
./scripts/backup.sh repair-hub
```

This writes `backups/repairhub-<timestamp>.tar.gz` (database snapshot +
media), keeping the last 14. To schedule it, add a cron job via Unraid's
**User Scripts** plugin pointing at `scripts/backup.sh repair-hub` (e.g.
daily at 3am). Since it's one plain tarball, an even simpler option is to
just back up `/mnt/user/appdata/repair-hub` with whatever appdata-backup
tool you already use (CA Backup / Appdata Backup plugin) — no database
server involved, no special handling needed.

To restore (stops the container, replaces the database and media, restarts
it):

```bash
./scripts/restore.sh backups/repairhub-20260101-030000.tar.gz repair-hub
```

## Adding your own content

### Repair guides (bulk import)

Write your guides as JSON (see the docstring in
`repairguides/management/commands/import_guides.py` for the exact shape),
then run inside the container:

```bash
docker cp my_guides.json repair-hub:/config/media/my_guides.json
docker exec -it repair-hub python manage.py import_guides /config/media/my_guides.json
```

Re-run with `--update` to overwrite existing guides with the same
title+system.

### DTC codes (manufacturer-specific, bulk import)

```bash
docker cp my_codes.csv repair-hub:/config/media/my_codes.csv
docker exec -it repair-hub python manage.py import_dtc_codes /config/media/my_codes.csv
```

CSV columns: `code,description,system,origin,make,likely_causes,diagnostic_steps`.

Both importers are also available as web forms at `/guides/import/` and
`/diagnostics/import/` for any staff-flagged user — upload the file directly
from your browser, no shell access needed.

### Everything else (photos, wiring diagrams, work orders, customers)

Use the built-in **Admin** panel (`/admin/`) — it has full CRUD for every
model, including image/file uploads and inline step editors for guides.

## External data sources used

| Source | What it provides | Why it's OK to use |
|---|---|---|
| [NHTSA vPIC](https://vpic.nhtsa.dot.gov/) | VIN decoding | Free public government API, no key |
| [NHTSA Recalls/Complaints](https://api.nhtsa.gov/) | Recalls & owner complaints by vehicle | Free public government API, no key |
| [iFixit API](https://www.ifixit.com/api/2.0/doc/) | Free repair guide search | Public API, CC-licensed content, designed for third-party search/link-out |
| [fueleconomy.gov (EPA)](https://www.fueleconomy.gov/feg/ws/) | Engine/transmission/MPG specs | Free public government API, no key |
| [Wikimedia Commons](https://commons.wikimedia.org/w/api.php) | Reference photos/diagrams | Free public API, CC-licensed media |
| YouTube (search link only) | Repair walkthrough videos | Plain search-results link, no API key, no embedding |

All of these are optional at runtime — pages degrade gracefully (with a plain
message) if the container has no internet access. Deliberately **not**
wired in: Mitchell1, Chilton/Haynes, RepairPal Pro, AutoZone/RockAuto parts
catalogs, and manufacturer factory service manuals — all are either paid,
ToS-restricted, or copyrighted with no public API.

## Local development (without Docker)

```bash
python -m venv .venv
.venv/Scripts/activate   # or source .venv/bin/activate on Linux/Mac
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_dtc_codes
python manage.py createsuperuser
python manage.py runserver
```

No environment variables needed — it defaults to `config/db.sqlite3` and
`config/media/` under the project root (gitignored) when `DB_PATH`/
`MEDIA_ROOT` aren't set.

## Running tests

The test suite (92 tests) covers models, permissions, and the key workflows
across every app — access control for all three account tiers, the full
estimate approve/decline/convert lifecycle, inventory stock deduction,
inspection creation and estimate generation, maintenance reminder due/overdue
logic, and the external API clients (mocked, not hitting the real network).
It runs against an in-memory SQLite database, so it needs no Postgres server:

```bash
python manage.py test --settings=repairhub.test_settings
```

Run a single app's tests with e.g. `python manage.py test shop.tests
--settings=repairhub.test_settings`. The two PDF-export tests
(`shop.tests.PDFExportTests`) skip themselves cleanly if `xhtml2pdf` can't be
imported in the current environment, so the rest of the suite still runs.

Run this after any change before deploying — it's much faster than the
manual click-through testing this project relied on during initial
development, and it'll catch a broken permission check or a regressed
workflow immediately.

`.github/workflows/test.yml` runs this same suite automatically on every
push and pull request to `main`.

## Releasing a new version

`.github/workflows/docker-publish.yml` builds and pushes
`allornothing/repair-hub` to Docker Hub (tagged `latest` and the version
number) whenever a tag matching `v*.*.*` is pushed:

```bash
git tag v1.1.0
git push origin v1.1.0
```

**One-time setup**, before the first release: add two repository secrets
under **Settings → Secrets and variables → Actions**:
- `DOCKERHUB_USERNAME` — your Docker Hub username
- `DOCKERHUB_TOKEN` — a Docker Hub **access token** (Docker Hub →
  Account Settings → Security → New Access Token; not your account
  password), scoped to read/write on this repository

After a release publishes, bump `<Date>`/`<Changes>` in
[`repair-hub.xml`](https://github.com/aon082910/AoN-Unraid-Apps/blob/main/Repair-Hub/repair-hub.xml)
in the template repo so Unraid users see there's an update.

## Project layout

- `vehicles/` — Make/Model/Vehicle records, VIN decode + specs via NHTSA/EPA,
  maintenance reminders, QR service-history page.
- `diagnostics/` — DTC code reference table + seed command.
- `repairguides/` — Repair guides (steps + photos) and wiring diagrams;
  bulk import commands.
- `shop/` — Customers, technicians, work orders, estimates, appointments,
  inventory, inspections, invoices, reports, activity log.
- `integrations/` — Manual ALLDATA link/attachment support for users with
  their own paid subscription.
- `core/` — Dashboard, global search, favorites, backup export, access
  control (`core/decorators.py`).
- `scripts/` — SQLite backup/restore shell scripts for Unraid cron.
- Each app's `tests.py` — the automated test suite (see "Running tests"
  above); `repairhub/test_settings.py` swaps in SQLite so it runs without
  a Postgres server.

### A note on PDF export

`workorder_pdf`/`estimate_pdf` use `xhtml2pdf`, which depends on
`python-bidi` (a Rust-backed package with prebuilt wheels for Linux/Docker —
this is why the Dockerfile doesn't need extra system packages for it). The
import is deliberately lazy (inside the two PDF view functions) so the rest
of the app works even in an environment where that dependency can't load.
