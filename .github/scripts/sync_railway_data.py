#!/usr/bin/env python3

import os
import sys
import psycopg2
import contextlib
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Get connection details
railway_url = os.getenv("RAILWAY_DATABASE_URL")
local_url = os.getenv("LOCAL_DB_URL", "postgresql://postgres:postgres@localhost:5432/test_db")

if not railway_url:
    print("Error: RAILWAY_DATABASE_URL is not set.", file=sys.stderr)
    sys.exit(1)

def get_connection(url):
    """Establish a PostgreSQL connection with explicit parameters."""
    try:
        return psycopg2.connect(url)
    except psycopg2.Error as e:
        print(f"Database connection failed: {e}", file=sys.stderr)
        return None

# Connect to Railway and Local databases
railway_conn = get_connection(railway_url)
local_conn = get_connection(local_url)

if not railway_conn or not local_conn:
    sys.exit(1)

railway_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
local_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

railway_cur = railway_conn.cursor()
local_cur = local_conn.cursor()

# Get all tables from Railway
railway_cur.execute("""
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public'
""")
tables = [row[0] for row in railway_cur.fetchall()]

# For each table, get schema and limited data
for table in tables:
    with contextlib.suppress(psycopg2.Error):
        local_cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier(table)))

    # Get column definitions
    railway_cur.execute(sql.SQL("""
        SELECT column_name, data_type, character_maximum_length
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """), [table])

    columns = railway_cur.fetchall()

    # Create table in local DB
    column_defs = [
        f"{col_name} {data_type}({max_length})" if max_length else f"{col_name} {data_type}"
        for col_name, data_type, max_length in columns
    ]
    create_table_sql = sql.SQL("CREATE TABLE {} ({})").format(
        sql.Identifier(table), sql.SQL(", ").join(map(sql.SQL, column_defs))
    )

    try:
        local_cur.execute(create_table_sql)
    except psycopg2.Error:
        continue

    # Get data (limited to 500 rows)
    try:
        railway_cur.execute(sql.SQL("SELECT * FROM {} LIMIT 500").format(sql.Identifier(table)))
        rows = railway_cur.fetchall()

        if rows:
            cols = [desc[0] for desc in railway_cur.description]
            placeholders = sql.SQL(",").join(sql.Placeholder() for _ in cols)

            insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, cols)), placeholders
            )

            with contextlib.suppress(psycopg2.Error):
                local_cur.executemany(insert_sql, rows)
    except psycopg2.Error:
        pass

# Close connections
railway_cur.close()
railway_conn.close()
local_cur.close()
local_conn.close()
