#!/bin/bash

# --- Configuration ---
SAMPLE_PERCENTAGE=${SAMPLE_PERCENTAGE:-10}
DUMP_FILE="${1:-partial_dump.sql}"
# Optional: Specify a column to order by for deterministic "first N%"
# If empty, relies on database's default order (often insertion order)
# Example: ORDER_BY_COLUMN="id"
ORDER_BY_COLUMN=""

# --- Strict Mode ---
set -euo pipefail
# Optional: uncomment for detailed command tracing
# set -x

# --- Check Environment Variable ---
if [ -z "${DATABASE_PUBLIC_URL:-}" ]; then
  echo "::error::DATABASE_PUBLIC_URL environment variable is not set." >&2
  exit 1
fi

echo "Creating partial dump file: $DUMP_FILE"
echo "Sampling percentage: ${SAMPLE_PERCENTAGE}% (using LIMIT)"
if ! [[ "$SAMPLE_PERCENTAGE" =~ ^[0-9]+$ ]] || [ "$SAMPLE_PERCENTAGE" -lt 0 ] || [ "$SAMPLE_PERCENTAGE" -gt 100 ]; then
    echo "::error:: SAMPLE_PERCENTAGE must be an integer between 0 and 100." >&2
    exit 1
fi

# --- Schema Dump ---
echo "-- Dumping schema structure..."
pg_dump -s --clean --if-exists "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

# --- Data Dump Header ---
echo "
--
-- Data dump (approximately first ${SAMPLE_PERCENTAGE}% of rows per table using LIMIT)
-- NOTE: 'First' depends on database internal order unless ORDER_BY_COLUMN is set.
--
" >> "$DUMP_FILE"

# --- Get Table List ---
TABLE_LIST_QUERY="
  SELECT table_schema, table_name
  FROM information_schema.tables
  WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    AND table_type = 'BASE TABLE';
"

# --- Data Sampling Loop ---
echo "-- Dumping sampled data using pg_dump with LIMIT..."
psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" --field-separator='\t' -c "$TABLE_LIST_QUERY" | while IFS=$'\t' read -r schema_name table_name; do
  if [ -z "$schema_name" ] || [ -z "$table_name" ]; then
    continue
  fi

  full_table_name="\"$schema_name\".\"$table_name\""
  echo "-- Processing table: $full_table_name"

  # Get total row count
  ROW_COUNT_STR=$(psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" -c "SELECT COUNT(*) FROM $full_table_name;")
   if ! [[ "$ROW_COUNT_STR" =~ ^[0-9]+$ ]]; then
      echo "::warning:: Could not get valid row count for $full_table_name. Received '$ROW_COUNT_STR'. Skipping." >&2
      continue
   fi
   ROW_COUNT=$((ROW_COUNT_STR))

  if [ "$ROW_COUNT" -eq 0 ]; then
    echo "-- Table $full_table_name is empty. Skipping."
    continue
  fi

  # Calculate the number of rows to sample (limit count)
  # Use integer arithmetic with ceiling division
  SAMPLE_COUNT=$(( (ROW_COUNT * SAMPLE_PERCENTAGE + 99) / 100 ))
  # Ensure at least 1 row if percentage > 0 and table not empty
  if [ "$SAMPLE_PERCENTAGE" -gt 0 ] && [ "$SAMPLE_COUNT" -eq 0 ] && [ "$ROW_COUNT" -gt 0 ]; then
      SAMPLE_COUNT=1
  fi

  if [ "$SAMPLE_COUNT" -gt 0 ]; then
    echo "-- Calculating LIMIT $SAMPLE_COUNT for $full_table_name ($ROW_COUNT total)"

    # Construct the ORDER BY clause if a column is specified
    ORDER_CLAUSE=""
    if [ -n "$ORDER_BY_COLUMN" ]; then
        # Basic check if column exists (optional, adds overhead)
        # psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" -c "SELECT 1 FROM information_schema.columns WHERE table_schema='$schema_name' AND table_name='$table_name' AND column_name='$ORDER_BY_COLUMN';" | grep -q 1 && \
        ORDER_CLAUSE="ORDER BY \"$ORDER_BY_COLUMN\""
        # echo "-- Using ORDER BY $ORDER_BY_COLUMN" # Uncomment for debugging
    fi

    # Construct the SELECT statement for pg_dump's --table argument
    # Alias the table name back to itself so pg_dump generates the correct COPY statement
    # SELECT * FROM "schema"."table" AS "table" ORDER BY ... LIMIT N
    select_statement="SELECT * FROM $full_table_name AS \"$table_name\" $ORDER_CLAUSE LIMIT $SAMPLE_COUNT"

    echo "-- Dumping data for: $full_table_name using LIMIT $SAMPLE_COUNT"

    # Dump data using the constructed SELECT statement
    # Filter out transaction control and comments
    pg_dump --data-only --table="$select_statement" "$DATABASE_PUBLIC_URL" | \
      grep -v '^--' | \
      grep -v '^SET ' | \
      grep -v '^SELECT ' | \
      grep -v '^BEGIN;' | \
      grep -v '^COMMIT;' | \
      grep -v '^\s*$' >> "$DUMP_FILE"

    dump_exit_status=${PIPESTATUS[0]}
    if [ $dump_exit_status -ne 0 ]; then
        echo "::warning:: pg_dump command failed for $full_table_name (Exit status: $dump_exit_status). Continuing..." >&2
    else
        echo "-- Finished dumping data for $full_table_name"
    fi
    echo "" >> "$DUMP_FILE" # Add newline separator
  else
    echo "-- Sample count is 0 for $full_table_name. Skipping data dump."
  fi

done # End of while loop

# --- Debug: Show end of dump file ---
echo "--- Last 20 lines of $DUMP_FILE: ---"
tail -n 20 "$DUMP_FILE"
echo "--- End of dump file preview ---"

# --- Completion ---
echo "Partial dump script finished. File: $DUMP_FILE"
# Optional: turn off trace mode if enabled
# set +x
exit 0
