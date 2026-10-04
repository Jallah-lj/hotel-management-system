# Aurora Grand Hotel Management System

Aurora Grand HMS is a production-oriented hotel operations workspace for a modern property. It connects a responsive staff console to a transactional FastAPI/PostgreSQL backend and covers the full operating loop:

> Guest registration → reservation → room assignment → check-in → folio charges → payment → invoice/receipt → check-out → housekeeping

This repository is intentionally structured as a real business system rather than a static dashboard demo. Dashboard figures, room availability, reservations, payments, housekeeping queues and reports are read from the database.

## What is included

### Operations

- Live operations dashboard: room inventory, occupancy, arrivals/departures, revenue, outstanding balances and housekeeping queue
- Room and room type catalog with availability search, rates, amenities, room condition and maintenance flags
- Server-side reservation search, pagination and date filtering
- Overlap prevention with a room row lock inside the reservation transaction
- Guest CRM profiles, VIP flags, contact/identity details and stay history
- Transactional check-in/check-out flow with room state changes and balance override controls
- Hotel services, restaurant/room-service orders and automatic folio posting
- Housekeeping task board, assignment, cleaning lifecycle and room readiness
- Maintenance tickets with priority, status, assignment and room blocking
- Expenses, payment methods, invoices and immutable payment/refund ledger entries
- CSV/PDF exports for revenue and invoices
- In-app notifications, immutable audit records and hotel settings

### Security and maintainability

- Bcrypt password hashing (no plaintext passwords)
- Short-lived signed access JWT + rotating, persisted, hashed refresh sessions
- HttpOnly session cookies, SameSite controls, CSRF double-submit protection and optional Bearer access for API clients
- RBAC with a permission catalog and built-in Super Administrator, Hotel Manager, Receptionist, Housekeeping, Accountant and Staff roles
- Login attempt tracking, account lockout and password reset/change workflows
- Input validation with Pydantic, domain business rules in services, database constraints and transaction scopes
- Soft deletion for guest, financial and operational records where appropriate
- Correlation IDs, secure headers, structured error envelopes and a database-backed `/health`
- Alembic initial migration, seed data, Docker Compose, automated tests and a static production frontend container

## Technology

- **Web:** React, TypeScript, Vite, React Router, Recharts, Lucide icons and a responsive CSS component system
- **API:** FastAPI, Pydantic v2, SQLAlchemy 2, Alembic
- **Database:** PostgreSQL 16 (SQLite is supported for the isolated unit test suite)
- **Security:** bcrypt, JOSE/JWT, secure cookies, CSRF middleware and rate-limit-ready configuration
- **Runtime:** Docker / Docker Compose, Gunicorn + Uvicorn workers, Nginx

## Repository layout

```text
backend/
  app/
    api/v1/routers/       REST endpoints by business module
    core/                 config, security, errors, RBAC, dependencies
    db/                   enums, sessions and normalized SQLAlchemy models
    schemas/              API contracts and validation
    services/             reservation/payment/auth/operations/report logic
  alembic/                migration environment and initial schema revision
  scripts/seed.py         realistic development seed data
  tests/                  auth, CSRF, RBAC and reservation business-rule tests
frontend/
  src/App.tsx             staff workspace routes and workflows
  src/lib/api.ts          credentialed API client with CSRF header support
  src/styles.css          responsive hotel operations design system
docker-compose.yml        PostgreSQL + API + Nginx web deployment
.env.example              documented environment contract
```

## Local development

### Requirements

- Python 3.11+
- Node 20+
- PostgreSQL 15+ (or Docker)

Create the environment file:

```bash
cp .env.example .env
# Set SECRET_KEY to a random value; for example:
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Backend

```bash
cd backend
python -m venv ../.venv
source ../.venv/bin/activate
pip install -r requirements-dev.txt

# Point DATABASE_URL at a local database, then:
alembic upgrade head
PYTHONPATH=. python -m scripts.seed
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API is available at `http://localhost:8000`. OpenAPI is at `/docs` while `ENABLE_DOCS=true`.

### Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The staff console is at `http://localhost:5173`. Vite proxies `/api` and `/health` to `127.0.0.1:8000`; browser code only uses relative URLs, so the same build works behind Nginx or a preview proxy.

For an isolated Arena/sandbox preview, run the API with `DEMO_MODE=true`. This keeps the seeded development account available and disables only the test-environment login throttle and lockout; the normal staff login page remains available. The test-only `/api/v1/auth/demo-login` route is disabled by default and rejected in production; do not enable it on a real deployment. For a local HTTP preview, use `COOKIE_SECURE=false` and `COOKIE_SAMESITE=lax`; reserve `COOKIE_SECURE=true` for HTTPS deployments.

