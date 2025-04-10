#!/bin/bash

DUMP_FILE="${1:-partial_dump.sql}"
SAMPLE_PERCENTAGE=10

set -e

if [ -z "$DATABASE_PUBLIC_URL" ]; then
  exit 1
fi

pg_dump -s "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

SCHEMA_LIST_CMD="psql -tA \"$DATABASE_PUBLIC_URL\" -c \"SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast') AND schema_name NOT LIKE 'pg_temp_%' AND schema_name NOT LIKE 'pg_toast_temp_%';\""

while IFS= read -r schema_name; do
  [ -z "$schema_name" ] && continue

  TABLE_LIST_CMD="psql -tA \"$DATABASE_PUBLIC_URL\" -c \"SELECT table_name FROM information_schema.tables WHERE table_schema = '$schema_name' AND table_type = 'BASE TABLE';\""

  while IFS= read -r table_name; do
    [ -z "$table_name" ] && continue

    full_table_name="\"$schema_name\".\"$table_name\""

    ROW_COUNT=$(psql -tA "$DATABASE_PUBLIC_URL" -c "SELECT COUNT(*) FROM $full_table_name;")

    if [[ "$ROW_COUNT" =~ ^[0-9]+$ ]]; then
      if [ "$ROW_COUNT" -gt 0 ]; then
        SAMPLE_COUNT=$(( ROW_COUNT * SAMPLE_PERCENTAGE / 100 ))
        if [ "$SAMPLE_PERCENTAGE" -gt 0 ] && [ "$SAMPLE_COUNT" -eq 0 ]; then
            SAMPLE_COUNT=1
        fi

        if [ "$SAMPLE_COUNT" -gt 0 ]; then
           echo "COPY $full_table_name FROM STDIN;" >> "$DUMP_FILE"
           psql "$DATABASE_PUBLIC_URL" -c "\copy (SELECT * FROM $full_table_name LIMIT $SAMPLE_COUNT) TO STDOUT" >> "$DUMP_FILE"
           echo "\." >> "$DUMP_FILE"
           echo "" >> "$DUMP_FILE"
        fi
      fi
    fi
  done < <(eval "$TABLE_LIST_CMD")

done < <(eval "$SCHEMA_LIST_CMD")

exit 0
