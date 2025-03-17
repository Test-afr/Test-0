import os

import psycopg2
import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Always use the local database for testing
LOCAL_DB_URL = os.getenv("LOCAL_DB_URL", "postgresql://postgres:postgres@localhost:5432/test_db")


@pytest.fixture
def db_connection() -> str:
    """Fixture that provides a database connection and handles cleanup."""
    # Set up connection
    conn = psycopg2.connect(LOCAL_DB_URL)
    cursor = conn.cursor()

    # Provide both connection and cursor to the test
    yield (conn, cursor)

    # Tear down/cleanup (runs after test completes)
    cursor.close()
    conn.close()


def test_database_connection(db_connection: str) -> None:
    """Test database connection to local database."""
    _, cursor = db_connection

    # Try executing a simple query
    cursor.execute("SELECT 1")
    result = cursor.fetchone()[0]

    assert result == 1


def test_tables_exist(db_connection: str) -> None:
    """Test that our tables exist in local database."""
    _, cursor = db_connection

    # Check all tables
    for table in ["users", "items", "orders"]:
        cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = '{table}'
            );
        """)
        table_exists = cursor.fetchone()[0]
        assert table_exists is True, f"Table '{table}' does not exist"


def test_sample_data(db_connection: str) -> None:
    """Test that sample data exists in local database."""
    _, cursor = db_connection

    # Check data in each table
    for table in ["users", "items", "orders"]:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        assert count > 0, f"No data found in table '{table}'"


def test_users_columns_structure(db_connection: str) -> None:
    """Test that the users table has the correct columns in order."""
    _, cursor = db_connection
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'users'
        ORDER BY ordinal_position
    """)
    columns = [row[0] for row in cursor.fetchall()]
    expected = ["id", "username", "email", "created_at"]
    assert columns == expected, f"Users table columns mismatch. Got {columns}"


def test_items_columns_structure(db_connection: str) -> None:
    """Test that the items table has the correct columns in order."""
    _, cursor = db_connection
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'items'
        ORDER BY ordinal_position
    """)
    columns = [row[0] for row in cursor.fetchall()]
    expected = ["id", "name", "description", "price", "category", "in_stock", "owner_id"]
    assert columns == expected, f"Items table columns mismatch. Got {columns}"


def test_orders_columns_structure(db_connection: str) -> None:
    """Test that the orders table has the correct columns in order."""
    _, cursor = db_connection
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'orders'
        ORDER BY ordinal_position
    """)
    columns = [row[0] for row in cursor.fetchall()]
    expected = [
        "id",
        "user_id",
        "item_id",
        "quantity",
        "total_price",
        "order_date",
        "status",
    ]
    assert columns == expected, f"Orders table columns mismatch. Got {columns}"


def test_items_foreign_key(db_connection: str) -> None:
    """Test that the items table has a foreign key on owner_id referencing users(id)."""
    _, cursor = db_connection
    cursor.execute("""
        SELECT kcu.column_name, ccu.table_name, ccu.column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
          ON ccu.constraint_name = tc.constraint_name
        WHERE tc.table_name = 'items' AND tc.constraint_type = 'FOREIGN KEY'
    """)
    fk = cursor.fetchall()
    # Expect a foreign key on owner_id referencing users(id)
    assert any(row[0] == "owner_id" and row[1] == "users" and row[2] == "id" for row in fk), (
        "Foreign key for items.owner_id referencing users(id) is missing"
    )


def test_orders_foreign_keys(db_connection: str) -> None:
    """Test that the orders table has foreign keys on user_id and item_id."""
    _, cursor = db_connection
    cursor.execute("""
        SELECT kcu.column_name, ccu.table_name, ccu.column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
          ON ccu.constraint_name = tc.constraint_name
        WHERE tc.table_name = 'orders' AND tc.constraint_type = 'FOREIGN KEY'
    """)
    fks = cursor.fetchall()
    fk_columns = {(row[0], row[1], row[2]) for row in fks}
    expected_fk_user = ("user_id", "users", "id")
    expected_fk_item = ("item_id", "items", "id")
    assert expected_fk_user in fk_columns, (
        "Foreign key for orders.user_id referencing users(id) is missing"
    )
    assert expected_fk_item in fk_columns, (
        "Foreign key for orders.item_id referencing items(id) is missing"
    )
