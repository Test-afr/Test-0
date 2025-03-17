"""Script to sync database schema and limited data from Railway to local PostgreSQL."""

import os
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path


def extract_password(url: str) -> str:
    """Extract password from database URL without exposing the entire URL."""
    try:
        parsed = urllib.parse.urlparse(url)
    except (ValueError, AttributeError):
        return ""
    else:
        return parsed.password or ""


def validate_command(cmd: list[str]) -> bool:
    """Validate that command is in our allowed list."""
    if not cmd:
        return False

    # Whitelist of allowed commands
    allowed_commands = {"pg_dump", "psql"}
    return cmd[0] in allowed_commands


def run_command(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run a command safely without shell=True."""
    # Validate command is in our allowed list
    if not validate_command(cmd):
        msg = f"Unauthorized command: {cmd[0]}"
        raise ValueError(msg)

    return subprocess.run(
        cmd,
        env=env,
        capture_output=capture,
        text=capture,
        check=check,
    )


def sanitize_table_name(name: str) -> str:
    """Sanitize table name to prevent SQL injection."""
    # Only allow alphanumeric and underscores, no special SQL characters
    return "".join(c for c in name if c.isalnum() or c == "_")


# Get database connection strings from environment
source_url = os.environ.get("RAILWAY_DATABASE_URL")
target_url = os.environ.get(
    "LOCAL_DB_URL",
    "postgresql://postgres:postgres@localhost:5432/test_db",
)

# Exit if source URL isn't available
if not source_url:
    sys.exit(1)

# Create a temporary file for the schema dump
with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp:
    temp_file = Path(tmp.name)

try:
    # Extract credentials for environment variables
    source_pw = extract_password(source_url)
    target_pw = extract_password(target_url)

    source_env = os.environ.copy()
    source_env["PGPASSWORD"] = source_pw

    target_env = os.environ.copy()
    target_env["PGPASSWORD"] = target_pw

    # Step 1: Dump schema (no data) from source database
    schema_cmd = [
        "pg_dump",
        "--schema-only",
        "--no-owner",
        "--no-acl",
        source_url,
        "-f",
        str(temp_file),
    ]
    run_command(schema_cmd, env=source_env)

    # Step 2: Reset and restore schema to target database
    reset_cmd = [
        "psql",
        target_url,
        "-c",
        "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
    ]
    run_command(reset_cmd, env=target_env)

    restore_cmd = ["psql", target_url, "-f", str(temp_file)]
    run_command(restore_cmd, env=target_env)

    # Step 3: Get list of tables
    get_tables_cmd = [
        "psql",
        source_url,
        "-t",
        "-c",
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public';",
    ]
    result = run_command(get_tables_cmd, env=source_env, capture=True)

    tables = [table.strip() for table in result.stdout.splitlines() if table.strip()]

    # Step 4: Copy limited data for each table
    row_limit = 100
    for table in tables:
        # Apply proper table name sanitization
        safe_table = sanitize_table_name(table)
        if not safe_table:
            continue

        # Using two separate temporary files for safer data transfer
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as export_file:
            export_path = Path(export_file.name)

            # Export data to file instead of piping directly
            export_cmd = [
                "psql",
                source_url,
                "-c",
                f"\\COPY (SELECT * FROM \"{safe_table}\" "
                f"LIMIT {row_limit}) TO '{export_path}' CSV HEADER",

            ]
            run_command(export_cmd, env=source_env)

            # Import data from file
            import_cmd = [
                "psql",
                target_url,
                "-c",
                f"\\COPY \"{safe_table}\" FROM '{export_path}' CSV HEADER",
            ]
            import_result = run_command(import_cmd, env=target_env, check=False)

            # Clean up temp file
            export_path.unlink()

            if import_result.returncode != 0:
                pass

except subprocess.CalledProcessError:
    sys.exit(1)
except (ValueError, KeyboardInterrupt):
    sys.exit(1)
finally:
    # Clean up
    if temp_file.exists():
        temp_file.unlink()
