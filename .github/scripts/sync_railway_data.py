import contextlib
import os
import sys

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, connection, cursor


def get_connection_details() -> tuple[str, str]:
    """Get database connection details from environment variables."""
    railway_url = os.environ.get("RAILWAY_DATABASE_URL")
    local_url = os.environ.get(
        "LOCAL_DB_URL",
        "postgresql://postgres:postgres@localhost:5432/test_db",
    )
    return railway_url, local_url


def connect_to_railway(url: str) -> tuple[connection | None, cursor | None]:
    """Connect to Railway database."""
    try:
        if url.startswith("postgresql://"):
            # Parse out components
            auth = url.split("@")[0].replace("postgresql://", "")
            username = auth.split(":")[0]
            password = auth.split(":")[1]

            host_part = url.split("@")[1]
            hostname = host_part.split(":")[0]
            port_db = host_part.split(":")[1]
            port = port_db.split("/")[0]
            database = port_db.split("/")[1].split("?")[0]

            conn = psycopg2.connect(
                host=hostname,
                port=port,
                dbname=database,
                user=username,
                password=password,
            )
        else:
            conn = psycopg2.connect(url)
    except psycopg2.Error:
        return None, None
    else:
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        return conn, cur


def connect_to_local(url: str) -> tuple[connection | None, cursor | None]:
    """Connect to local database."""
    try:
        conn = psycopg2.connect(url)
    except psycopg2.Error:
        return None, None
    else:
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        return conn, cur


def get_tables(cur: cursor) -> list[str]:
    """Get all tables from the database."""
    cur.execute(
        """
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
        """,
    )
    return [row[0] for row in cur.fetchall()]


def get_column_definitions(cur: cursor, table: str) -> list[tuple]:
    """Get column definitions for a table."""
    cur.execute(
        "SELECT column_name, data_type, character_maximum_length "
        "FROM information_schema.columns "
        "WHERE table_name = %s "
        "ORDER BY ordinal_position",
        (table,),
    )
    return cur.fetchall()


def create_table_sql(table: str, columns: list[tuple]) -> str:
    """Generate CREATE TABLE SQL statement."""
    create_sql = f"CREATE TABLE {table} ("
    column_defs = []

    for col_name, data_type, max_length in columns:
        col_def = f"{col_name} {data_type}"
        if max_length:
            col_def += f"({max_length})"
        column_defs.append(col_def)

    create_sql += ", ".join(column_defs) + ")"
    return create_sql


def copy_table_data(source_cur: cursor, dest_cur: cursor, table: str) -> None:
    """Copy data from source to destination."""
    try:
        query = sql.SQL("SELECT * FROM {} LIMIT 500").format(sql.Identifier(table))
        source_cur.execute(query)
        rows = source_cur.fetchall()

        if rows:
            cols = [desc[0] for desc in source_cur.description]
            placeholders = sql.SQL(",").join(sql.Placeholder() for _ in cols)
            insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(table),
                sql.SQL(",").join(map(sql.Identifier, cols)),
                placeholders,
            )
            for row in rows:
                with contextlib.suppress(psycopg2.Error):
                    dest_cur.execute(insert_sql, row)
    except psycopg2.Error:
        pass


def close_connections(*connections: connection) -> None:
    """Close database connections."""
    for conn in connections:
        if conn:
            with contextlib.suppress(psycopg2.Error):
                conn.close()


def main() -> None:
    """Copy database schema and data."""
    railway_url, local_url = get_connection_details()

    # Verify we have the necessary environment variables
    if not railway_url:
        sys.exit(1)

    # Connect to databases
    railway_conn, railway_cur = connect_to_railway(railway_url)
    if not railway_conn or not railway_cur:
        sys.exit(1)

    local_conn, local_cur = connect_to_local(local_url)
    if not local_conn or not local_cur:
        close_connections(railway_conn)
        sys.exit(1)

    try:
        # Get all tables from Railway
        tables = get_tables(railway_cur)

        # For each table, get schema and limited data
        for table in tables:
            # Drop existing table in local DB
            with contextlib.suppress(psycopg2.Error):
                local_cur.execute(
                    sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier(table)),
                )

            # Get column definitions and create table
            columns = get_column_definitions(railway_cur, table)
            create_sql = create_table_sql(table, columns)

            try:
                local_cur.execute(create_sql)
            except psycopg2.Error:
                continue

            # Copy data
            copy_table_data(railway_cur, local_cur, table)
    finally:
        # Clean up connections
        close_connections(railway_conn, local_conn)


if __name__ == "__main__":
    main()
