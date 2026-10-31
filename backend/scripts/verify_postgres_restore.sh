#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <compressed-custom-format-backup.dump.gz>" >&2
  exit 2
fi

backup_file=$1
restore_db=gridsense_restore_test

if [[ ! -f "$backup_file" ]]; then
  echo "Backup file not found: $backup_file" >&2
  exit 2
fi

gzip -t -- "$backup_file"
gzip -dc -- "$backup_file" | docker compose exec -T db pg_restore --list >/dev/null
docker compose exec -T db pg_isready -U postgres -d gridsense >/dev/null

database_exists=$(
  docker compose exec -T db psql -XAt -v ON_ERROR_STOP=1 -U postgres -d postgres \
    -c "SELECT 1 FROM pg_database WHERE datname = '$restore_db'"
)
if [[ "$database_exists" == "1" ]]; then
  echo "Refusing to overwrite existing $restore_db; inspect or remove that disposable database first." >&2
  exit 1
fi

source_counts=$(
  docker compose exec -T db psql -XAt -v ON_ERROR_STOP=1 -U postgres -d gridsense \
    -c "SELECT count_line FROM (
          SELECT 'users=' || COUNT(*) AS count_line FROM users
          UNION ALL SELECT 'meters=' || COUNT(*) FROM meters
          UNION ALL SELECT 'readings=' || COUNT(*) FROM readings
          UNION ALL SELECT 'nem12_uploads=' || COUNT(*) FROM nem12_uploads
          UNION ALL SELECT 'daily_aggregates=' || COUNT(*) FROM daily_aggregates
        ) AS counts ORDER BY count_line"
)

docker compose exec -T db createdb -U postgres --maintenance-db=postgres "$restore_db"
gzip -dc -- "$backup_file" |
  docker compose exec -T db pg_restore -U postgres --exit-on-error --no-owner \
    --dbname="$restore_db"

restored_counts=$(
  docker compose exec -T db psql -XAt -v ON_ERROR_STOP=1 -U postgres -d "$restore_db" \
    -c "SELECT count_line FROM (
          SELECT 'users=' || COUNT(*) AS count_line FROM users
          UNION ALL SELECT 'meters=' || COUNT(*) FROM meters
          UNION ALL SELECT 'readings=' || COUNT(*) FROM readings
          UNION ALL SELECT 'nem12_uploads=' || COUNT(*) FROM nem12_uploads
          UNION ALL SELECT 'daily_aggregates=' || COUNT(*) FROM daily_aggregates
        ) AS counts ORDER BY count_line"
)

if [[ "$source_counts" != "$restored_counts" ]]; then
  printf 'Restore row-count check failed.\nSource:\n%s\nRestored:\n%s\n' \
    "$source_counts" "$restored_counts" >&2
  exit 1
fi

printf 'Restore verified in %s. Matched table counts:\n%s\n' "$restore_db" "$restored_counts"
printf 'Inspect the disposable database, then remove it with:\n'
printf 'docker compose exec -T db dropdb -U postgres %s\n' "$restore_db"
