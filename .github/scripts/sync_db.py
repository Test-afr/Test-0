import os
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()


def get_connection_details() -> tuple[str, str]:
    """Get database connection details from environment variables."""
    railway_url = os.environ.get("DATABASE_PUBLIC_URL")
    local_url = os.environ.get("DEVELOPMENT_DATABASE_URL")
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


def main() -> None:
    """Dump the Railway database and restore it to the local database."""
    railway_url, local_url = get_connection_details()

    reset_local_schema(local_url)

    dump_cmd = ["pg_dump", railway_url]
    try:
        dump_result = subprocess.run(dump_cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as err:
        sys.exit(f"Error running pg_dump: {err.stderr}") #clean pgdump --clean

    restore_cmd = ["psql", local_url]
    try:
        subprocess.run(restore_cmd, input=dump_result.stdout, text=True, check=True)
    except subprocess.CalledProcessError as err:
        sys.exit(f"Error running psql restore: {err.stderr}")
 # add a test

if __name__ == "__main__":
    main()
