#!/bin/bash

# --- Configuration ---
# Default sample percentage if the environment variable is not set
SAMPLE_PERCENTAGE=${SAMPLE_PERCENTAGE:-10}
# Output dump file name (can be overridden by the first script argument)
DUMP_FILE="${1:-partial_dump.sql}"

# --- Strict Mode ---
# Exit immediately if a command exits with a non-zero status.
# Treat unset variables as an error when substituting.
# Pipelines return the exit status of the last command to exit non-zero.
set -euo pipefail

# --- Check Environment Variable ---
if [ -z "${DATABASE_PUBLIC_URL:-}" ]; then
  echo "::error::DATABASE_PUBLIC_URL environment variable is not set." >&2
  exit 1
fi

echo "Creating partial dump file: $DUMP_FILE"
echo "Sampling percentage: ${SAMPLE_PERCENTAGE}%"
# Ensure percentage is an integer
if ! [[ "$SAMPLE_PERCENTAGE" =~ ^[0-9]+$ ]] || [ "$SAMPLE_PERCENTAGE" -lt 0 ] || [ "$SAMPLE_PERCENTAGE" -gt 100 ]; then
    echo "::error:: SAMPLE_PERCENTAGE must be an integer between 0 and 100." >&2
    exit 1
fi


# --- Schema Dump ---
echo "-- Dumping schema structure..."
# -s: schema only, --clean: add drop commands, --if-exists: add IF EXISTS to drop
pg_dump -s --clean --if-exists "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

# --- Data Dump Header ---
echo "
--
-- Data dump (approximately first ${SAMPLE_PERCENTAGE}% of rows per table)
-- Using LIMIT without ORDER BY for sampling.
--
" >> "$DUMP_FILE"

# --- Get Table List ---
# Query to select user tables (excluding system schemas)
TABLE_LIST_QUERY="
  SELECT table_schema, table_name
  FROM information_schema.tables
  WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    AND table_type = 'BASE TABLE';
"

# --- Data Sampling Loop ---
echo "-- Dumping sampled data using COPY format..."
# Use psql to get the list of tables, then loop through them
# -t: tuples only (no headers), -A: unaligned (removes padding)
# IFS=$'\t': set Internal Field Separator to tab for read
psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" --field-separator='\t' -c "$TABLE_LIST_QUERY" | while IFS=$'\t' read -r schema_name table_name; do
  # Skip potentially empty lines read from psql output
  if [ -z "$schema_name" ] || [ -z "$table_name" ]; then
    continue
  fi

  # Fully qualified table name for use in queries
  full_table_name="\"$schema_name\".\"$table_name\""
  echo "-- Processing table: $full_table_name"

  # Get total row count for the table
  ROW_COUNT_STR=$(psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" -c "SELECT COUNT(*) FROM $full_table_name;")

  # Validate row count is a number
   if ! [[ "$ROW_COUNT_STR" =~ ^[0-9]+$ ]]; then
      echo "::warning:: Could not get valid row count for $full_table_name. Received '$ROW_COUNT_STR'. Skipping data dump." >&2
      continue
   fi
   ROW_COUNT=$((ROW_COUNT_STR)) # Convert to integer

  if [ "$ROW_COUNT" -eq 0 ]; then
    echo "-- Table $full_table_name is empty. Skipping."
    continue
  fi

  # Calculate the number of rows to sample
  # Use integer arithmetic. Add 99 before dividing by 100 for ceiling effect.
  SAMPLE_COUNT=$(( (ROW_COUNT * SAMPLE_PERCENTAGE + 99) / 100 ))

  # Ensure at least 1 row is selected if percentage > 0 and table is not empty
  if [ "$SAMPLE_PERCENTAGE" -gt 0 ] && [ "$SAMPLE_COUNT" -eq 0 ] && [ "$ROW_COUNT" -gt 0 ]; then
      SAMPLE_COUNT=1
  fi

  # Only proceed if there are rows to sample
  if [ "$SAMPLE_COUNT" -gt 0 ]; then
    echo "-- Sampling first $SAMPLE_COUNT rows from $full_table_name ($ROW_COUNT total)" >> "$DUMP_FILE"

    # Append COPY command header to the dump file
    echo "COPY $full_table_name FROM STDIN;" >> "$DUMP_FILE"

    # Execute the query to select the first SAMPLE_COUNT rows and COPY them to STDOUT
    # Pipe the output directly into the dump file
    # -t: tuples only is sufficient here, COPY TO STDOUT handles formatting
    psql -v ON_ERROR_STOP=1 -t "$DATABASE_PUBLIC_URL" -c "COPY (SELECT * FROM $full_table_name LIMIT $SAMPLE_COUNT) TO STDOUT;" >> "$DUMP_FILE"

    # Append COPY command terminator and a newline
    echo "\." >> "$DUMP_FILE"
    echo "" >> "$DUMP_FILE"
  else
     echo "-- Sample count is 0 for $full_table_name. Skipping data dump."
  fi

done # End of while loop reading tables

# --- Completion ---
echo "Partial dump created successfully: $DUMP_FILE"
exit 0
