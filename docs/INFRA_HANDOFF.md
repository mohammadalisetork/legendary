# Infrastructure handoff — Release 2.5

- **Repository:** [mohammadalisetork/legendary](https://github.com/mohammadalisetork/legendary)
- **Approved product/UAT source:** `5da3c9e1e319f271d0742d178e55909c1fc4624f`.
- **Deployment source:** `release/2.5-production-final`; checkout the exact final SHA supplied with the release, then verify `git rev-parse HEAD` and ancestry from the approved product source. Never deploy a moving branch tip.
- **Runtime:** Python 3.12, Django 5.2.17, Gunicorn (3 workers, 60-second timeout), Docker/Compose. Container entrypoint runs DB wait, migrations, catalogue initialization, collectstatic, optional admin creation, then Gunicorn.
- **Database:** PostgreSQL, Compose image `postgres:17-alpine`. Preserve the `postgres_data` volume. Check existing cluster's major version before reusing a volume.
- **Files:** WhiteNoise serves rebuilt static assets; local user media is on the persistent `uploads` volume at `/app/uploads`, or private S3-compatible storage. Back up media separately from the database.
- **Private configuration:** Copy `deploy/production.env.example` to ignored `.env`; configure production HTTPS URL/hosts/CSRF origins, random `AUTH_SECRET` (50+ characters), PostgreSQL credentials and storage. Initial admin temporary password is supplied privately and removed after first login/rotation. No production secrets are committed.
- **Network:** App binds `127.0.0.1:8000` on the host, behind TLS proxy forwarding Host and X-Forwarded-Proto. The sample Nginx file needs real TLS configuration.
- **Start:** `docker compose config --quiet && docker compose build web && docker compose up -d`; verify entrypoint logs and `GET /health` (HTTP 200 plus DB query). Full steps and separate update/rollback procedures: [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md).
- **Before every update:** record old SHA, back up PostgreSQL and local uploads/S3, verify restore plan; do not remove database or media volumes. The new web container automatically migrates at startup.
- **Forbidden in production:** demo seed, Django runserver, development/DEBUG mode, committed credentials, database reset, `docker compose down -v`, destructive migration reversal and media deletion.
