#!/usr/bin/env python3

import contextlib
import os
import sys

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Get connection details
railway_url = os.environ.get("RAILWAY_DATABASE_URL")
local_url = os.environ.get("LOCAL_DB_URL", "postgresql://postgres:postgres@localhost:5432/test_db")

# Verify we have the necessary environment variables
if not railway_url:
    sys.exit(1)

# Connect to databases - keeping the manual URL parsing that works with Railway
try:
    # Parse connection parameters using the working method
    if railway_url.startswith("postgresql://"):
        auth = railway_url.split("@")[0].replace("postgresql://", "")
        username = auth.split(":")[0]
        password = auth.split(":")[1]

        host_part = railway_url.split("@")[1]
        hostname = host_part.split(":")[0]
        port_db = host_part.split(":")[1]
        port = port_db.split("/")[0]
        database = port_db.split("/")[1].split("?")[0]

        railway_conn = psycopg2.connect(
            host=hostname,
            port=port,
            dbname=database,
            user=username,
            password=password,
        )
    else:
        railway_conn = psycopg2.connect(railway_url)

    railway_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    # Connect to local database
    local_conn = psycopg2.connect(local_url)
    local_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    # Create cursors
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
        # Drop existing table in local DB
        local_cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

        # Get column definitions
        railway_cur.execute(f"""
            SELECT column_name, data_type, character_maximum_length,
                   is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = '{table}'
            ORDER BY ordinal_position
        """)
        columns = railway_cur.fetchall()

        # Create table in local DB with slightly more schema information
        create_table_sql = f"CREATE TABLE {table} ("
        column_defs = []

        for col_name, data_type, max_length, is_nullable, default in columns:
            col_def = f"{col_name} {data_type}"
            if max_length:
                col_def += f"({max_length})"

            # Add nullability constraint
            if is_nullable == "NO":
                col_def += " NOT NULL"

            # Add default value if present
            if default:
                col_def += f" DEFAULT {default}"

            column_defs.append(col_def)

        create_table_sql += ", ".join(column_defs) + ")"

        try:
            local_cur.execute(create_table_sql)
        except Exception:
            continue

        # Get data (limited to 500 rows) using the same method as original
        try:
            railway_cur.execute(f"SELECT * FROM {table} LIMIT 500")
            rows = railway_cur.fetchall()

            if rows:
                cols = [desc[0] for desc in railway_cur.description]
                placeholders = ",".join(["%s"] * len(cols))

                insert_sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"

                # Batch inserts for better performance
                batch_size = 100
                for i in range(0, len(rows), batch_size):
                    batch = rows[i : i + batch_size]
                    with local_conn.cursor() as batch_cur:
                        for row in batch:
                            with contextlib.suppress(Exception):
                                batch_cur.execute(insert_sql, row)
        except Exception:
            pass

    # Success message

except Exception:
    sys.exit(1)
finally:
    # Clean up connections in a finally block to ensure they close
    for conn in [c for c in (locals().get("railway_conn"), locals().get("local_conn")) if c]:
        with contextlib.suppress(Exception):
            conn.close()
