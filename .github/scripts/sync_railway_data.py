#!/usr/bin/env python3

import os
import sys
import contextlib
from urllib.parse import urlparse

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Get connection details
railway_url = os.environ.get("RAILWAY_DATABASE_URL")
local_url = os.environ.get("LOCAL_DB_URL", "postgresql://postgres:postgres@localhost:5432/test_db")

# Exit if required environment variables are missing
if not railway_url:
    sys.exit(1)

# Connect to databases using context managers to ensure proper cleanup
try:
    with psycopg2.connect(railway_url) as railway_conn, \
         psycopg2.connect(local_url) as local_conn:
        
        # Set isolation level to AUTOCOMMIT for both connections
        railway_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        local_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        with railway_conn.cursor() as railway_cur, \
             local_conn.cursor() as local_cur:
            
            # Get all tables from Railway
            railway_cur.execute("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
            """)
            tables = [row[0] for row in railway_cur.fetchall()]
            
            for table in tables:
                # Drop existing table in local DB if it exists
                local_cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                
                # Create table in local DB using PostgreSQL's built-in functionality
                # First get table definition
                railway_cur.execute(f"""
                    SELECT 
                        pg_get_createtable_command('{table}'::regclass)
                """)
                create_table_sql = railway_cur.fetchone()[0]
                
                # Create the table using the exact schema from source
                try:
                    local_cur.execute(create_table_sql)
                except Exception as e:
                    print(f"Error creating table {table}: {e}")
                    continue
                
                # Copy data using PostgreSQL's COPY command
                try:
                    # First, get column names
                    railway_cur.execute(f"""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = '{table}'
                        ORDER BY ordinal_position
                    """)
                    columns = [row[0] for row in railway_cur.fetchall()]
                    columns_str = ', '.join(columns)
                    
                    # Use COPY to efficiently transfer data (limited to 500 rows)
                    railway_cur.execute(f"""
                        CREATE TEMPORARY TABLE temp_export AS 
                        SELECT * FROM {table} LIMIT 500
                    """)
                    
                    railway_cur.execute(f"""
                        COPY (SELECT * FROM temp_export) TO STDOUT WITH CSV
                    """)
                    
                    # Copy data from Railway to local
                    local_cur.copy_expert(f"""
                        COPY {table} ({columns_str}) FROM STDIN WITH CSV
                    """, railway_cur.connection)
                    
                except Exception as e:
                    print(f"Error copying data for table {table}: {e}")
                    
except Exception as e:
    print(f"Connection error: {e}")
    sys.exit(1)

print("Migration completed")
