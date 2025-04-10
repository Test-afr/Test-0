#!/bin/bash

SAMPLE_PERCENTAGE=10
DUMP_FILE="${1:-partial_dump.sql}"

set -e

if [ -z "$DATABASE_PUBLIC_URL" ]; then
  echo "::error::DATABASE_PUBLIC_URL environment variable is not set." >&2
  exit 1
fi

# 1. Dump schema structure only
pg_dump -s --clean --if-exists "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

# Add comment to separate schema from data
echo "
-- 
-- Data dump (${SAMPLE_PERCENTAGE}% sample)
-- 
" >> "$DUMP_FILE"

# Get list of tables
psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" --field-separator='\t' -c "
  SELECT table_schema, table_name FROM information_schema.tables
  WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    AND table_type = 'BASE TABLE';
" | while IFS=$'\t' read -r schema_name table_name; do
  # Skip potentially empty lines from psql output
  [ -z "$schema_name" ] || [ -z "$table_name" ] && continue

  # Calculate sample size
  ROW_COUNT=$(psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" -c "
    SELECT COUNT(*) FROM \"$schema_name\".\"$table_name\";
  ")
  
  if [ "$ROW_COUNT" -gt 0 ]; then
    SAMPLE_COUNT=$(( ROW_COUNT * SAMPLE_PERCENTAGE / 100 ))
    [ "$SAMPLE_COUNT" -lt 1 ] && SAMPLE_COUNT=1
    
    echo "-- Sampling $SAMPLE_COUNT rows from $schema_name.$table_name" >> "$DUMP_FILE"
    
    # Use a temporary table for the sample data
    TEMP_TABLE="temp_sample_${RANDOM}"
    
    # Create and populate a temporary table with sampled data
    psql -v ON_ERROR_STOP=1 "$DATABASE_PUBLIC_URL" -c "
      CREATE TEMPORARY TABLE ${TEMP_TABLE} AS
      SELECT * FROM \"$schema_name\".\"$table_name\"
      ORDER BY random()
      LIMIT $SAMPLE_COUNT;
    "
    
    # Use pg_dump with --inserts to dump properly formatted INSERT statements
    pg_dump --data-only --inserts --table="${TEMP_TABLE}" "$DATABASE_PUBLIC_URL" |
      grep -v "^--" |  # Remove comments
      grep -v "^SET " |  # Remove SET statements
      grep -v "^SELECT " |  # Remove pg_dump catalog selections
      sed "s/${TEMP_TABLE}/\"$schema_name\".\"$table_name\"/g" >> "$DUMP_FILE"
    
    # Clean up
    psql -v ON_ERROR_STOP=1 "$DATABASE_PUBLIC_URL" -c "DROP TABLE IF EXISTS ${TEMP_TABLE};"
  fi
done

echo "Partial dump created: $DUMP_FILE"
exit 0
