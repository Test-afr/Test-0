import os
import subprocess
import sys

import psycopg2

# make it a script .sh
# pg cron -> try and count number of commits
# sync db


def get_connection_details() -> tuple[str, str]:
    """Get database connection details from environment variables."""
    railway_url = os.environ.get("RAILWAY_DATABASE_URL")
    local_url = os.environ.get("TEST_DATABASE_URL")
    if not railway_url:
        sys.exit("RAILWAY_DATABASE_URL environment variable not set")
    if not local_url:
        sys.exit("TEST_DATABASE_URL environment variable not set")

    return railway_url, local_url


def reset_local_schema(local_url: str) -> None:
    """Reset the local database's public schema to ensure a clean restoration."""
    reset_cmd = [
        "psql",
        local_url,
        "-c",
        "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
    ]
    try:
        subprocess.run(reset_cmd, text=True, capture_output=True, check=True)
    except subprocess.CalledProcessError as err:
        sys.exit(f"Error resetting local schema: {err.stderr}")


def is_public_schema_empty(local_url: str) -> bool:
    """Check if the local database public schema is empty.

    Uses Postgres system catalogs to determine if any non-system
    tables exist in the 'public' schema.
    """
    try:
        conn = psycopg2.connect(local_url)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)
                FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
                  AND tablename NOT LIKE 'pg_%'
                  AND tablename NOT LIKE 'sql_%';
                """,
            )
            count = cur.fetchone()[0]
    except psycopg2.Error:
        return False
    else:
        conn.close()
        return count == 0


def main() -> None:
    """Dump the Railway database and restore it to the local database."""
    railway_url, local_url = get_connection_details()

    # Determine if we're running in CI by checking the "CI" env variable.
    ci_env = os.environ.get("CI") is not None

    # In local runs (not CI) we try to avoid syncing when the schema is not empty.
    if not ci_env and not is_public_schema_empty(local_url):
        sys.exit(0)

    # For CI (or if the local DB is empty) reset the schema and perform syncing.
    reset_local_schema(local_url)

    dump_cmd = ["pg_dump", railway_url]
    try:
        dump_result = subprocess.run(dump_cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as err:
        sys.exit(f"Error running pg_dump: {err.stderr}")

    restore_cmd = ["psql", local_url]
    try:
        subprocess.run(restore_cmd, input=dump_result.stdout, text=True, check=True)
    except subprocess.CalledProcessError as err:
        sys.exit(f"Error running psql restore: {err.stderr}")


if __name__ == "__main__":
    main()
