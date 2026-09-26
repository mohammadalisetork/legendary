#!/bin/sh
set -eu
python manage.py wait_for_db
python manage.py migrate --noinput
python manage.py seed_catalog
python manage.py collectstatic --noinput
if [ -n "${INITIAL_ADMIN_USERNAME:-}" ] && [ -n "${INITIAL_ADMIN_PASSWORD:-}" ]; then
  python manage.py create_initial_admin
fi
exec "$@"
