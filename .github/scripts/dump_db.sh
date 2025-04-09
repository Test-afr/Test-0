#!/bin/bash
set -e
set -x # Print commands

# ... rest of script ...

# Add -v ON_ERROR_STOP=1 here:
psql -v ON_ERROR_STOP=1 -tA "$DATABASE_URL" --field-separator='\t' -c "..." | while ...

  # Add -v ON_ERROR_STOP=1 here:
  order_by=$(psql -v ON_ERROR_STOP=1 -tA "$DATABASE_URL" -c "...")

  # Add -v ON_ERROR_STOP=1 here:
  psql -v ON_ERROR_STOP=1 "$DATABASE_URL" -c "\copy (...) TO STDOUT" >> "$DUMP_FILE"
done
