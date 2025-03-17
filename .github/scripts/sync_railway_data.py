import os
import subprocess
import sys


def get_connection_details() -> tuple[str, str]:
    """Get database connection details from environment variables."""
    railway_url = os.environ.get("RAILWAY_DATABASE_URL")
    local_url = os.environ.get(
        "LOCAL_DB_URL",
        "postgresql://postgres:postgres@localhost:5432/test_db",
    )
    if not railway_url:
        sys.exit("RAILWAY_DATABASE_URL environment variable not set")
    return railway_url, local_url


def main() -> None:
    """Dump the Railway database and restore it to the local database."""
    railway_url, local_url = get_connection_details()

    # Dump the entire Railway database (schema + data)
    if not railway_url.startswith("postgresql://"):
        sys.exit("Invalid railway URL format")
    dump_cmd = ["pg_dump", "--dbname", railway_url]
    try:
        dump_result = subprocess.run(dump_cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as err:
        sys.exit(f"Error running pg_dump: {err.stderr}")

    # Restore dump into local database
    if not railway_url.startswith("postgresql://"):
        sys.exit("Invalid railway URL format")
    restore_cmd = ["psql", "--dbname", railway_url]
    try:
        subprocess.run(restore_cmd, input=dump_result.stdout, text=True, check=True)
    except subprocess.CalledProcessError as err:
        sys.exit(f"Error running psql restore: {err.stderr}")


if __name__ == "__main__":
    main()
