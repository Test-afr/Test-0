#!/bin/bash

SAMPLE_PERCENTAGE=10
DUMP_FILE="${1:-partial_dump.sql}"

set -e

[ -z "$DATABASE_PUBLIC_URL" ] && exit 1

# Dump schema only
pg_dump -s --clean --if-exists "$DATABASE_PUBLIC_URL" > "$DUMP_FILE"

# Get all tables
psql -tA "$DATABASE_PUBLIC_URL" -c "
  SELECT table_schema, table_name FROM information_schema.tables
  WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
" | while IFS='|' read -r schema_name table_name; do
  [ -z "$table_name" ] && continue
  
  # Get sample directly using SQL
  psql "$DATABASE_PUBLIC_URL" -c "
    COPY (
      SELECT * FROM \"$schema_name\".\"$table_name\" 
      ORDER BY random() 
      LIMIT GREATEST(1, (SELECT count(*) * $SAMPLE_PERCENTAGE / 100 FROM \"$schema_name\".\"$table_name\"))
    ) TO STDOUT WITH CSV HEADER
  " > temp_data.csv
  
  # Skip if file is empty (just header)
  if [ $(wc -l < temp_data.csv) -gt 1 ]; then
    # Add SQL commands to the dump file
    echo "" >> "$DUMP_FILE"
    echo "-- Data for table $schema_name.$table_name" >> "$DUMP_FILE"
    echo "COPY \"$schema_name\".\"$table_name\" FROM stdin;" >> "$DUMP_FILE"
    
    # Skip header and convert to PostgreSQL copy format
    tail -n +2 temp_data.csv | sed 's/\\/\\\\/g' >> "$DUMP_FILE"
    
    # End COPY command
    echo "\\." >> "$DUMP_FILE"
    echo "" >> "$DUMP_FILE"
  fi
  
  rm -f temp_data.csv
done
