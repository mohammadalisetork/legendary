# Production deployment guide

## 1. Release and application

The approved product/UAT source is `5da3c9e1e319f271d0742d178e55909c1fc4624f` in [mohammadalisetork/legendary](https://github.com/mohammadalisetork/legendary). The `release/2.5-production-final` branch adds this operational guide and the validated static-asset repair to that source. Deploy the **exact final commit SHA provided with the release**, not the moving branch tip; check `git rev-parse HEAD` against that SHA before building. Do not merge or deploy `main` as a substitute.

This is a Persian service desk with department-scoped catalogue, requests, approvals, credits and management reporting. Runtime: Python 3.12, Django 5.2.17, PostgreSQL, Gunicorn 23, Django templates, WhiteNoise 6.12, and local persistent uploads or S3-compatible storage. The Docker image is built from `Dockerfile`; Compose uses PostgreSQL 17 Alpine. `requirements.txt` pins Python dependencies. No separate frontend build is needed.

## 2. Infrastructure and secrets

Provide Docker Engine and Compose, a PostgreSQL database, durable database and upload storage, a private environment file, a reverse proxy and TLS certificate. No tested CPU/RAM sizing is specified by the application. Compose binds the app only to `127.0.0.1:8000`, suitable for a proxy on the same host; arrange private networking deliberately if the proxy is elsewhere. The container listens on port 8000. The database is internal to Compose and is not published.

Copy `deploy/production.env.example` to the ignored `.env` and replace **all** placeholders. Keep `.env` outside Git, restrict its file permissions, and deliver secrets through your normal secret manager. Do not paste real values into tickets or shell history. `APP_ENV=production` sets `DEBUG=False`; there is no `DEBUG` or `DJANGO_SECRET_KEY` setting: the application reads `AUTH_SECRET`. Required values:

| Setting | Production meaning |
| --- | --- |
| `APP_ENV` | `production` |
| `APP_URL` | Public HTTPS origin, such as `https://services.example.invalid` |
| `AUTH_SECRET` | Secret random string of at least 50 characters; keep stable across restarts |
| `ALLOWED_HOSTS` | Comma-separated public hostnames, without scheme |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated HTTPS origins, with scheme |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | PostgreSQL database, user and private password; required by this Compose file |
| `POSTGRES_HOST`, `POSTGRES_PORT` | `db`, `5432` under Compose; use the real host/port for a non-Compose deployment |
| `FILE_STORAGE_TYPE` | `local` for durable `uploads` volume, or `s3` |
| `UPLOAD_PATH` | `/app/uploads` for Compose local uploads |

`DATABASE_URL` can replace individual PostgreSQL settings in Django outside Compose; Compose itself still requires `POSTGRES_PASSWORD` and passes `POSTGRES_*` to its database and web services. Set `DATABASE_URL` empty when using the bundled database. For a managed database with this Compose file, adapt the database service/network deliberately before deployment rather than assuming that changing `.env` alone removes the bundled PostgreSQL service. `DB_SSLMODE` defaults to `prefer`; choose the managed database's required TLS mode. Use one consistent PostgreSQL major version for an existing data directory: **never attach a PostgreSQL 17 container directly to an older major-version data volume**. Plan a separate PostgreSQL upgrade if necessary.

If `FILE_STORAGE_TYPE=s3`, supply private `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` and an appropriate bucket backup policy. Django uses private signed object URLs. Optional settings in the template: `MAX_UPLOAD_SIZE`, `ALLOWED_UPLOAD_EXTENSIONS`, `REPORT_AT_RISK_RATIO`, `LOGIN_MAX_FAILURES`, `LOGIN_LOCK_MINUTES`, `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, and initial admin fields. Do not change reporting or login limits without application owner approval. `TIME_ZONE=Asia/Tehran` is set in Django, not through an environment variable.

Production sets secure session/CSRF cookies and trusts `X-Forwarded-Proto: https`. `SECURE_SSL_REDIRECT=true` and HSTS are enabled by default; HSTS includes subdomains and preload. Confirm organizational TLS/subdomain readiness before exposing the hostname. The sample `deploy/nginx.conf.example` is a starting point, **not** a complete TLS configuration: provide certificates and HTTPS termination in infrastructure. Forward the original `Host` and correct `X-Forwarded-Proto`; protect the upstream port. Do not make `/media/` a public static alias: attachment/logo responses are served through authorization-aware Django endpoints.

## 3. Persistence, static assets and process

Compose volumes `postgres_data` and `uploads` must survive every application update and restart. The database contains requests, historical snapshots, accounts and settings; `uploads` contains user files when using local storage. Back up both on a coordinated schedule. With S3, back up/protect the bucket independently. Do not delete either volume or recreate an existing production database during an update.

`STATIC_ROOT` is `/app/staticfiles` in the image filesystem. Container startup runs `collectstatic --noinput`; WhiteNoise serves versioned/compressed application assets. Static files can be rebuilt from source, unlike uploads. The image runs as UID 10001 and its startup sequence is: wait for DB (up to 30 two-second retries), `migrate --noinput`, `seed_catalog`, `collectstatic --noinput`, optional `create_initial_admin`, then Gunicorn. `seed_catalog` initializes missing catalogue defaults without overwriting edited entries; it is distinct from demo data. A startup migration failure prevents Gunicorn from starting.

The production command in `Dockerfile` is:

```sh
gunicorn service_portal.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60 --access-logfile -
```

Compose restarts both services with `unless-stopped`, checks PostgreSQL using `pg_isready` and checks web at `/health`. Gunicorn access logs go to standard output and startup/error logs to standard error; inspect both using `docker compose logs`.

## 4. First deployment

Use a **new empty** PostgreSQL database and new durable volumes only for a genuine first installation. Replace the SHA below with the exact **final release commit** supplied in the release message; the approved product ancestor is `5da3c9e1e319f271d0742d178e55909c1fc4624f`.

```sh
git clone https://github.com/mohammadalisetork/legendary.git
cd legendary
git fetch origin release/2.5-production-final
DEPLOY_SHA='<exact final release commit from release message>'
git checkout --detach "$DEPLOY_SHA"
test "$(git rev-parse HEAD)" = "$DEPLOY_SHA"
git merge-base --is-ancestor 5da3c9e1e319f271d0742d178e55909c1fc4624f HEAD
cp deploy/production.env.example .env
chmod 600 .env
# Edit .env privately: real HTTPS origin, hosts, random AUTH_SECRET, DB, storage and admin bootstrap.
docker compose config --quiet
docker compose build web
docker compose up -d
docker compose ps
docker compose logs --tail=100 web
docker compose exec -T web python manage.py showmigrations
curl -fsS -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/health
```

Compose interpolates `POSTGRES_PASSWORD` from `.env`; verify `.env` before `up`. The web entrypoint automatically runs migrations, catalogue initialization and collectstatic before Gunicorn. Check its logs for completion and confirm `/static/` resources load through the proxy. Create the initial administrator either with `INITIAL_ADMIN_USERNAME` and a **temporary strong** `INITIAL_ADMIN_PASSWORD` in the private `.env` on first startup, or set those variables privately and run `docker compose exec web python manage.py create_initial_admin`. The command does **not** reset an existing admin password. The new admin must change the password on first login. Remove the bootstrap password from the runtime environment after creation and restart web without it. Never use local demo accounts in production.

Configure DNS/TLS and proxy to the private upstream, verify public HTTPS login and an authorized attachment, and check the public `/health`. If your proxy sends HTTPS headers correctly, secure redirects should not loop.

## 5. Updating an existing deployment

Arrange a maintenance window for schema changes. Record the current SHA and PostgreSQL major version, retain the existing `.env`, database and uploads. **Back up before bringing up the new web image**, because its entrypoint automatically migrates. Perform a restore drill independently of this release.

```sh
git rev-parse HEAD                          # record OLD_SHA for rollback
docker compose ps
mkdir -p /secure/backups/legendary          # operator-controlled private location
docker compose exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > /secure/backups/legendary/pre-update.dump
test -s /secure/backups/legendary/pre-update.dump
# If using local uploads, save the volume too (not needed for S3-backed media):
docker compose run -T --rm --no-deps --entrypoint tar web -C /app/uploads -czf - . > /secure/backups/legendary/pre-update-uploads.tar.gz
test -s /secure/backups/legendary/pre-update-uploads.tar.gz
git fetch origin release/2.5-production-final
DEPLOY_SHA='<exact approved final commit>'
git checkout --detach "$DEPLOY_SHA"
test "$(git rev-parse HEAD)" = "$DEPLOY_SHA"
docker compose config --quiet
docker compose build web
docker compose stop web
docker compose up -d --no-deps web
docker compose logs --tail=100 web          # entrypoint: migrate, seed_catalog, collectstatic, Gunicorn
docker compose exec -T web python manage.py showmigrations
curl -fsS -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/health
```

Backups must be secured off host and named by timestamp/deployment. If S3 is selected, back up/version the bucket instead of the local upload volume. Verify a login, a scoped request, static assets and an authorized attachment after the health check. Avoid changing the PostgreSQL image's major version against an existing volume; the Compose file uses version 17.

The checkout above updates only application source and the web image. **Never run `docker compose down -v`, `docker volume rm`, `flush`, a destructive reset, or database recreation as part of an update.** Never delete local uploads or S3 objects to resolve a deployment error.

## 6. Migrations, backup and rollback

`python manage.py migrate --noinput` runs automatically before Gunicorn on every start. To inspect pending operations without modifying data: `docker compose exec -T web python manage.py showmigrations --plan` (on the currently running image) and review the target release migrations in source before switching. The migration history is `portal/0001` through `0014`. Forward migrations contain legacy department/governance mappings and a `0010` historical catalogue-snapshot backfill that reads existing records; size the maintenance window for actual row counts. `0014` only seeds approval policies for project-manager submissions at Normal, High, Very Urgent and Emergency priorities; it does not drop tables or columns. Review active/customized approval policies before the update: a previously disabled matching policy remains disabled, so the submission gate may require administrator configuration. Historical catalogue states that were not originally stored cannot be reconstructed. `0005` has a destructive reverse mapping: **do not blindly run reverse migrations**. Take a verified PostgreSQL backup before any schema upgrade.

The `pg_dump -Fc` command above captures the database without writing secrets into the repository. Secure the dump, check that it is nonempty, and test `pg_restore` in a separate environment. Back up local media with a volume snapshot or the tar command above; coordinate timing with database backup to preserve reference consistency. Store the previous image/commit and backup outside the worktree.

If post-update validation fails, stop web, identify whether migrations already ran, and assess old-code/new-schema compatibility before rebuilding the old commit. For code-only failures compatible with the current schema, `git checkout --detach "$OLD_SHA"; docker compose build web; docker compose up -d --no-deps web`, then rerun health and smoke checks. If the migration changed data/schema incompatibly, restore the **pre-update database backup** into a controlled database and the corresponding media snapshot, then start the old image. Coordinate this with the DBA: restore may overwrite all writes since the snapshot. Do not assume Django reverse migrations are safe or that a code checkout reverses database changes.

## 7. Health and troubleshooting

`GET /health` responds with HTTP 200 `{"status":"ok","database":"ok"}` when Django can execute `SELECT 1`; it returns HTTP 503 with database unavailable otherwise. It checks Django process routing and a DB query, **not** schema completeness, object/local file storage, login, queues or business workflows. Probe the public HTTPS endpoint as well as the private upstream. Compose's internal probe sets `X-Forwarded-Proto: https` for the SSL-redirect setting.

Use `docker compose ps`, `docker compose logs --tail=200 web db`, and `docker compose exec -T web python manage.py showmigrations` to diagnose startup, Gunicorn, DB/migration and health errors. A startup wait timeout points to DB host/port/credentials or service health. HTTP 400 suggests `ALLOWED_HOSTS`; CSRF rejection suggests `CSRF_TRUSTED_ORIGINS`, origin or proxy scheme. HTTPS redirect loops suggest an incorrect `X-Forwarded-Proto`. Missing static files: inspect `collectstatic` logs, WhiteNoise and `/static/` proxy handling. Attachment errors: inspect durable volume permissions at UID 10001 or S3 credentials/bucket access; do not expose `/media/` directly. Application code does not configure centralized log retention; the operator must collect and retain container logs.

## 8. Production prohibitions

- Do **not** run `python manage.py seed_demo --confirm-local-only`: it is local/UAT tooling, guarded by environment checks, and is never called by the production entrypoint.
- Do **not** use Django `runserver`, set `APP_ENV` to development/test, or enable `DEBUG=True` for production.
- Do **not** commit `.env`, passwords, database dumps, uploaded media or signing keys.
- Do **not** recreate the production database, remove volumes, delete media, reverse migrations casually or use local demo credentials.
