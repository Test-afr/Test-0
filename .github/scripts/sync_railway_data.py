"""Script to sync database schema and limited data from Railway to local PostgreSQL."""

import os
import subprocess
import sys
import tempfile

# Get database URLs
source_url = os.environ.get("RAILWAY_DATABASE_URL")
target_url = os.environ.get(
    "LOCAL_DB_URL", "postgresql://postgres:postgres@localhost:5432/test_db",
)

if not source_url:
    sys.exit(1)

# Create temp file for schema
temp_schema = tempfile.mktemp(suffix=".sql")

try:
    # 1. Export & import schema
    subprocess.run(
        ["pg_dump", "--schema-only", "--no-owner", source_url, "-f", temp_schema], check=True,
    )
    subprocess.run(
        ["psql", target_url, "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"], check=True,
    )
    subprocess.run(["psql", target_url, "-f", temp_schema], check=True)

    # 2. Export core tables first (reference tables)
    tables_query = """SELECT tablename FROM pg_tables WHERE schemaname = 'public'
                      ORDER BY tablename IN (SELECT ccu.table_name FROM information_schema.table_constraints tc
                      JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                      WHERE tc.constraint_type = 'FOREIGN KEY') ASC;"""

    tables = subprocess.run(
        ["psql", source_url, "-t", "-c", tables_query], capture_output=True, text=True, check=True,
    ).stdout.splitlines()

    # 3. Import data with dependency handling
    for table in [t.strip() for t in tables if t.strip()]:
        subprocess.run(
            [
                "pg_dump",
                "--data-only",
                "--disable-triggers",
                "--table",
                f"public.{table}",
                "--rows=100",
                source_url,
            ],
            stdout=subprocess.PIPE,
            check=True,
        ).stdout | subprocess.run(["psql", target_url], stdin=subprocess.PIPE, check=False)

finally:
    if os.path.exists(temp_schema):
        os.unlink(temp_schema)
