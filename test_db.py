# test_db.py
import os
import pytest
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Always use the local database for testing
LOCAL_DB_URL = os.getenv("LOCAL_DB_URL", "postgresql://postgres:postgres@localhost:5432/test_db")

@pytest.fixture
def db_connection():
    """Fixture that provides a database connection and handles cleanup"""
    # Set up connection
    conn = psycopg2.connect(LOCAL_DB_URL)
    cursor = conn.cursor()
    
    # Provide both connection and cursor to the test
    yield (conn, cursor)
    
    # Tear down/cleanup (runs after test completes)
    cursor.close()
    conn.close()

def test_database_connection(db_connection):
    """Test database connection to local database"""
    _, cursor = db_connection
    
    # Try executing a simple query
    cursor.execute("SELECT 1")
    result = cursor.fetchone()[0]
    
    assert result == 1

def test_tables_exist(db_connection):
    """Test that our tables exist in local database"""
    _, cursor = db_connection
    
    # Check all tables
    for table in ['users', 'items', 'orders']:
        cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = '{table}'
            );
        """)
        table_exists = cursor.fetchone()[0]
        assert table_exists == True, f"Table '{table}' does not exist"

def test_sample_data(db_connection):
    """Test that sample data exists in local database"""
    _, cursor = db_connection
    
    # Check data in each table
    for table in ['users', 'items', 'orders']:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        assert count > 0, f"No data found in table '{table}'"
