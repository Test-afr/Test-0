# init_db.py
import os
import psycopg2
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in .env file")

print(f"Connecting to database...")

# Connect to database
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cursor = conn.cursor()

# Create tables
print("Creating tables...")
cursor.execute("""
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS items CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    price NUMERIC(10, 2),
    category VARCHAR(50),
    in_stock BOOLEAN DEFAULT TRUE,
    owner_id INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    item_id INTEGER REFERENCES items(id),
    quantity INTEGER NOT NULL,
    total_price NUMERIC(10, 2),
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending'
);
""")

# Check if data already exists
cursor.execute("SELECT COUNT(*) FROM users")
user_count = cursor.fetchone()[0]

# Insert sample data if none exists
if user_count == 0:
    print("Adding sample data...")
    
    # Create 500 users
    print("Creating users...")
    for i in range(1, 501):
        username = f"user{i}"
        email = f"user{i}@example.com"
        cursor.execute(
            "INSERT INTO users (username, email) VALUES (%s, %s) RETURNING id",
            (username, email)
        )
    
    # Create 2000 items
    print("Creating items...")
    categories = ["Electronics", "Clothing", "Home", "Books", "Sports", "Food", "Tools", "Toys"]
    for i in range(1, 2001):
        name = f"Item {i}"
        description = f"Description for item {i}"
        price = round(random.uniform(5.99, 199.99), 2)
        category = random.choice(categories)
        in_stock = random.choice([True, True, True, False])  # 75% in stock
        owner_id = random.randint(1, 500)  # Random user
        
        cursor.execute(
            "INSERT INTO items (name, description, price, category, in_stock, owner_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (name, description, price, category, in_stock, owner_id)
        )
    
    # Create 2000 orders
    print("Creating orders...")
    statuses = ["pending", "processing", "shipped", "delivered", "cancelled"]
    start_date = datetime.now() - timedelta(days=365)  # Orders from last year
    
    for i in range(1, 2001):
        user_id = random.randint(1, 500)
        item_id = random.randint(1, 2000)
        quantity = random.randint(1, 5)
        
        # Get the price of the item
        cursor.execute("SELECT price FROM items WHERE id = %s", (item_id,))
        item_price = cursor.fetchone()[0]
        
        total_price = item_price * quantity
        
        # Random date within the last year
        days_ago = random.randint(0, 365)
        order_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
        
        # Older orders more likely to be delivered
        if days_ago > 30:
            status = random.choice(["delivered", "delivered", "delivered", "shipped", "cancelled"])
        else:
            status = random.choice(statuses)
            
        cursor.execute(
            "INSERT INTO orders (user_id, item_id, quantity, total_price, order_date, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, item_id, quantity, total_price, order_date, status)
        )
        
        if i % 200 == 0:
            print(f"Created {i} orders...")
    
    print("Sample data added!")
else:
    print("Data already exists. Skipping initialization.")

# Add indexes for performance
print("Creating indexes...")
cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_items_owner_id ON items (owner_id);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders (user_id);
CREATE INDEX IF NOT EXISTS idx_orders_item_id ON orders (item_id);
CREATE INDEX IF NOT EXISTS idx_orders_date ON orders (order_date);
""")

# Print table counts
cursor.execute("SELECT COUNT(*) FROM users")
user_count = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM items")
item_count = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM orders")
order_count = cursor.fetchone()[0]

print(f"Database now has {user_count} users, {item_count} items, and {order_count} orders")

# Close connection
cursor.close()
conn.close()

print("Database setup complete!")
