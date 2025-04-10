#!/bin/bash

DUMP_FILE="${1:-partial_dump.sql}"
SCHEMA_NAME="public"
SAMPLE_PERCENTAGE=10

set -e

if [ -z "$DATABASE_PUBLIC_URL" ]; then
  exit 1
fi

# Dump schema only
pg_dump -s --schema="$SCHEMA_NAME" "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

TABLE_LIST_CMD="psql -tA \"$DATABASE_PUBLIC_URL\" -c \"SELECT table_name FROM information_schema.tables WHERE table_schema = '$SCHEMA_NAME' AND table_type = 'BASE TABLE';\""

eval "$TABLE_LIST_CMD" | while IFS= read -r table_name; do
  [ -z "$table_name" ] && continue

  full_table_name="\"$SCHEMA_NAME\".\"$table_name\""

  ROW_COUNT=$(psql -tA "$DATABASE_PUBLIC_URL" -c "SELECT COUNT(*) FROM $full_table_name;")

  # Check if row count is a positive number
  if [[ "$ROW_COUNT" =~ ^[1-9][0-9]*$ ]]; then
    SAMPLE_COUNT=$(( ROW_COUNT * SAMPLE_PERCENTAGE / 100 ))
    if [ "$SAMPLE_PERCENTAGE" -gt 0 ] && [ "$SAMPLE_COUNT" -eq 0 ]; then
        SAMPLE_COUNT=1
    fi

    if [ "$SAMPLE_COUNT" -gt 0 ]; then
       # Add the COPY command header
       echo "COPY $full_table_name FROM STDIN;" >> "$DUMP_FILE"

       # Append the data using \copy
       psql "$DATABASE_PUBLIC_URL" -c "\copy (SELECT * FROM $full_table_name LIMIT $SAMPLE_COUNT) TO STDOUT" >> "$DUMP_FILE"

       # Add the COPY command terminator
       echo "\." >> "$DUMP_FILE"
       echo "" >> "$DUMP_FILE"
    fi
  fi
done

exit 0
