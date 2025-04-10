#!/bin/bash

SAMPLE_PERCENTAGE=10
DUMP_FILE="${1:-partial_dump.sql}"

set -e

[ -z "$DATABASE_PUBLIC_URL" ] && exit 1

pg_dump -s --clean --if-exists "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" --field-separator='\t' -c "
  SELECT table_schema, table_name FROM information_schema.tables
  WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    AND table_type = 'BASE TABLE';
" | while IFS=$'\t' read -r schema_name table_name; do
  [ -z "$schema_name" ] || [ -z "$table_name" ] && continue

  ROW_COUNT=$(psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" -c "
    SELECT COUNT(*) FROM \"$schema_name\".\"$table_name\";
  ")
  
  if [ "$ROW_COUNT" -gt 0 ]; then
    SAMPLE_COUNT=$(( ROW_COUNT * SAMPLE_PERCENTAGE / 100 ))
    [ "$SAMPLE_COUNT" -lt 1 ] && SAMPLE_COUNT=1
    
    TEMP_TABLE="temp_sample_${RANDOM}"
    
    psql -v ON_ERROR_STOP=1 "$DATABASE_PUBLIC_URL" -c "
      CREATE TEMPORARY TABLE ${TEMP_TABLE} AS
      SELECT * FROM \"$schema_name\".\"$table_name\"
      ORDER BY random()
      LIMIT $SAMPLE_COUNT;
    "
    
    pg_dump --data-only --inserts --table="${TEMP_TABLE}" "$DATABASE_PUBLIC_URL" |
      grep -v "^--" |
      grep -v "^SET " |
      grep -v "^SELECT " |
      sed "s/${TEMP_TABLE}/\"$schema_name\".\"$table_name\"/g" >> "$DUMP_FILE"
    
    psql -v ON_ERROR_STOP=1 "$DATABASE_PUBLIC_URL" -c "DROP TABLE IF EXISTS ${TEMP_TABLE};"
  fi
done
