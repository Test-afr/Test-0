#!/bin/bash

SAMPLE_PERCENTAGE=10
DUMP_FILE="${1:-partial_dump.sql}"

set -e

[ -z "$DATABASE_PUBLIC_URL" ] && exit 1

# Dump schema only first
pg_dump -s --clean --if-exists "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

# Get tables and add data
psql -tA "$DATABASE_PUBLIC_URL" -c "
  SELECT table_name FROM information_schema.tables
  WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
" | while read -r table_name; do
  [ -z "$table_name" ] && continue
  
  # Create a temp table with deterministic sampling (first 10%, not random)
  TEMP_TABLE="temp_${RANDOM}"
  
  # Find the primary key for ordering
  pk_column=$(psql -tA "$DATABASE_PUBLIC_URL" -c "
    SELECT a.attname FROM pg_index i
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
    WHERE i.indrelid = '${table_name}'::regclass AND i.indisprimary
    LIMIT 1
  ")
  
  # Default to 'id' if no PK found
  [ -z "$pk_column" ] && pk_column="id"
  
  # Sample first N% of rows ordered by PK
  psql "$DATABASE_PUBLIC_URL" -c "
    CREATE TEMP TABLE ${TEMP_TABLE} AS
    SELECT * FROM ${table_name}
    ORDER BY ${pk_column}
    LIMIT (SELECT GREATEST(1, count(*) * ${SAMPLE_PERCENTAGE} / 100) FROM ${table_name})
  "
  
  # Dump the temp table with proper inserts
  pg_dump --data-only --column-inserts --table=${TEMP_TABLE} "$DATABASE_PUBLIC_URL" |
    grep -v "^--" |
    grep -v "^SET" |
    grep -v "^SELECT" |
    sed "s/${TEMP_TABLE}/${table_name}/g" >> "$DUMP_FILE"
  
  # Clean up
  psql "$DATABASE_PUBLIC_URL" -c "DROP TABLE IF EXISTS ${TEMP_TABLE}"
done
