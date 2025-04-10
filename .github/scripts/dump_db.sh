#!/bin/bash

# --- Configuration ---
DUMP_FILE="${1:-partial_dump.sql}" # Use first argument as filename, or default
SCHEMA_NAME="public"              # Assuming 'public' schema, adjust if needed
SAMPLE_PERCENTAGE=10              # The desired percentage

# --- Strict Mode ---
# Exit immediately if a command exits with a non-zero status.
set -e

# --- Check Environment Variable ---
if [ -z "${DATABASE_PUBLIC_URL:-}" ]; then
  echo "::error::DATABASE_PUBLIC_URL environment variable is not set." >&2 # Error to stderr
  exit 1
fi

# --- Schema Dump ---
# Dump only the schema structure for the specified schema
echo "-- Dumping schema structure for schema '$SCHEMA_NAME'..."
pg_dump -s --clean --if-exists --schema="$SCHEMA_NAME" "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

# --- Data Dump Header ---
echo "
--
-- Data dump (approximately first ${SAMPLE_PERCENTAGE}% of rows per table using LIMIT)
-- NOTE: 'First' depends on database internal order.
--
" >> "$DUMP_FILE"

# --- Get Table List ---
# Get list of base tables within the specified schema
# -t: Tuples only (no headers/footers)
# -A: Unaligned output (no padding)
TABLE_LIST_CMD="psql -v ON_ERROR_STOP=1 -tA \"$DATABASE_PUBLIC_URL\" -c \"SELECT table_name FROM information_schema.tables WHERE table_schema = '$SCHEMA_NAME' AND table_type = 'BASE TABLE';\""

# --- Data Slicing Loop ---
echo "-- Appending sliced data using \\copy and LIMIT..."

# Use eval to execute the command and pipe its output to the while loop
# IFS= ensures leading/trailing whitespace isn't trimmed from table names (though unlikely)
eval "$TABLE_LIST_CMD" | while IFS= read -r table_name; do
  # Skip empty lines potentially returned by psql
  [ -z "$table_name" ] && continue

  # Properly quote schema and table names for SQL
  full_table_name="\"$SCHEMA_NAME\".\"$table_name\""
  echo "-- Processing table: $full_table_name"

  # 1. Get total row count for the current table
  ROW_COUNT_STR=$(psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" -c "SELECT COUNT(*) FROM $full_table_name;")
  # Basic check if count is a number
  if ! [[ "$ROW_COUNT_STR" =~ ^[0-9]+$ ]]; then
      echo "::warning:: Could not get row count for $full_table_name. Skipping data copy." >&2
      continue
  fi
  ROW_COUNT=$((ROW_COUNT_STR))

  if [ "$ROW_COUNT" -eq 0 ]; then
    echo "-- Table $full_table_name is empty. Skipping."
    continue
  fi

  # 2. Calculate the LIMIT count (number of rows to fetch)
  # Use integer arithmetic with ceiling division ((N * P + 99) / 100)
  SAMPLE_COUNT=$(( (ROW_COUNT * SAMPLE_PERCENTAGE + 99) / 100 ))

  # Ensure at least 1 row is copied if percentage > 0 and table is not empty
  if [ "$SAMPLE_PERCENTAGE" -gt 0 ] && [ "$SAMPLE_COUNT" -eq 0 ]; then
      SAMPLE_COUNT=1
  fi

  echo "-- Calculated LIMIT: $SAMPLE_COUNT rows for $full_table_name ($ROW_COUNT total)"

  # 3. If SAMPLE_COUNT > 0, append data using \copy with LIMIT
  if [ "$SAMPLE_COUNT" -gt 0 ]; then
    # Use psql's \copy command to execute the SELECT with LIMIT and output in COPY format
    # Append the output directly to the main dump file
    psql -v ON_ERROR_STOP=1 "$DATABASE_PUBLIC_URL" -c "\copy (SELECT * FROM $full_table_name LIMIT $SAMPLE_COUNT) TO STDOUT" >> "$DUMP_FILE"
  else
    echo "-- Sample count is 0. Not copying data for $full_table_name."
  fi

done # End of while loop

# --- Completion ---
echo "Partial dump created: $DUMP_FILE"
exit 0
