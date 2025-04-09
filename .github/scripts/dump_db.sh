#!/bin/bash

SAMPLE_PERCENTAGE=10
DUMP_FILE="${1:-partial_dump.sql}"

[ -z "$DATABASE_URL" ] && echo "::error::DATABASE_URL environment variable is not set." >&2 && exit 1

# Dump schema structure only
pg_dump -s --clean "$DATABASE_URL" > "$DUMP_FILE"

# Get and process user tables
psql -tA "$DATABASE_URL" --field-separator='\t' -c "
  SELECT table_schema, table_name
  FROM information_schema.tables
  WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    AND table_type = 'BASE TABLE';" | while IFS=$'\t' read -r schema_name table_name; do
  
  [ -z "$schema_name" ] || [ -z "$table_name" ] && continue
  # Get primary key columns for ordering
  order_by=$(psql -tA "$DATABASE_URL" -c "
    SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
    FROM information_schema.key_column_usage
    WHERE constraint_schema IN (
      SELECT constraint_schema FROM information_schema.table_constraints 
      WHERE constraint_type = 'PRIMARY KEY' AND table_schema = '$schema_name' AND table_name = '$table_name'
    )
    AND table_schema = '$schema_name'
    AND table_name = '$table_name';")
  
  # Create ORDER BY clause if primary keys exist
  [ -n "$order_by" ] && order_by="ORDER BY $order_by"

  # Dump sample data
  psql "$DATABASE_URL" -c "\copy (
    SELECT * FROM \"$schema_name\".\"$table_name\" $order_by
    LIMIT (SELECT round(count(*) * $SAMPLE_PERCENTAGE / 100.0)::integer FROM \"$schema_name\".\"$table_name\")
  ) TO STDOUT" >> "$DUMP_FILE"
done
