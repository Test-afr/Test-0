#!/bin/bash

DUMP_FILE="${1:-partial_dump.sql}"
SAMPLE_PERCENTAGE=10

set -e

if [ -z "$DATABASE_PUBLIC_URL" ]; then
  exit 1
fi

# Dump schema for all non-system schemas (simpler than specifying one)
pg_dump -s "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

# Query for all user tables (schema and name), excluding system schemas
TABLE_LIST_CMD="psql -tA \"$DATABASE_PUBLIC_URL\" -c \"SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast') AND table_type = 'BASE TABLE';\""

# Loop through schema.table pairs read using IFS
eval "$TABLE_LIST_CMD" | while IFS=$'\t' read -r schema_name table_name; do
  # Skip empty lines if any occur
  [ -z "$schema_name" ] || [ -z "$table_name" ] && continue

  # Quote names correctly for use in SQL
  full_table_name="\"$schema_name\".\"$table_name\""

  ROW_COUNT=$(psql -tA "$DATABASE_PUBLIC_URL" -c "SELECT COUNT(*) FROM $full_table_name;")

  # Check if row count is a positive number
  if [[ "$ROW_COUNT" =~ ^[1-9][0-9]*$ ]]; then
    SAMPLE_COUNT=$(( ROW_COUNT * SAMPLE_PERCENTAGE / 100 ))
    if [ "$SAMPLE_PERCENTAGE" -gt 0 ] && [ "$SAMPLE_COUNT" -eq 0 ]; then
        SAMPLE_COUNT=1
    fi

    if [ "$SAMPLE_COUNT" -gt 0 ]; then
       # Use the dynamically read schema_name and table_name
       echo "COPY $full_table_name FROM STDIN;" >> "$DUMP_FILE"
       psql "$DATABASE_PUBLIC_URL" -c "\copy (SELECT * FROM $full_table_name LIMIT $SAMPLE_COUNT) TO STDOUT" >> "$DUMP_FILE"
       echo "\." >> "$DUMP_FILE"
       echo "" >> "$DUMP_FILE"
    fi
  fi
done

exit 0
