# Local Browser UAT Guide

This guide runs the Release 2.5 application from this branch and creates a small, repeatable local dataset for an independent reviewer. The demo users, password, and generated records are for local UAT only. Never run the seed command against a production database.

## Prerequisites

- Git and Python 3.12 for the local path.
- Docker Engine and Docker Compose for the recommended PostgreSQL path.
- A browser pointed at `http://localhost:8000`.

Start from `release/2.5-management-intelligence-reporting`. The repository contains no UAT database or uploaded runtime files; migrations and the seed command create the data locally.

## Recommended: Docker Compose with PostgreSQL

```bash
cp .env.example .env
```

Edit `.env` for local use. Set `APP_ENV=development`, `SECURE_SSL_REDIRECT=false`, `APP_URL=http://localhost:8000`, `ALLOWED_HOSTS=localhost,127.0.0.1`, and a disposable local `POSTGRES_PASSWORD`. Use a dummy local `AUTH_SECRET` (at least 50 characters). Remove the example initial-admin variables or leave them empty; the demo seed creates the local accounts. Do not use production credentials or a production database.

```bash
docker compose up --build -d
docker compose exec web python manage.py seed_demo --confirm-local-only
docker compose ps
```

Compose waits for PostgreSQL, applies migrations, seeds the standard catalogue, collects static files, and starts Gunicorn. `seed_demo` then adds the local UAT accounts, six published departments, catalogue examples, programs/projects, requests, approvals, and credit records. The command can be rerun; it updates its UAT-owned rows without deleting other records. The local upload volume is named `uploads` and is not part of the demo dataset.

## Fallback: local Python and SQLite

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
APP_ENV=development .venv/bin/python manage.py migrate
APP_ENV=development .venv/bin/python manage.py seed_demo --confirm-local-only
APP_ENV=development .venv/bin/python manage.py runserver 127.0.0.1:8000
```

The default local database is `db.sqlite3` in the checkout and is ignored by Git. To use another database, set `DATABASE_URL=sqlite:////absolute/path/to/local-uat.sqlite3` for each command. `seed_demo` requires both the explicit confirmation flag and local/development/test mode; for PostgreSQL it also restricts the configured host to `db`, `localhost`, or a loopback address.

## Demo accounts

All accounts use the deliberately non-production local password `Local-UAT-Only-2026!`. Each has an `@example.test` email. These records are not initial production accounts. The demo seed will reset these demo-account passwords each time it runs.

| Role | Login |
|---|---|
| Super Admin | `uat-admin` |
| Executive Viewer | `uat-executive` |
| Supervisor | `uat-supervisor` |
| Department Lead | `uat-department-lead` |
| Request Manager | `uat-request-manager` |
| Program Manager | `uat-program-manager` |
| Project Manager | `uat-project-manager` |
| Requester | `uat-requester` |
| Senior Approval Authority | `uat-senior-approver` |

Department Lead and Request Manager assignments are scoped to all six demo departments. Program Manager and Project Manager assignments cover the demo programs and projects. Executive and Supervisor are read-only global roles. Super Admin has the global administrative role.

## Role-by-role review

- **Requester:** browse the Service Catalogue, open a service, save a draft, submit a request, review status/history, and read the public conversation.
- **Project Manager:** create a request in a managed project context and review program-level requests and project analytics. Use this role for the Very Urgent/Emergency approval journey.
- **Program Manager:** inspect program requests, approve or reject pending Program approval, and open a program dashboard.
- **Request Manager:** review incoming requests, assign and update work, respond, add internal notes, and route a request for Program or Senior approval.
- **Senior Approval Authority:** review and decide a pending Senior approval from the approval inbox.
- **Department Lead:** review only the authorized department scope and its analytics.
- **Executive Viewer:** review management dashboards, drill-downs, and exports without access to request details or administrative actions.
- **Supervisor:** inspect global analytics in read-only mode.
- **Super Admin:** inspect administration, catalogue lifecycle, governance configuration, and all analytics.

## End-to-end UAT scenario

1. Sign in as `uat-project-manager`. From **Service Catalogue**, select a published service and create a request under a managed program/project with **Very Urgent** priority. Submit it.
2. Sign in as `uat-program-manager`; find the request in the approval inbox and approve it. The request becomes available to provider processing.
3. Sign in as `uat-request-manager`; open the request, assign/update it, and request Senior approval from the provider workflow.
4. Sign in as `uat-senior-approver`; approve the request. Return as Request Manager, continue processing, and mark it complete.
5. Sign in as `uat-requester` or the original Project Manager and inspect the request journey, conversation, status, and history.
6. Sign in as Executive Viewer or Super Admin. Open **Analytics**, change the period or filter by Department/Program/Service/Priority/Status, open a chart or matrix drill-down, export Excel, and generate an Executive PDF report.

Some governance examples below are pre-seeded historical states for analytics and inbox inspection; they are not all live workflow tasks intended to be decided repeatedly.

## Named records for dashboards

The `UAT-RQ-###` identifiers are stable across reruns:

| Review | Record(s) | What to inspect |
|---|---|---|
| At Risk | `UAT-RQ-001` | Open request close to its initial response target. |
| Overdue | `UAT-RQ-002` | Open request beyond its initial response target. |
| Program approval | `UAT-RQ-003` | Pending Very Urgent Program Manager approval. |
| Senior approval | `UAT-RQ-004` | Pending provider Senior approval. |
| Emergency credit | `UAT-RQ-005`, `UAT-RQ-015` | Emergency credit consumption and approved governance case. |
| SLA | `UAT-RQ-006`, `UAT-RQ-010` | Completed within target and work in progress. |
| Reserved credit | `UAT-RQ-013` | Reserved Very Urgent credit. |
| Released credit | `UAT-RQ-014` | Released Emergency credit. |
| Aging | `UAT-RQ-016`–`UAT-RQ-018` | Approximately 15-, 30-, and 60-day open work. |
| Lifecycle | `UAT-RQ-007`–`UAT-RQ-012` | Cancelled, rejected, waiting, in progress, under review, and new states. |

The dashboard uses the current local date to calculate aging and SLA. Request timestamps are generated relative to each seed run, keeping the dataset useful after time passes.

## Reset and cleanup

Rerun `seed_demo --confirm-local-only` to restore/update the named demo records and reset demo account passwords. It does not delete records, so other local work is retained. To start from a fully fresh UAT database, stop Compose and remove only the local checkout's `postgres_data` volume (Docker path), or remove the local SQLite database file after stopping the app (Python path), then run migrations and the seed again. Never run these cleanup steps against shared or production infrastructure.

## Stop the application

```bash
docker compose down
```

For local SQLite, stop `runserver` with `Ctrl+C`. Browser visual review is performed by the UAT reviewer; automated checks do not substitute for that review.
