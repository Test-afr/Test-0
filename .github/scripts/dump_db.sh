#!/bin/bash

SAMPLE_PERCENTAGE=10
DUMP_FILE="${1:-partial_dump.sql}"

set -e

[ -z "$DATABASE_PUBLIC_URL" ] && exit 1

# Dump schema only
pg_dump -s --clean --if-exists "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

# Get tables
psql -tA "$DATABASE_PUBLIC_URL" -c "
  SELECT table_schema, table_name FROM information_schema.tables
  WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
" | while IFS='|' read -r schema_name table_name; do
  [ -z "$table_name" ] && continue
  
  # Count rows and calculate sample size
  ROW_COUNT=$(psql -tA "$DATABASE_PUBLIC_URL" -c "SELECT COUNT(*) FROM \"$schema_name\".\"$table_name\"")
  SAMPLE_COUNT=$(( ROW_COUNT * SAMPLE_PERCENTAGE / 100 ))
  [ "$SAMPLE_COUNT" -lt 1 ] && SAMPLE_COUNT=1
  
  # Use pg_dump with WHERE clause to get a sample of data
  pg_dump --data-only --table="$schema_name.$table_name" \
    --column-inserts \
    --where="ctid IN (SELECT ctid FROM \"$schema_name\".\"$table_name\" TABLESAMPLE SYSTEM($SAMPLE_PERCENTAGE) LIMIT $SAMPLE_COUNT)" \
    "$DATABASE_PUBLIC_URL" >> "$DUMP_FILE"
done
