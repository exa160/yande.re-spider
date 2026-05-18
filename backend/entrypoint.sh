#!/bin/sh
set -e

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running database migrations..."

cd /app/backend

alembic upgrade head 2>&1 || {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: Alembic migration failed, falling back to create_all"
}

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting application..."
exec uvicorn service:main_app --host 0.0.0.0 --port 8000
