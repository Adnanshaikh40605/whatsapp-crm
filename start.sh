#!/bin/bash
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Daphne ASGI serves HTTP + WebSocket (Channels). Gunicorn WSGI cannot handle /ws/inbox/.
exec daphne -b 0.0.0.0 -p "${PORT:-8000}" config.asgi:application
