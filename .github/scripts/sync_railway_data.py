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
        ["pg_dump", "--schema-only", "--no-owner", source_url, "-f", temp_schema],
        check=True,
        encoding="utf-8",  # Fix encoding warning
    )

    subprocess.run(
        ["psql", target_url, "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"],
        check=True,
        encoding="utf-8",
    )

    subprocess.run(["psql", target_url, "-f", temp_schema], check=True, encoding="utf-8")

    # 2. Disable foreign key constraints in target database
    subprocess.run(
        ["psql", target_url, "-c", "SET session_replication_role = 'replica';"],
        check=True,
        encoding="utf-8",
    )

    # 3. Get all tables
    tables_query = (
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
    )
    result = subprocess.run(
        ["psql", source_url, "-t", "-c", tables_query],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    tables = [t.strip() for t in result.stdout.splitlines() if t.strip()]

    # 4. Import data with foreign keys disabled
    for table in tables:
        subprocess.run(
            ["pg_dump", "--data-only", "--table", f"public.{table}", "--rows=100", source_url],
            stdout=subprocess.PIPE,
            check=True,
            encoding="utf-8",
        ).stdout | subprocess.run(
            ["psql", target_url], stdin=subprocess.PIPE, check=False, encoding="utf-8",
        )

    # 5. Re-enable foreign key constraints
    subprocess.run(
        ["psql", target_url, "-c", "SET session_replication_role = 'origin';"],
        check=True,
        encoding="utf-8",
    )

finally:
    if os.path.exists(temp_schema):
        os.unlink(temp_schema)
