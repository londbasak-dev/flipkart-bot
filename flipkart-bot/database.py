import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracker.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(admin_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tracked_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                last_price INTEGER,
                status TEXT,
                is_in_stock BOOLEAN DEFAULT 0,
                last_checked TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, url)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                check_interval_seconds INTEGER DEFAULT 300
            )
        ''')
        
        # Ensure admin is always approved
        if admin_id:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, status)
                VALUES (?, 'admin', 'Admin', 'approved')
                ON CONFLICT(user_id) DO UPDATE SET status = 'approved'
            ''', (admin_id,))
            
        conn.commit()

def get_user(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()

def add_user_request(user_id: int, username: str, first_name: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, status)
            VALUES (?, ?, ?, 'pending')
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        ''', (user_id, username or "", first_name or ""))
        conn.commit()

def approve_user(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = 'approved' WHERE user_id = ?", (user_id,))
        conn.commit()

def reject_user(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = 'rejected' WHERE user_id = ?", (user_id,))
        conn.commit()

def is_user_approved(user_id: int, admin_id: int) -> bool:
    if str(user_id) == str(admin_id):
        return True
    user = get_user(user_id)
    return user is not None and user["status"] == "approved"

def add_product(user_id: int, url: str, title: str, price: int, status: str, is_in_stock: bool):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tracked_products (user_id, url, title, last_price, status, is_in_stock, last_checked)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, url) DO UPDATE SET
                title = excluded.title,
                last_price = excluded.last_price,
                status = excluded.status,
                is_in_stock = excluded.is_in_stock,
                last_checked = excluded.last_checked
        ''', (user_id, url, title, price, status, 1 if is_in_stock else 0, now))
        conn.commit()
        return cursor.lastrowid

def get_user_products(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tracked_products WHERE user_id = ? ORDER BY id ASC", (user_id,))
        return cursor.fetchall()

def delete_product(product_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tracked_products WHERE id = ? AND user_id = ?", (product_id, user_id))
        conn.commit()
        return cursor.rowcount > 0

def clear_user_products(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tracked_products WHERE user_id = ?", (user_id,))
        conn.commit()

def get_all_products():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tracked_products")
        return cursor.fetchall()

def update_product_status(product_id: int, price: int, status: str, is_in_stock: bool):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE tracked_products 
            SET last_price = ?, status = ?, is_in_stock = ?, last_checked = ?
            WHERE id = ?
        ''', (price, status, 1 if is_in_stock else 0, now, product_id))
        conn.commit()

def set_user_interval(user_id: int, seconds: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_settings (user_id, check_interval_seconds)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET check_interval_seconds = excluded.check_interval_seconds
        ''', (user_id, seconds))
        conn.commit()

def get_user_interval(user_id: int, default_seconds: int = 300) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT check_interval_seconds FROM user_settings WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row['check_interval_seconds'] if row and row['check_interval_seconds'] else default_seconds

def set_user_pincode(user_id: int, pincode: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_settings (user_id, pincode)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET pincode = excluded.pincode
        ''', (user_id, str(pincode)))
        conn.commit()

def get_user_pincode(user_id: int, default_pincode: str = "110091") -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT pincode FROM user_settings WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return str(row['pincode']) if row and row['pincode'] else default_pincode
        except Exception:
            return default_pincode

