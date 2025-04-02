#!/bin/bash

DUMP_FILE="${1:-partial_dump.sql}" # Use first argument as filename, or default
SCHEMA_NAME="public"
SAMPLE_PERCENTAGE=10

set -e

if [ -z "$DATABASE_PUBLIC_URL" ]; then
  echo "::error::DATABASE_PUBLIC_URL environment variable is not set." >&2 # Error to stderr
  exit 1
fi

pg_dump -s --clean --schema="$SCHEMA_NAME" "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

# Get list of tables (-tA = tuples only, unaligned)
TABLE_LIST_CMD="psql -tA \"$DATABASE_PUBLIC_URL\" -c \"SELECT table_name FROM information_schema.tables WHERE table_schema = '$SCHEMA_NAME' AND table_type = 'BASE TABLE';\""

# Loop through each table name and append sampled data
eval "$TABLE_LIST_CMD" | while IFS= read -r table_name; do
  [ -z "$table_name" ] && continue

  # Append \copy output (to STDOUT) directly to the main dump file
  psql "$DATABASE_PUBLIC_URL" -c "\copy (SELECT * FROM \"$SCHEMA_NAME\".\"$table_name\" TABLESAMPLE SYSTEM($SAMPLE_PERCENTAGE)) TO STDOUT" >> "$DUMP_FILE"

done

echo "Partial dump created: $DUMP_FILE"

exit 0
