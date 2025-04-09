#!/bin/bash

SAMPLE_PERCENTAGE=10
DUMP_FILE="${1:-partial_dump.sql}"

set -e # Exit on error is crucial for reliability

if [ -z "$DATABASE_PUBLIC_URL" ]; then
  echo "::error::DATABASE_PUBLIC_URL environment variable is not set." >&2
  exit 1
fi

# 1. Dump schema (unchanged)
pg_dump -s --clean --if-exists "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

# 2. Get table list (unchanged, -v ON_ERROR_STOP=1 added for safety)
TABLE_LIST=$(psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" --field-separator='\t' -c "
  SELECT table_schema, table_name FROM information_schema.tables
  WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast') AND table_type = 'BASE TABLE';
")

# 3. Loop through tables
while IFS=$'\t' read -r schema_name table_name; do
  [ -z "$schema_name" ] || [ -z "$table_name" ] && continue

  # --- This block is the necessary addition for ORDERED sampling ---
  # Find Primary Key column(s) for ordering this table.
  ORDER_COLUMNS=$(psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" -c "
    SELECT string_agg(quote_ident(kcu.column_name), ', ' ORDER BY kcu.ordinal_position)
    FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu USING (constraint_schema, constraint_name, table_schema, table_name)
    WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = '$schema_name' AND tc.table_name = '$table_name';
  ")
  ORDER_BY_CLAUSE=""
  [ -n "$ORDER_COLUMNS" ] && ORDER_BY_CLAUSE="ORDER BY $ORDER_COLUMNS"
  # --- End of necessary addition ---

  # Build query: Includes ORDER BY (if possible) and calculates LIMIT
  SQL_QUERY=$(cat <<-EOF
SELECT * FROM "$schema_name"."$table_name" $ORDER_BY_CLAUSE
LIMIT (SELECT round(count(*) * $SAMPLE_PERCENTAGE / 100.0)::integer FROM "$schema_name"."$table_name");
EOF
)

  # Append data using \copy (-v ON_ERROR_STOP=1 added for safety)
  psql -v ON_ERROR_STOP=1 "$DATABASE_PUBLIC_URL" -c "\copy ($SQL_QUERY) TO STDOUT" >> "$DUMP_FILE"

done <<< "$TABLE_LIST" # Use here-string for safety

echo "Partial dump created: $DUMP_FILE"
exit 0
