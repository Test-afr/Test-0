#!/usr/bin/env python3

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Get connection details 
railway_url = os.environ.get('RAILWAY_DATABASE_URL')
local_url = os.environ.get('LOCAL_DB_URL', 'postgresql://postgres:postgres@localhost:5432/test_db')

# Debug connection info (without revealing password)
def print_connection_info(url):
    if not url:
        return "None"
    # Hide password in output
    parts = url.split('@')
    if len(parts) > 1:
        auth_parts = parts[0].split(':')
        if len(auth_parts) > 2:
            masked = f"{auth_parts[0]}:****@{parts[1]}"
            return masked
    return "Invalid URL format"

print(f"Railway connection info: {print_connection_info(railway_url)}")
print(f"Local connection info: {print_connection_info(local_url)}")

# Verify we have the necessary environment variables
if not railway_url:
    print("ERROR: RAILWAY_DATABASE_URL environment variable is not set")
    sys.exit(1)

print(f"Connecting to Railway database...")

# Connect to both databases with explicit parameters
try:
    # Parse connection parameters instead of using URL directly
    if railway_url.startswith('postgresql://'):
        # Parse out components in case URL format is causing issues
        # Format: postgresql://username:password@hostname:port/database
        auth = railway_url.split('@')[0].replace('postgresql://', '')
        username = auth.split(':')[0]
        password = auth.split(':')[1]
        
        host_part = railway_url.split('@')[1]
        hostname = host_part.split(':')[0]
        port_db = host_part.split(':')[1]
        port = port_db.split('/')[0]
        database = port_db.split('/')[1].split('?')[0]
        
        print(f"Connecting to: host={hostname}, port={port}, dbname={database}, user={username}")
        
        # Connect with explicit parameters
        railway_conn = psycopg2.connect(
            host=hostname,
            port=port,
            dbname=database,
            user=username,
            password=password
        )
    else:
        # Try direct connection as fallback
        railway_conn = psycopg2.connect(railway_url)
        
    railway_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    railway_cur = railway_conn.cursor()
    print("Successfully connected to Railway database")
except Exception as e:
    print(f"ERROR connecting to Railway database: {e}")
    sys.exit(1)

try:
    # Connect to local database
    local_conn = psycopg2.connect(local_url)
    local_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    local_cur = local_conn.cursor()
    print("Successfully connected to local database")
except Exception as e:
    print(f"ERROR connecting to local database: {e}")
    railway_conn.close()
    sys.exit(1)

# Get all tables from Railway
railway_cur.execute("""
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public'
""")
tables = [row[0] for row in railway_cur.fetchall()]

# For each table, get schema and limited data
for table in tables:
    print(f"Processing table: {table}")
    
    # Drop existing table in local DB
    try:
        local_cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    except Exception as e:
        print(f"Error dropping table {table}: {e}")
    
    # Get column definitions
    railway_cur.execute(f"""
        SELECT column_name, data_type, character_maximum_length 
        FROM information_schema.columns
        WHERE table_name = '{table}'
        ORDER BY ordinal_position
    """)
    columns = railway_cur.fetchall()
    
    # Create table in local DB
    create_table_sql = f"CREATE TABLE {table} ("
    column_defs = []
    
    for col_name, data_type, max_length in columns:
        col_def = f"{col_name} {data_type}"
        if max_length:
            col_def += f"({max_length})"
        column_defs.append(col_def)
    
    create_table_sql += ", ".join(column_defs) + ")"
    
    try:
        local_cur.execute(create_table_sql)
    except Exception as e:
        print(f"Error creating table {table}: {e}")
        continue
    
    # Get data (limited to 500 rows)
    try:
        railway_cur.execute(f"SELECT * FROM {table} LIMIT 500")
        rows = railway_cur.fetchall()
        
        if rows:
            cols = [desc[0] for desc in railway_cur.description]
            placeholders = ",".join(["%s"] * len(cols))
            
            insert_sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
            
            for row in rows:
                try:
                    local_cur.execute(insert_sql, row)
                except Exception as e:
                    print(f"Error inserting row: {e}")
        
        print(f"Copied {len(rows)} rows from {table}")
    except Exception as e:
        print(f"Error fetching data from {table}: {e}")

# Close connections
railway_cur.close()
railway_conn.close()
local_cur.close()
local_conn.close()

print("Database sync completed!")