To test the platform without any sign-in at all, run the API with `DISABLE_LOGIN=true` (combine with `DEMO_MODE=true`). The frontend reads `/api/v1/auth/config`, never shows the login screen, and opens the seeded development workspace automatically; the sidebar shows a `TEST MODE` badge instead of the sign-out button. The flag is rejected when `ENVIRONMENT=production`.

### Development seed accounts

These credentials are for local development only. **Change or remove them before deployment.**

| Role | Email | Password |
| --- | --- | --- |
| Super Administrator | `admin@auroragrand.example` | `AuroraAdmin!2026` |
| Hotel Manager | `manager@auroragrand.example` | `AuroraManager!2026` |
| Receptionist | `frontdesk@auroragrand.example` | `AuroraFrontdesk!2026` |
| Accountant | `finance@auroragrand.example` | `AuroraFinance!2026` |
| Housekeeping | `housekeeping@auroragrand.example` | `AuroraHousekeeping!2026` |

The seed adds 22 rooms across five room types, services, menu items, guests, future and in-house reservations, housekeeping tasks and a maintenance ticket. It is idempotent for the catalog and accounts and does not add duplicate property records.

## Database and migrations

Production schema changes go through Alembic:

```bash
cd backend
DATABASE_URL='postgresql+psycopg://user:password@host:5432/hms' alembic upgrade head
# Create a later migration after changing models:
alembic revision --autogenerate -m "describe the change"
```

The API only calls `Base.metadata.create_all()` for `development` and `test` convenience environments. Production uses the explicit migration step.

## Tests and quality checks

```bash
cd backend
PYTHONPATH=. pytest -q
# PostgreSQL integration run:
TEST_DATABASE_URL='postgresql+psycopg://...' PYTHONPATH=. pytest -q

cd ../frontend
npm run build
```

The backend tests cover:

- health and database connectivity
- session cookie issuance and authentication
- password failure behaviour
- CSRF enforcement for cookie-authenticated writes
- permission-denied responses
- reservation date validation
- overlapping room reservation prevention

## REST API overview

All application routes are under `/api/v1` and return JSON. List endpoints use a consistent page envelope:

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "pages": 0,
  "has_next": false,
  "has_previous": false
}
```

Main route groups:

- `/auth` — login, refresh, logout, password reset/change and sessions
- `/dashboard` — live operational aggregates
- `/users`, `/roles`, `/permissions` via `/admin`
- `/guests`, `/room-types`, `/rooms`, `/rooms/availability`
- `/reservations`, `/reservations/{id}/check-in`, `/check-out`, `/cancel`
- `/payments`, `/invoices`, `/expenses`
- `/services`, `/orders`, `/housekeeping`, `/maintenance`, `/notifications`
- `/reports/revenue`, `/reports/occupancy`, `/reports/expenses`, `/reports/revenue.csv`
- `/admin/settings`, `/admin/audit-logs`
- `/health`

Every state-changing domain operation is validated on the server, runs within the request transaction and creates an audit entry when applicable. Raw card numbers, CVVs and payment credentials are never accepted or stored.

## Docker deployment

```bash
cp .env.example .env
# Set a long random SECRET_KEY and a strong POSTGRES_PASSWORD in .env
docker compose up --build
```

Compose starts PostgreSQL, applies migrations, seeds a development property if the database is empty, starts Gunicorn with two Uvicorn workers, and serves the compiled React application through Nginx at `http://localhost:5173`.

For a real production deployment:

1. Use a managed PostgreSQL database with encrypted connections and automated backups.
2. Replace all seed accounts; use an external secret manager for `SECRET_KEY`, database and SMTP credentials.
3. Set `ENVIRONMENT=production`, `DEBUG=false`, `COOKIE_SECURE=true`, and HTTPS-only `CORS_ORIGINS`.
4. Run migrations as a release job before starting the API containers.
5. Configure SMTP, centralized logs, alerting, object storage for attachments, database pool limits and backup retention.
6. Put the web container behind TLS termination and a WAF; restrict PostgreSQL to the private network.

## Security notes

The development fallback secret is generated per process and is not suitable for a shared environment. Never copy the credentials above into a production database. Financial records are voided or soft deleted rather than silently removed, and the audit log has no update/delete API. Access permissions are checked in FastAPI dependencies as well as represented in the frontend, so hiding a screen never substitutes for authorization.
