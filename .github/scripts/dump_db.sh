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

#    Use -v ON_ERROR_STOP=1 to catch psql errors early
psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" --field-separator='\t' -c "
  SELECT table_schema, table_name FROM information_schema.tables
  WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    AND table_type = 'BASE TABLE';
" | while IFS=$'\t' read -r schema_name table_name; do
  # Skip potentially empty lines from psql output
  [ -z "$schema_name" ] || [ -z "$table_name" ] && continue

  # 3. Find Primary Key column(s) for ordering this specific table.
  ORDER_COLUMNS=$(psql -v ON_ERROR_STOP=1 -tA "$DATABASE_PUBLIC_URL" -c "
    SELECT string_agg(quote_ident(kcu.column_name), ', ' ORDER BY kcu.ordinal_position)
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu USING (constraint_schema, constraint_name, table_schema, table_name)
    WHERE tc.constraint_type = 'PRIMARY KEY'
      AND tc.table_schema = '$schema_name'
      AND tc.table_name = '$table_name';
  ")
  ORDER_BY_CLAUSE=""
  # Only add ORDER BY if PK exists; otherwise, LIMIT applies arbitrarily
  [ -n "$ORDER_COLUMNS" ] && ORDER_BY_CLAUSE="ORDER BY $ORDER_COLUMNS"
  # --- End of necessary complexity ---

  # 4. Build and execute the COPY command for this table's data
  psql -v ON_ERROR_STOP=1 "$DATABASE_PUBLIC_URL" -c "
    COPY (
      SELECT * FROM \"$schema_name\".\"$table_name\" $ORDER_BY_CLAUSE
      LIMIT ( -- Calculate row count for the percentage for THIS table
          SELECT round(count(*) * $SAMPLE_PERCENTAGE / 100.0)::integer
          FROM \"$schema_name\".\"$table_name\"
      )
    ) TO STDOUT;
  " >> "$DUMP_FILE" # Append data directly to the dump file

done

echo "Partial dump created: $DUMP_FILE"
exit 0
