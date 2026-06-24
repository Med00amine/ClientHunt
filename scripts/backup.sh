#!/bin/sh
# SQLite (local run):  ./scripts/backup.sh
# PostgreSQL (docker): ./scripts/backup.sh docker
set -e
cd "$(dirname "$0")/.."
mkdir -p backups
STAMP=$(date +%Y-%m-%d_%H-%M-%S)
if [ "$1" = "docker" ]; then
  docker compose exec -T db pg_dump -U clienthunt clienthunt | gzip > "backups/pg_$STAMP.sql.gz"
  echo "backups/pg_$STAMP.sql.gz"
else
  backend/.venv/bin/python -m app.cli backup 2>/dev/null || (cd backend && .venv/bin/python -m app.cli backup)
fi
tar -czf "backups/exports_$STAMP.tar.gz" exports 2>/dev/null && echo "backups/exports_$STAMP.tar.gz"
