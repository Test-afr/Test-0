#!/usr/bin/env python3

import os
import sys
import subprocess
import tempfile

# Get database connection strings from environment
source_url = os.environ.get("RAILWAY_DATABASE_URL")
target_url = os.environ.get("LOCAL_DB_URL", "postgresql://postgres:postgres@localhost:5432/test_db")

# Exit if source URL isn't available
if not source_url:
    print("ERROR: RAILWAY_DATABASE_URL is not set")
    sys.exit(1)

# Create a temporary file for the schema dump
temp_file = tempfile.mktemp(suffix='.sql')

try:
    # Step 1: Dump schema (no data) from source database
    print("Exporting schema from source database...")
    schema_cmd = f'PGPASSWORD="{source_url.split(":", 2)[2].split("@")[0]}" pg_dump --schema-only --no-owner --no-acl {source_url} -f {temp_file}'
    subprocess.run(schema_cmd, shell=True, check=True)
    
    # Step 2: Reset and restore schema to target database
    print("Restoring schema to target database...")
    reset_cmd = f'PGPASSWORD="{target_url.split(":", 2)[2].split("@")[0]}" psql {target_url} -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'
    subprocess.run(reset_cmd, shell=True, check=True)
    
    restore_cmd = f'PGPASSWORD="{target_url.split(":", 2)[2].split("@")[0]}" psql {target_url} -f {temp_file}'
    subprocess.run(restore_cmd, shell=True, check=True)
    
    # Step 3: Get list of tables
    print("Getting table list...")
    get_tables_cmd = f'PGPASSWORD="{source_url.split(":", 2)[2].split("@")[0]}" psql {source_url} -t -c "SELECT tablename FROM pg_tables WHERE schemaname = \'public\';"'
    result = subprocess.run(get_tables_cmd, shell=True, capture_output=True, text=True, check=True)
    
    tables = [table.strip() for table in result.stdout.splitlines() if table.strip()]
    
    # Step 4: Copy limited data for each table
    row_limit = 500
    for table in tables:
        print(f"Copying data for table: {table} (max {row_limit} rows)")
        
        # Export data from source and import to target in one pipeline
        copy_cmd = (
            f'PGPASSWORD="{source_url.split(":", 2)[2].split("@")[0]}" psql {source_url} -c '
            f'"\\COPY (SELECT * FROM {table} LIMIT {row_limit}) TO STDOUT CSV HEADER" | '
            f'PGPASSWORD="{target_url.split(":", 2)[2].split("@")[0]}" psql {target_url} -c '
            f'"\\COPY {table} FROM STDIN CSV HEADER"'
        )
        
        # We don't use check=True here because some tables might fail but we want to continue
        result = subprocess.run(copy_cmd, shell=True)
        if result.returncode != 0:
            print(f"  Warning: Could not copy data for table {table}")
    
    print("Database sync completed successfully")
    
except subprocess.CalledProcessError as e:
    print(f"Error: Command failed with code {e.returncode}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
finally:
    # Clean up
    if os.path.exists(temp_file):
        os.unlink(temp_file)
