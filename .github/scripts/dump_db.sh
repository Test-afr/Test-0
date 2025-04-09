#!/bin/bash

SAMPLE_PERCENTAGE=10
DUMP_FILE="${1:-partial_dump.sql}" # Use first argument or default

set -e # Exit on error

# Ensure DATABASE_URL is set (should be provided by the workflow environment)
if [ -z "$DATABASE_URL" ]; then
  echo "::error::DATABASE_URL environment variable is not set." >&2
  exit 1
fi

# 1. Dump schema structure only
# Use --if-exists with --clean for robustness
pg_dump -s --clean --if-exists "$DATABASE_URL" > "$DUMP_FILE"

# 2. Get list of user tables (schema.table)
# Use -v ON_ERROR_STOP=1 for psql commands
TABLE_LIST=$(psql -v ON_ERROR_STOP=1 -tA "$DATABASE_URL" --field-separator='\t' -c "
  SELECT table_schema, table_name
  FROM information_schema.tables
  WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    AND table_type = 'BASE TABLE';
")

# Check if table list is empty (optional but good practice)
if [ -z "$TABLE_LIST" ]; then
  echo "::warning::No user tables found to dump data from."
  # Exit gracefully or continue, depending on desired behavior
  echo "Partial dump created (schema only): $DUMP_FILE"
  exit 0
fi

# 3. Loop through tables and dump ordered percentage of data
while IFS=$'\t' read -r schema_name table_name; do
  # Skip potentially empty lines
  [ -z "$schema_name" ] || [ -z "$table_name" ] && continue

  # Find Primary Key column(s) for deterministic ordering using JOIN
  ORDER_COLUMNS=$(psql -v ON_ERROR_STOP=1 -tA "$DATABASE_URL" -c "
    SELECT string_agg(quote_ident(kcu.column_name), ', ' ORDER BY kcu.ordinal_position)
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu USING (constraint_schema, constraint_name, table_schema, table_name)
    WHERE tc.constraint_type = 'PRIMARY KEY'
      AND tc.table_schema = '$schema_name'
      AND tc.table_name = '$table_name';
  ")

  ORDER_BY_CLAUSE=""
  if [ -n "$ORDER_COLUMNS" ]; then
    ORDER_BY_CLAUSE="ORDER BY $ORDER_COLUMNS"
  else
     echo "::warning:: No PRIMARY KEY found for \"$schema_name\".\"$table_name\". Order for LIMIT is not guaranteed." >&2
  fi

  # Build query: Select all columns, order by PK (if found), limit to N%
  SQL_QUERY=$(cat <<-EOF
SELECT *
FROM "$schema_name"."$table_name"
$ORDER_BY_CLAUSE
LIMIT ( -- Calculate row count for the percentage
    SELECT round(count(*) * $SAMPLE_PERCENTAGE / 100.0)::integer
    FROM "$schema_name"."$table_name"
);
EOF
)

  # Append data using \copy
  # Use -v ON_ERROR_STOP=1 here too
  psql -v ON_ERROR_STOP=1 "$DATABASE_URL" -c "\copy ($SQL_QUERY) TO STDOUT" >> "$DUMP_FILE"

done <<< "$TABLE_LIST" # Feed table list using here-string

echo "Partial dump created: $DUMP_FILE"
exit 0
