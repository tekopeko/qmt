#!/bin/sh
# Migrate, then serve. Railway injects $PORT.
set -e
alembic upgrade head
exec uvicorn qmt.web.app:app --host 0.0.0.0 --port "${PORT:-8000}"
