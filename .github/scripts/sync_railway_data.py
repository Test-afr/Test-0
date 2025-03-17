# .github/scripts/sync_railway_data.py
#!/usr/bin/env python3

import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Connection details from environment
railway_url = os.environ.get('RAILWAY_DATABASE_URL')
local_url = os.environ.get('LOCAL_DB_URL')

print("Syncing database schema and test data...")

# Connect to both databases
railway_conn = psycopg2.connect(railway_url)
railway_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
railway_cur = railway_conn.cursor()

local_conn = psycopg2.connect(local_url)
local_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
local_cur = local_conn.cursor()

# Get all tables from Railway
railway_cur.execute("""
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public'
""")
tables = [row[0] for row in railway_cur.fetchall()]

# For each table, get schema and sample data
for table in tables:
    print(f"Processing table: {table}")
    
    # Get table schema
    railway_cur.execute(f"""
        SELECT column_name, data_type, character_maximum_length
        FROM information_schema.columns 
        WHERE table_name = '{table}'
    """)
    columns = railway_cur.fetchall()
    
    # Create table in local DB
    create_table_sql = f"CREATE TABLE IF NOT EXISTS {table} ("
    column_defs = []
    
    for col_name, data_type, max_length in columns:
        col_def = f"{col_name} {data_type}"
        if max_length:
            col_def += f"({max_length})"
        column_defs.append(col_def)
    
    create_table_sql += ", ".join(column_defs) + ")"
    
    try:
        local_cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        local_cur.execute(create_table_sql)
    except Exception as e:
        print(f"Error creating table {table}: {e}")
    
    # Copy up to 500 rows of data
    railway_cur.execute(f"SELECT * FROM {table} LIMIT 500")
    rows = railway_cur.fetchall()
    
    if rows:
        cols = [desc[0] for desc in railway_cur.description]
        placeholders = ",".join(["%s"] * len(cols))
        
        insert_sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
        
        try:
            for row in rows:
                local_cur.execute(insert_sql, row)
        except Exception as e:
            print(f"Error inserting data into {table}: {e}")

# Close connections
railway_cur.close()
railway_conn.close()
local_cur.close()
local_conn.close()

print("Database sync completed!")
