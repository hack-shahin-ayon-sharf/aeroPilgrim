#!/usr/bin/env bash
set -euo pipefail

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-search.settings}"

python manage.py makemigrations --noinput
python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn search.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}"
