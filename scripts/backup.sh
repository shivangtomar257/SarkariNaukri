#!/bin/sh
set -eu
mkdir -p /backups
STAMP=$(date +%Y%m%d_%H%M%S)
pg_dump "$DATABASE_URL" | gzip > "/backups/sarkarinaukri_${STAMP}.sql.gz"
find /backups -type f -name '*.sql.gz' -mtime +14 -delete
