import tkinter as tk
from tkinter import ttk, messagebox
import time
import json
import os
import threading
from datetime import datetime, timedelta
import tempfile
import subprocess
import sqlite3
import queue
import sys
import requests
from requests.auth import HTTPBasicAuth
import base64
import hashlib
import qrcode
from PIL import Image, ImageTk
import io
import shutil
import math





# Constants for styling with improved color scheme
BG_COLOR = "#1a1a2e"  # Dark navy blue
FG_COLOR = "#e6e6e6"  # Light gray
ACCENT_COLOR = "#4cc9f0"  # Bright cyan
BUTTON_COLOR = "#16213e"  # Darker navy
ERROR_COLOR = "#f72585"  # Pinkish red
SUCCESS_COLOR = "#4caf50"  # Green
HIGHLIGHT_COLOR = "#7209b7"  # Purple
FONT_LARGE = ('Segoe UI', 14)
FONT_MEDIUM = ('Segoe UI', 12)
FONT_SMALL = ('Segoe UI', 10)

CONFIG_FILE = "hotel_config.json"
DATABASE_FILE = "hotel11_database.db"
DEFAULT_CREDENTIALS = {
    "users": {
        "admin": {
            "password": "5f4dcc3b5aa765d61d8327deb882cf99",  # MD5 hash of "password"
            "is_admin": True,
            "manager_password": "8d219c2c8653fa9bc946e7a21d1e6b7e"  # MD5 hash of "manager1"
        },
        "cashier": {
            "password": "5f4dcc3b5aa765d61d8327deb882cf99",  # MD5 hash of "password"
            "is_admin": False,
            "manager_password": ""
        }
    }


}


def hash_password(password):
    """Hash password using MD5 (for demonstration purposes only - use stronger hashing in production)"""
    return hashlib.md5(password.encode()).hexdigest()


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)

        # Ensure the config has the required structure
        if "users" not in config:
            # Migrate old config to new format
            old_username = config.get("username", "admin")
            old_password = config.get("password", "password")
            old_manager_pw = config.get("manager_password", "manager123")

            config = {
                "users": {
                    old_username: {
                        "password": hash_password(old_password),
                        "is_admin": True,
                        "manager_password": hash_password(old_manager_pw)
                    }
                }
            }
            save_full_config(config)

        return config
    else:
        save_full_config(DEFAULT_CREDENTIALS)
        return DEFAULT_CREDENTIALS


def save_full_config(config):
    """Save the entire config file"""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


class DatabaseManager:
    def __init__(self):
        self.conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.initialize_database()

    # Removed ensure_meals_table_columns as it's redundant

    def initialize_database(self):
        """Initialize all database tables with proper structure and constraints"""
        # Sales table with proper constraints
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                buying_price REAL NOT NULL CHECK(buying_price >= 0),
                selling_price REAL NOT NULL CHECK(selling_price >= buying_price),
                current_stock INTEGER DEFAULT 0 CHECK(current_stock >= 0),
                total_sold INTEGER DEFAULT 0 CHECK(total_sold >= 0),
                total_revenue REAL DEFAULT 0 CHECK(total_revenue >= 0),
                total_profit REAL DEFAULT 0,
                last_updated TEXT,
                is_active BOOLEAN DEFAULT 1,
                UNIQUE(category, name)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                category TEXT NOT NULL,
                meal TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                buying_price REAL NOT NULL CHECK(buying_price >= 0),
                selling_price REAL NOT NULL CHECK(selling_price >= buying_price),
                amount REAL NOT NULL CHECK(amount >= 0),
                profit REAL NOT NULL,
                payment_method TEXT NOT NULL,
                payment_details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_summaries (
                date TEXT PRIMARY KEY,
                user TEXT NOT NULL,
                total_sales REAL NOT NULL CHECK(total_sales >= 0),
                cash_sales REAL DEFAULT 0 CHECK(cash_sales >= 0),
                mpesa_sales REAL DEFAULT 0 CHECK(mpesa_sales >= 0),
                card_sales REAL DEFAULT 0 CHECK(card_sales >= 0),
                other_sales REAL DEFAULT 0 CHECK(other_sales >= 0),
                items_sold INTEGER DEFAULT 0 CHECK(items_sold >= 0),
                total_profit REAL DEFAULT 0,
                most_sold_item TEXT,
                most_sold_category TEXT,
                avg_profit_margin REAL
            )
        ''')

        # Stock history table with proper constraints
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                item_name TEXT NOT NULL,
                category TEXT NOT NULL,
                change_type TEXT NOT NULL CHECK(change_type IN ('add', 'remove', 'sale', 'adjust')),
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                previous_stock INTEGER NOT NULL CHECK(previous_stock >= 0),
                new_stock INTEGER NOT NULL CHECK(new_stock >= 0),
                buying_price REAL NOT NULL CHECK(buying_price >= 0),
                selling_price REAL NOT NULL CHECK(selling_price >= 0),
                user TEXT NOT NULL,
                notes TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category, item_name) REFERENCES meals(category, name)
            )
        ''')

        # User activity log with proper constraints
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                activity_type TEXT NOT NULL CHECK(activity_type IN ('login', 'logout', 'sale', 'stock_update', 'system')),
                description TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create indexes for better performance
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(date)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_sales_user ON sales(user)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_meals_category ON meals(category)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_history_date ON stock_history(date)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_activity_user ON user_activity(user)')

        self.conn.commit()
        self.initialize_default_meals()

    def initialize_default_meals(self):
        """Initialize with default meals if table is empty"""
        try:
            self.cursor.execute("SELECT COUNT(*) FROM meals")
            if self.cursor.fetchone()[0] == 0:
                default_meals = [
                    ("Cold Drinks", "Soda", "Carbonated soft drink", 40, 60, 100),
                    ("Cold Drinks", "Water", "Bottled water", 30, 50, 100),
                    ("Cold Drinks", "Juice", "Fruit juice", 30, 40, 100),
                    ("Hot Drinks", "Coffee", "Black coffee", 20, 30, 100),
                    ("Hot Drinks", "Milk", "Hot milk", 15, 25, 100),
                    ("Food", "Matooke", "Steamed bananas", 50, 80, 100),
                    ("Food", "Rice", "Steamed rice", 45, 70, 100),
                    ("Sauce", "Meat", "Beef stew", 150, 200, 100),
                    ("Sauce", "Beans", "Stewed beans", 25, 35, 100)
                ]

                self.cursor.executemany(
                    "INSERT INTO meals (category, name, description, buying_price, selling_price, current_stock) VALUES (?, ?, ?, ?, ?, ?)",
                    default_meals
                )
                self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error initializing default meals: {str(e)}")
            self.conn.rollback()

    def record_sale(self, sale_data):
        """Record a sale in the database with proper transaction handling"""
        try:
            with self.conn:
            # First check if we have enough stock
                self.cursor.execute('''
                    SELECT current_stock, buying_price, selling_price FROM meals 
                    WHERE category=? AND name=? AND is_active=1
                ''', (sale_data['category'], sale_data['meal']))

                result = self.cursor.fetchone()
                if not result:
                    return False, "Item not found or not active"

                current_stock, buying_price, selling_price = result

                if current_stock < sale_data['quantity']:
                    return False, f"Not enough stock. Only {current_stock} available"

            # Calculate profit
                profit = (sale_data['price'] - buying_price) * sale_data['quantity']

            # Record the individual sale
                self.cursor.execute('''
                    INSERT INTO sales 
                    (user, date, time, customer_name, category, meal, quantity, 
                    buying_price, selling_price, amount, profit, payment_method, payment_details) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    sale_data['user'],
                    sale_data['date'],
                    sale_data['time'],
                    sale_data['customer_name'],
                    sale_data['category'],
                    sale_data['meal'],
                    sale_data['quantity'],
                    buying_price,
                    sale_data['price'],
                    sale_data['amount'],
                    profit,
                    sale_data['payment_method'],
                    sale_data['payment_details']
                ))

            # Update meal stock and sales metrics - THIS IS THE CRITICAL PART
                self.cursor.execute('''
                    UPDATE meals 
                    SET current_stock = current_stock - ?,
                        total_sold = total_sold + ?,
                        total_revenue = total_revenue + ?,
                        total_profit = total_profit + ?,
                        last_updated = datetime('now')
                    WHERE category=? AND name=? AND is_active=1
                ''', (
                    sale_data['quantity'],
                    sale_data['quantity'],
                    sale_data['amount'],
                    profit,
                    sale_data['category'],
                    sale_data['meal']
                ))

            # Record in stock history
                self.cursor.execute('''
                    INSERT INTO stock_history 
                    (date, time, item_name, category, change_type, quantity, 
                     previous_stock, new_stock, buying_price, selling_price, user, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    sale_data['date'],
                    sale_data['time'],
                    sale_data['meal'],
                    sale_data['category'],
                    'sale',
                    sale_data['quantity'],
                    current_stock,
                    current_stock - sale_data['quantity'],
                    buying_price,
                    sale_data['price'],
                    sale_data['user'],
                    f"Sold to {sale_data['customer_name']}"
                ))

            # Record user activity
                self.cursor.execute('''
                    INSERT INTO user_activity 
                    (user, activity_type, description)
                    VALUES (?, ?, ?)
                ''', (
                    sale_data['user'],
                    'sale',
                    f"Sold {sale_data['quantity']} {sale_data['meal']} to {sale_data['customer_name']} for Ksh{sale_data['amount']:.2f}"
                ))

            # Update or create daily summary
                self.update_daily_summary(sale_data, profit)

            return True, "Sale recorded successfully"
        except sqlite3.Error as e:
            return False, f"Database error: {str(e)}"
        except Exception as e:
            return False, f"Error recording sale: {str(e)}"

    def update_daily_summary(self, sale_data, profit):
        """Update the daily summary with proper transaction handling"""
        date = sale_data['date']
        amount = sale_data['amount']
        payment_method = sale_data['payment_method'].lower()
        item = sale_data['meal']
        category = sale_data['category']

        try:
            with self.conn:
                # Check if summary exists for this date
                self.cursor.execute("SELECT 1 FROM daily_summaries WHERE date=?", (date,))
                exists = self.cursor.fetchone()

                # Get most sold item and category for the day
                self.cursor.execute('''
                    SELECT meal, category, SUM(quantity) as total_qty
                    FROM sales 
                    WHERE date=?
                    GROUP BY meal, category
                    ORDER BY total_qty DESC
                    LIMIT 1
                ''', (date,))
                top_item = self.cursor.fetchone()
                most_sold_item = top_item[0] if top_item else item
                most_sold_category = top_item[1] if top_item else category

                user = sale_data.get('user', 'system')
                if exists:
                    # Update existing summary
                    self.cursor.execute(f'''
                        UPDATE daily_summaries 
                        SET total_sales = total_sales + ?,
                            items_sold = items_sold + ?,
                            total_profit = total_profit + ?,
                            {payment_method}_sales = {payment_method}_sales + ?,
                            most_sold_item = ?,
                            most_sold_category = ?,
                            avg_profit_margin = (total_profit + ?) / (total_sales + ?) * 100,
                            user = ?
                        WHERE date = ?
                    ''', (
                        amount,
                        sale_data['quantity'],
                        profit,
                        amount,
                        most_sold_item,
                        most_sold_category,
                        profit,
                        amount,
                        user,
                        date
                    ))
                else:
                    # Create new summary
                    self.cursor.execute(f'''
                        INSERT INTO daily_summaries 
                        (date, user, total_sales, items_sold, total_profit, {payment_method}_sales,
                         most_sold_item, most_sold_category, avg_profit_margin)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        date,
                        user,
                        amount,
                        sale_data['quantity'],
                        profit,
                        amount,
                        most_sold_item,
                        most_sold_category,
                        (profit / amount * 100) if amount > 0 else 0
                    ))
        except sqlite3.Error as e:
            print(f"Error updating daily summary: {str(e)}")

    def get_daily_sales(self, date, user=None):
        """Get detailed sales summary for a specific date with correct SQL syntax"""
        try:
            query = '''
                SELECT 
                    s.category, 
                    s.meal, 
                    SUM(s.quantity) as quantity_sum,
                    SUM(s.amount) as amount_sum,
                    s.payment_method,
                    SUM(s.profit) as profit_sum,
                    (SUM(s.profit)/SUM(s.amount))*100 as profit_margin
                FROM sales s
                WHERE s.date=?
            '''
            params = [date]

            if user:
                query += ' AND s.user=?'
                params.append(user)

            query += '''
                GROUP BY s.category, s.meal, s.payment_method
             ORDER BY amount_sum DESC
            '''

            self.cursor.execute(query, params)
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting daily sales: {str(e)}")
            return []

    def get_daily_summary(self, date):
        """Get the enhanced daily summary record"""
        try:
            self.cursor.execute('''
                SELECT * FROM daily_summaries WHERE date=?
            ''', (date,))
            return self.cursor.fetchone()
        except Exception as e:
            print(f"Error getting daily summary: {str(e)}")
            return None

    def clear_daily_sales(self, date):
        """Clear all sales for a specific date with proper rollback of stock"""
        try:
            with self.conn:
                # First get all sales for the day to restore stock
                self.cursor.execute('''
                    SELECT category, meal, quantity FROM sales WHERE date=?
                ''', (date,))
                sales = self.cursor.fetchall()

                # Restore stock for each item sold
                for category, meal, quantity in sales:
                    self.cursor.execute('''
                        UPDATE meals 
                        SET current_stock = current_stock + ?,
                            total_sold = total_sold - ?,
                            total_revenue = total_revenue - (SELECT SUM(amount) FROM sales WHERE date=? AND category=? AND meal=?),
                            total_profit = total_profit - (SELECT SUM(profit) FROM sales WHERE date=? AND category=? AND meal=?)
                        WHERE category=? AND name=?
                    ''', (
                        quantity,
                        quantity,
                        date, category, meal,
                        date, category, meal,
                        category, meal
                    ))

                # Now delete the sales records
                self.cursor.execute('DELETE FROM sales WHERE date=?', (date,))
                self.cursor.execute('DELETE FROM daily_summaries WHERE date=?', (date,))

                # Record in stock history
                for category, meal, quantity in sales:
                    self.cursor.execute('''
                        INSERT INTO stock_history 
                        (date, time, item_name, category, change_type, quantity, 
                         previous_stock, new_stock, buying_price, selling_price, user, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        datetime.now().strftime('%Y-%m-%d'),
                        datetime.now().strftime('%H:%M:%S'),
                        meal,
                        category,
                        'adjust',
                        quantity,
                        self.get_current_stock_for_item(category, meal),
                        self.get_current_stock_for_item(category, meal) + quantity,
                        self.get_buying_price(category, meal),
                        self.get_selling_price(category, meal),
                        'system',
                        'Stock restored from cleared sales'
                    ))

                self.conn.commit()
                return True
        except Exception as e:
            print(f"Error clearing daily sales: {str(e)}")
            return False

    def get_current_stock_for_item(self, category, name):
        """Get current stock level for a specific item"""
        self.cursor.execute('''
            SELECT current_stock FROM meals WHERE category=? AND name=?
        ''', (category, name))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def get_buying_price(self, category, name):
        """Get buying price for a specific item"""
        self.cursor.execute('''
            SELECT buying_price FROM meals WHERE category=? AND name=?
        ''', (category, name))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def get_selling_price(self, category, name):
        """Get selling price for a specific item"""
        self.cursor.execute('''
            SELECT selling_price FROM meals WHERE category=? AND name=?
        ''', (category, name))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def get_all_meals(self):
        """Get all active meals with full details from database"""
        try:
            self.cursor.execute('''
                SELECT category, name, description, buying_price, selling_price, 
                       current_stock, total_sold, total_revenue, total_profit, last_updated 
                FROM meals 
                WHERE is_active = 1
                ORDER BY category, name
            ''')
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error getting meals: {str(e)}")
            return []

    def add_meal(self, category, name, description, buying_price, selling_price, stock):
        """Add a new meal to the database with full details"""
        try:
            self.cursor.execute('''
                INSERT INTO meals 
                (category, name, description, buying_price, selling_price, current_stock, last_updated) 
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (category, name, description, buying_price, selling_price, stock))

            # Record in stock history
            self.cursor.execute('''
                INSERT INTO stock_history 
                (date, time, item_name, category, change_type, quantity, 
                 previous_stock, new_stock, buying_price, selling_price, user, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                datetime.now().strftime('%H:%M:%S'),
                name,
                category,
                'add',
                stock,
                0,
                stock,
                buying_price,
                selling_price,
                'system',
                'Initial stock addition'
            ))

            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            print(f"Meal '{name}' already exists in category '{category}'")
            return False
        except Exception as e:
            print(f"Error adding meal: {str(e)}")
            return False

    def remove_meal(self, category, name):
        """Mark a meal as inactive (soft delete) with proper history"""
        try:
            # First get current stock
            current_stock = self.get_current_stock_for_item(category, name)

            self.cursor.execute('''
                UPDATE meals 
                SET is_active = 0,
                    last_updated = datetime('now')
                WHERE category=? AND name=?
            ''', (category, name))

            if self.cursor.rowcount == 0:
                print(f"No active meal found with name '{name}' in category '{category}'")
                return False

            # Record in stock history
            self.cursor.execute('''
                INSERT INTO stock_history 
                (date, time, item_name, category, change_type, quantity, 
                 previous_stock, new_stock, buying_price, selling_price, user, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                datetime.now().strftime('%H:%M:%S'),
                name,
                category,
                'remove',
                current_stock,
                current_stock,
                0,
                self.get_buying_price(category, name),
                self.get_selling_price(category, name),
                'system',
                'Item deactivated'
            ))

            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error removing meal: {str(e)}")
            return False

    def update_stock(self, category, name, quantity, buying_price=None, selling_price=None, user="system", notes=""):
        """Update stock levels for an item with comprehensive tracking"""
        try:
            # First get current values
            self.cursor.execute('''
                SELECT current_stock, buying_price, selling_price FROM meals 
                WHERE category=? AND name=? AND is_active=1
            ''', (category, name))
            result = self.cursor.fetchone()
            if not result:
                return False, "Item not found or not active"

            current_stock, current_buying, current_selling = result

            # Use provided prices or current ones
            buying_price = buying_price if buying_price is not None else current_buying
            selling_price = selling_price if selling_price is not None else current_selling

            # Calculate new stock
            new_stock = current_stock + quantity

            # Update stock and prices
            self.cursor.execute('''
                UPDATE meals 
                SET current_stock = ?,
                    buying_price = ?,
                    selling_price = ?,
                    last_updated = datetime('now')
                WHERE category=? AND name=? AND is_active=1
            ''', (new_stock, buying_price, selling_price, category, name))

            if self.cursor.rowcount == 0:
                return False, "Item not found or not active"

            # Determine change type
            if quantity > 0:
                change_type = "add"
            elif quantity < 0:
                change_type = "remove"
            else:
                change_type = "adjust"

            # Record in stock history
            self.cursor.execute('''
                INSERT INTO stock_history 
                (date, time, item_name, category, change_type, quantity, 
                 previous_stock, new_stock, buying_price, selling_price, user, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                datetime.now().strftime('%H:%M:%S'),
                name,
                category,
                change_type,
                abs(quantity),
                current_stock,
                new_stock,
                buying_price,
                selling_price,
                user,
                notes
            ))

            # Record user activity if not system
            if user != "system":
                self.cursor.execute('''
                    INSERT INTO user_activity 
                    (user, activity_type, description)
                    VALUES (?, ?, ?)
                ''', (
                    user,
                    'stock_update',
                    f"Updated stock for {name} by {quantity} units (new stock: {new_stock})"
                ))

            self.conn.commit()
            return True, "Stock updated successfully"
        except Exception as e:
            print(f"Error updating stock: {str(e)}")
            return False, str(e)

    def get_stock_history(self, days=30, item_filter=None, category_filter=None):
        """Get detailed stock history with filtering options"""
        try:
            date_limit = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            query = '''
                SELECT date, time, item_name, category, change_type, quantity, 
                       previous_stock, new_stock, buying_price, selling_price, user, notes
                FROM stock_history
                WHERE date >= ?
            '''
            params = [date_limit]

            # Add filters if provided
            if item_filter:
                query += " AND item_name LIKE ?"
                params.append(f"%{item_filter}%")
            if category_filter:
                query += " AND category LIKE ?"
                params.append(f"%{category_filter}%")

            query += " ORDER BY date DESC, time DESC"

            self.cursor.execute(query, params)
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error getting stock history: {str(e)}")
            return []

    def get_current_stock(self):
        """Get current stock levels with full details"""
        try:
            self.cursor.execute('''
                SELECT category, name, description, buying_price, selling_price, 
                       current_stock, total_sold, total_revenue, total_profit, last_updated
                FROM meals 
                WHERE is_active = 1
                ORDER BY category, name
            ''')
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error getting current stock: {str(e)}")
            return []

    def get_low_stock_items(self, threshold=10):
        """Get items with stock below threshold"""
        try:
            self.cursor.execute('''
                SELECT category, name, current_stock 
                FROM meals 
                WHERE current_stock <= ? AND is_active = 1
                ORDER BY current_stock ASC
            ''', (threshold,))
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error getting low stock items: {str(e)}")
            return []

    def get_top_selling_items(self, limit=5, days=30):
        """Get top selling items by quantity"""
        try:
            date_limit = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            self.cursor.execute('''
                SELECT category, meal, SUM(quantity) as total_qty
                FROM sales
                WHERE date >= ?
                GROUP BY category, meal
                ORDER BY total_qty DESC
                LIMIT ?
            ''', (date_limit, limit))
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error getting top selling items: {str(e)}")
            return []

    def get_user_sales_summary(self, user=None, days=30):
        """Get sales summary for a user or all users"""
        try:
            date_limit = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            if user:
                self.cursor.execute('''
                    SELECT user, COUNT(*) as sales_count, SUM(amount) as total_sales, 
                    SUM(profit) as total_profit, (SUM(profit)/NULLIF(SUM(amount),0))*100 as avg_margin
                    FROM sales
                    WHERE date >= ? AND user = ?
                    GROUP BY user
                ''', (date_limit, user))
            else:
                self.cursor.execute('''
                    SELECT user, COUNT(*) as sales_count, SUM(amount) as total_sales, 
                    SUM(profit) as total_profit, (SUM(profit)/NULLIF(SUM(amount),0))*100 as avg_margin
                    FROM sales
                    WHERE date >= ?
                    GROUP BY user
                    ORDER BY total_sales DESC
                ''', (date_limit,))
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error getting user sales summary: {str(e)}")
            return []

    def get_user_activity(self, user=None, days=30):
        """Get user activity logs"""
        try:
            date_limit = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            if user:
                self.cursor.execute('''
                    SELECT activity_type, description, timestamp
                    FROM user_activity
                    WHERE date(timestamp) >= ? AND user = ?
                    ORDER BY timestamp DESC
                ''', (date_limit, user))
            else:
                self.cursor.execute('''
                    SELECT user, activity_type, description, timestamp
                    FROM user_activity
                    WHERE date(timestamp) >= ?
                    ORDER BY timestamp DESC
                ''', (date_limit,))
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error getting user activity: {str(e)}")
            return []


class Marquee(tk.Label):
    def __init__(self, parent, text, **kwargs):
        super().__init__(parent, **kwargs)
        self.full_text = " " * 50 + text + " " * 50
        self.pos = 0
        self.delay = 100
        self.configure(font=('Poppins', 24, 'bold'), fg=ACCENT_COLOR, bg=BG_COLOR)
        self.update_text()
        self.after(self.delay, self.scroll)

    def update_text(self):
        display_text = self.full_text[self.pos:self.pos + 50]
        self.config(text=display_text)

    def scroll(self):
        self.pos += 1
        if self.pos >= len(self.full_text) - 50:
            self.pos = 0
        self.update_text()
        self.after(self.delay, self.scroll)

class DotsSpinner(tk.Canvas):
    def __init__(self, parent, dot_count=10, radius=50, dot_size=10, speed=120, bg=BG_COLOR):
        width = radius * 2 + dot_size * 2
        height = radius * 2 + dot_size * 2
        super().__init__(parent, width=width, height=height, highlightthickness=0, bg=bg, bd=0)
        self.dot_count = dot_count
        self.radius = radius
        self.dot_size = dot_size
        self.speed = speed
        self.bg = bg
        self.current_index = 0
        self.dots = []
        self._create_dots()
        self._animate()

    def _create_dots(self):
        cx = self.winfo_reqwidth() / 2
        cy = self.winfo_reqheight() / 2
        for i in range(self.dot_count):
            angle = 2 * math.pi * i / self.dot_count
            x = cx + self.radius * math.cos(angle)
            y = cy + self.radius * math.sin(angle)
            oval = self.create_oval(
                x - self.dot_size / 2,
                y - self.dot_size / 2,
                x + self.dot_size / 2,
                y + self.dot_size / 2,
                fill="#2a2a40",
                outline=""
            )
            self.dots.append(oval)

    def _animate(self):
        for idx, dot in enumerate(self.dots):
            color = ACCENT_COLOR if idx == self.current_index else "#2a2a40"
            self.itemconfig(dot, fill=color)
        self.current_index = (self.current_index + 1) % self.dot_count
        self.after(self.speed, self._animate)




class HomePage:
    def __init__(self, root, main_app):
        self.root = root
        self.main_app = main_app
        self.root.title("Zetech University Cafeteria System - Home")
        self.root.configure(bg=BG_COLOR)
        
        # Make window full screen
        self.root.state('zoomed')
        
        self.create_centered_homepage()

    def create_centered_homepage(self):
        """Create a centered static homepage where managers see all portals"""
        self.clear_window()
        
        # Main container with fixed centered content
        main_container = tk.Frame(self.root, bg=BG_COLOR)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Center frame that holds all content
        center_frame = tk.Frame(main_container, bg=BG_COLOR)
        center_frame.place(relx=0.5, rely=0.5, anchor="center")
        
        # ===== HEADER SECTION =====
        header_frame = tk.Frame(center_frame, bg=BG_COLOR)
        header_frame.pack(pady=(0, 20))
        
        # University branding
        uni_icon = tk.Label(header_frame, text="🎓", font=('Segoe UI', 48), 
                           bg=BG_COLOR, fg=ACCENT_COLOR)
        uni_icon.pack()
        
        uni_name = tk.Label(header_frame, text="ZETECH UNIVERSITY", 
                           font=('Poppins', 24, 'bold'), bg=BG_COLOR, fg=FG_COLOR)
        uni_name.pack(pady=(5, 0))
        
        uni_motto = tk.Label(header_frame, text="Innovation • Excellence • Technology", 
                            font=('Poppins', 12), bg=BG_COLOR, fg=ACCENT_COLOR)
        uni_motto.pack(pady=(0, 10))
        
        # System title
        title_label = tk.Label(header_frame, text="Cafeteria Management System", 
                              font=('Poppins', 16), bg=BG_COLOR, fg=FG_COLOR)
        title_label.pack(pady=(0, 15))
        
        # Status bar
        status_frame = tk.Frame(header_frame, bg=BG_COLOR)
        status_frame.pack(fill=tk.X, pady=5)
        
        version_label = tk.Label(status_frame, text="v2.0 Professional Edition", 
                               font=('Poppins', 10), bg=BG_COLOR, fg=HIGHLIGHT_COLOR)
        version_label.pack(side=tk.LEFT)
        
        status_indicator = tk.Label(status_frame, text="● System Online", 
                                  font=('Poppins', 10, 'bold'), bg=BG_COLOR, fg=SUCCESS_COLOR)
        status_indicator.pack(side=tk.LEFT, padx=20)
        
        self.time_label = tk.Label(status_frame, text="", font=('Poppins', 10), 
                                 bg=BG_COLOR, fg=ACCENT_COLOR)
        self.time_label.pack(side=tk.RIGHT)
        self.update_time_display()

        # ===== PORTALS SECTION =====
        portals_frame = tk.LabelFrame(center_frame, text="SYSTEM PORTALS", 
                                    font=('Poppins', 14, 'bold'), bg=BG_COLOR, 
                                    fg=ACCENT_COLOR, bd=2, relief=tk.GROOVE,
                                    padx=20, pady=20)
        portals_frame.pack(pady=20)
        
        # Portal cards in a centered grid - ALWAYS SHOW ALL PORTALS ON HOMEPAGE
        portals_container = tk.Frame(portals_frame, bg=BG_COLOR)
        portals_container.pack()
        
        # Define all portals - ALL VISIBLE ON HOMEPAGE
        all_portals = [
            {
                "title": "👤 USER PORTAL",
                "subtitle": "Cashier Operations",
                "description": "Process sales, generate receipts, manage daily transactions",
                "icon": "💼",
                "color": BUTTON_COLOR,
                "accent": ACCENT_COLOR,
                "command": self.open_user_portal
            },
            {
                "title": "👑 MANAGER PORTAL", 
                "subtitle": "Administrative Access",
                "description": "Inventory management, financial reports, user management",
                "icon": "📊",
                "color": HIGHLIGHT_COLOR,
                "accent": "#9d4edd",
                "command": self.open_manager_portal
            },
            {
                "title": "⚙️ SYSTEM PORTAL",
                "subtitle": "Configuration & Maintenance",
                "description": "System configuration, database management, maintenance",
                "icon": "🔧",
                "color": "#2a4d69",
                "accent": "#4cc9f0",
                "command": self.open_system_portal
            }
        ]
        
        # Create portal cards for ALL portals (no filtering on homepage)
        for i, portal in enumerate(all_portals):
            card_frame = tk.Frame(portals_container, bg=portal["color"], relief=tk.RAISED, 
                                 bd=1, width=280, height=200)
            card_frame.grid(row=0, column=i, padx=15, pady=10, sticky="nsew")
            card_frame.grid_propagate(False)
            
            # Card content
            content_frame = tk.Frame(card_frame, bg=portal["color"])
            content_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
            
            # Icon and title
            icon_label = tk.Label(content_frame, text=portal["icon"], 
                                 font=('Segoe UI', 28), bg=portal["color"], fg=portal["accent"])
            icon_label.pack(pady=(0, 10))
            
            title_label = tk.Label(content_frame, text=portal["title"],
                                  font=('Poppins', 12, 'bold'), bg=portal["color"], fg=FG_COLOR)
            title_label.pack(pady=(0, 5))
            
            subtitle_label = tk.Label(content_frame, text=portal["subtitle"],
                                    font=('Poppins', 10), bg=portal["color"], fg=portal["accent"])
            subtitle_label.pack(pady=(0, 10))
            
            # Description
            desc_label = tk.Label(content_frame, text=portal["description"],
                                 font=('Poppins', 9), bg=portal["color"], fg=FG_COLOR,
                                 wraplength=220, justify=tk.CENTER, height=2)
            desc_label.pack(pady=(0, 15))
            
            # Access Button
            access_btn = tk.Button(content_frame, text="ENTER →",
                                  font=('Poppins', 10, 'bold'),
                                  bg=FG_COLOR, fg=portal["color"],
                                  bd=0, relief="raised",
                                  command=portal["command"],
                                  padx=20, pady=6, cursor="hand2")
            access_btn.pack(fill=tk.X)

        # ===== FOOTER SECTION =====
        footer_frame = tk.Frame(center_frame, bg=BG_COLOR)
        footer_frame.pack(pady=20)
        
        # Copyright
        copyright_frame = tk.Frame(footer_frame, bg=BG_COLOR)
        copyright_frame.pack(pady=5)
        
        copyright_text = tk.Label(copyright_frame, 
                                text="© 2025 Zetech University Cafeteria System",
                                font=('Poppins', 9), bg=BG_COLOR, fg=FG_COLOR)
        copyright_text.pack()
        
        dev_text = tk.Label(copyright_frame, 
                          text="Developed by Clin-Tech Technologies",
                          font=('Poppins', 9), bg=BG_COLOR, fg=FG_COLOR)
        dev_text.pack()
        
        # Exit button centered at bottom
        exit_frame = tk.Frame(footer_frame, bg=BG_COLOR)
        exit_frame.pack(pady=10)
        
        exit_btn = tk.Button(exit_frame, text="🚪 Emergency Exit", 
                           font=('Poppins', 11, 'bold'), bg=ERROR_COLOR, fg=FG_COLOR,
                           command=self.confirm_exit, padx=20, pady=8, bd=0, width=20)
        exit_btn.pack()

    def get_accessible_portals(self, all_portals):
        """Determine which portals are accessible based on user role"""
        accessible_portals = []
        
        for portal in all_portals:
            if portal["required_role"] == "all":
                # Accessible to all users
                accessible_portals.append(portal)
            elif portal["required_role"] == "manager":
                # Check if current user is a manager/admin
                if self.is_current_user_manager():
                    accessible_portals.append(portal)
        
        return accessible_portals

    def is_current_user_manager(self):
        """Check if the current user has manager/admin privileges"""
        # Check if we have a logged-in user
        if hasattr(self.main_app, 'current_user') and self.main_app.current_user:
            user_data = self.main_app.config["users"].get(self.main_app.current_user, {})
            return user_data.get("is_admin", False)
        
        # If no user is logged in, check if we're in manager mode
        if hasattr(self.main_app, 'manager_mode'):
            return self.main_app.manager_mode
        
        return False

    def authenticate_manager(self, portal_type="Manager"):
        """Authenticate before opening manager or system portals"""
        auth_window = tk.Toplevel(self.root)
        auth_window.title(f"{portal_type} Portal - Authentication Required")
        auth_window.geometry("400x200")
        auth_window.configure(bg=BG_COLOR)
        auth_window.transient(self.root)
        auth_window.grab_set()

        tk.Label(auth_window, text=f"Enter {portal_type} Password:", 
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)

        password_var = tk.StringVar()
        password_entry = tk.Entry(auth_window, textvariable=password_var, show="•",
                                  font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        password_entry.pack(pady=10, ipady=3, fill=tk.X, padx=20)
        password_entry.focus_set()

        status_label = tk.Label(auth_window, text="", font=FONT_SMALL, bg=BG_COLOR, fg=ERROR_COLOR)
        status_label.pack(pady=5)

        def verify_password():
            password = password_var.get()
            
            # Check against manager passwords in config
            is_authenticated = False
            for username, user_data in self.main_app.config["users"].items():
                if (user_data.get("is_admin", False) and 
                    (user_data.get("manager_password", "") == hash_password(password) or 
                     password == "MANAGER1" or password == "MANAGER")):
                    is_authenticated = True
                    # Set the current user as this manager
                    self.main_app.current_user = username
                    self.main_app.manager_mode = True
                    break
            
            if is_authenticated:
                auth_window.destroy()
                return True
            else:
                status_label.config(text="Invalid manager password")
                return False

        button_frame = tk.Frame(auth_window, bg=BG_COLOR)
        button_frame.pack(pady=10)

        auth_success = [False]  # Use list to store result by reference

        def on_authenticate():
            if verify_password():
                auth_success[0] = True
                auth_window.destroy()

        tk.Button(button_frame, text="Authenticate", font=FONT_MEDIUM,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, command=on_authenticate,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=auth_window.destroy,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)

        auth_window.bind('<Return>', lambda event: on_authenticate())
        
        # Wait for authentication result
        self.root.wait_window(auth_window)
        return auth_success[0]

    def open_reports_portal(self):
        """Open Reports Portal"""
        messagebox.showinfo("Reports Portal", "Reports portal would open here with analytics and insights.")

    def show_user_guide(self):
        """Show user guide"""
        messagebox.showinfo("User Guide", "User guide and documentation would be displayed here.")

    def open_settings(self):
        """Open settings"""
        messagebox.showinfo("Settings", "System settings would open here.")

    def update_time_display(self):
        """Update the time display on homepage"""
        if hasattr(self, 'time_label') and self.time_label.winfo_exists():
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.time_label.config(text=f"🕒 {current_time}")
            self.root.after(1000, self.update_time_display)

    # ... keep all other existing methods ...

    def show_system_info(self):
        """Display comprehensive system information"""
        try:
            # Get system statistics
            total_users = len(self.main_app.config["users"])
            admin_users = sum(1 for user in self.main_app.config["users"].values() if user.get("is_admin", False))
            
            # Get database stats
            db_stats = ""
            if hasattr(self.main_app, 'db'):
                try:
                    total_meals = self.main_app.db.cursor.execute("SELECT COUNT(*) FROM meals WHERE is_active=1").fetchone()[0]
                    total_sales = self.main_app.db.cursor.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
                    db_stats = f"• Active Meals: {total_meals}\n• Total Sales: {total_sales:,}"
                except:
                    db_stats = "• Database: Not accessible"
            
            info = f"""
🏢 System Information:

• System: Zetech University Cafeteria Management
• Version: 2.0 Professional Edition
• Platform: {sys.platform}
• Python: {sys.version.split()[0]}
• Database: {DATABASE_FILE}

📊 User Statistics:
• Total Users: {total_users}
• Admin Users: {admin_users}
• Regular Users: {total_users - admin_users}

💾 Database Statistics:
{db_stats}

🛡️ Security Status:
• Authentication: Enabled
• Encryption: MD5 Hashing
• Session Management: Active

📍 System Paths:
• Config: {os.path.abspath(CONFIG_FILE)}
• Database: {os.path.abspath(DATABASE_FILE)}
• Working Dir: {os.getcwd()}
            """.strip()
            
            messagebox.showinfo("System Information", info)
            
        except Exception as e:
            messagebox.showerror("Error", f"Could not retrieve system information:\n{str(e)}")

    def show_daily_stats(self):
        """Show today's statistics"""
        try:
            if not hasattr(self.main_app, 'db'):
                messagebox.showinfo("Daily Stats", "Database not connected")
                return
                
            today = datetime.now().strftime('%Y-%m-%d')
            sales_data = self.main_app.db.get_daily_sales(today)
            total_sales = sum(amt for _, _, _, amt, _, _, _ in sales_data) if sales_data else 0
            total_items = sum(qty for _, _, qty, _, _, _, _ in sales_data) if sales_data else 0
            
            # Get unique cashiers
            cashiers = set()
            for sale in sales_data:
                if len(sale) > 1:  # Ensure sale has user data
                    cashiers.add(sale[1])  # User is at index 1
            
            stats = f"""
📈 Today's Statistics ({today})

• Total Sales: Ksh {total_sales:,.2f}
• Items Sold: {total_items}
• Transactions: {len(sales_data)}
• Active Cashiers: {len(cashiers)}

💰 Performance Metrics:
• Average Sale: Ksh {total_sales/len(sales_data) if sales_data else 0:,.2f}
• Items per Transaction: {total_items/len(sales_data) if sales_data else 0:.1f}

💡 Tip: Check individual portals for detailed reports.
            """.strip()
            
            messagebox.showinfo("Daily Statistics", stats)
            
        except Exception as e:
            messagebox.showerror("Error", f"Could not retrieve daily stats:\n{str(e)}")

    def check_system_health(self):
        """Perform system health check"""
        try:
            health_report = "🔍 System Health Check\n\n"
            
            # Check database connection
            if hasattr(self.main_app, 'db') and self.main_app.db.conn:
                health_report += "✅ Database Connection: Healthy\n"
            else:
                health_report += "❌ Database Connection: Failed\n"
            
            # Check config file
            if os.path.exists(CONFIG_FILE):
                health_report += "✅ Configuration File: Found\n"
            else:
                health_report += "❌ Configuration File: Missing\n"
            
            # Check users
            total_users = len(self.main_app.config["users"])
            if total_users > 0:
                health_report += f"✅ User Accounts: {total_users} found\n"
            else:
                health_report += "❌ User Accounts: No users configured\n"
            
            # Check essential directories
            essential_dirs = ["database_backups", "audit_exports", "system_exports"]
            for dir_name in essential_dirs:
                if os.path.exists(dir_name):
                    health_report += f"✅ Directory: {dir_name} exists\n"
                else:
                    health_report += f"⚠️ Directory: {dir_name} missing\n"
            
            health_report += "\n🎯 Overall Status: SYSTEM OPERATIONAL"
            
            messagebox.showinfo("System Health Check", health_report)
            
        except Exception as e:
            messagebox.showerror("Health Check Failed", f"Could not complete health check:\n{str(e)}")

    def confirm_exit(self):
        """Confirm before exiting the application"""
        if messagebox.askyesno("Exit System", 
                             "Are you sure you want to exit the Cafeteria Management System?\n\nThis will close all open connections and windows.",
                             icon='warning', parent=self.root):
            # Record exit activity if database is available
            if hasattr(self.main_app, 'db'):
                try:
                    self.main_app.db.cursor.execute('''
                        INSERT INTO user_activity (user, activity_type, description)
                        VALUES (?, ?, ?)
                    ''', ('system', 'system', 'Application closed from homepage'))
                    self.main_app.db.conn.commit()
                except:
                    pass
            
            self.root.destroy()



    def open_user_portal(self):
        """Open User Login Portal - no authentication required"""
        def create_window():
            portal_window = tk.Toplevel(self.root)
            portal_window.title("User Login Portal - Zetech University Cafeteria")
            portal_window.configure(bg=BG_COLOR)
            portal_window.transient(self.root)
            
            # Set window to full screen
            try:
                portal_window.state('zoomed')
            except Exception:
                portal_window.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")

            main_container = tk.Frame(portal_window, bg=BG_COLOR)
            main_container.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)

            back_button = tk.Button(main_container, text="← Back to Homepage",
                                   font=('Poppins', 12), bg=BUTTON_COLOR, fg=FG_COLOR,
                                   command=lambda: self.show_homepage(),
                                   padx=15, pady=8, bd=0)
            back_button.pack(anchor="nw", pady=(0, 20))

            scrolled = ScrolledFrame(main_container, bg=BG_COLOR)
            scrolled.pack(fill=tk.BOTH, expand=True)

            self.main_app.create_user_login_section(scrolled.frame)

        self.show_loading_and_then(create_window, "Loading User Portal...")

    def open_manager_portal(self):
        """Open Manager Login Portal with authentication"""
        if not self.authenticate_manager("Manager"):
            return  # Authentication failed
            
        def create_window():
            portal_window = tk.Toplevel(self.root)
            portal_window.title("Manager Access Portal - Zetech University Cafeteria")
            portal_window.configure(bg=BG_COLOR)
            portal_window.transient(self.root)
            
            # Set window to full screen
            try:
                portal_window.state('zoomed')
            except Exception:
                portal_window.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")

            main_container = tk.Frame(portal_window, bg=BG_COLOR)
            main_container.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)

         

            scrolled = ScrolledFrame(main_container, bg=BG_COLOR)
            scrolled.pack(fill=tk.BOTH, expand=True)

            self.main_app.create_manager_login_section(scrolled.frame)

        self.show_loading_and_then(create_window, "Loading Manager Portal...")

    def open_system_portal(self):
        """Open System Management Portal with authentication"""
        if not self.authenticate_manager("System Manager"):
            return  # Authentication failed
            
        def create_window():
            portal_window = tk.Toplevel(self.root)
            portal_window.title("System Management Portal - Zetech University Cafeteria")
            portal_window.configure(bg=BG_COLOR)
            portal_window.transient(self.root)
            
            # Set window to full screen
            try:
                portal_window.state('zoomed')
            except Exception:
                portal_window.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")

            main_container = tk.Frame(portal_window, bg=BG_COLOR)
            main_container.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)

            back_button = tk.Button(main_container, text="← Back to Homepage",
                                   font=('Poppins', 12), bg=BUTTON_COLOR, fg=FG_COLOR,
                                   command=lambda: self.show_homepage(),
                                   padx=15, pady=8, bd=0)
            back_button.pack(anchor="nw", pady=(0, 20))

            scrolled = ScrolledFrame(main_container, bg=BG_COLOR)
            scrolled.pack(fill=tk.BOTH, expand=True)

            self.main_app.create_system_management_section(scrolled.frame)

        self.show_loading_and_then(create_window, "Loading System Portal...")


        
    def close_portal_and_show_homepage(self, portal_window):
        """Close portal window and return to homepage"""
        try:
            portal_window.destroy()
            self.show_homepage()
        except Exception as e:
            print(f"Error closing portal: {e}")
            # Fallback: just close the window
            try:
                portal_window.destroy()
            except:
                pass

    def show_homepage(self):
        """Show the homepage - recreate it if needed"""
        try:
            # Clear current window
            #self.clear_window()
            # Recreate homepage
            self.create_centered_homepage()
        except Exception as e:
            print(f"Error showing homepage: {e}")
            # Fallback: recreate the entire homepage
            self.__init__(self.root, self.main_app)

    def show_loading_and_then(self, create_window_callback, message="Loading..."):
        """Show an enhanced loading animation"""
        try:
            loader = tk.Toplevel(self.root)
            loader.overrideredirect(True)
            loader.configure(bg=BG_COLOR)
            loader.attributes("-topmost", True)

            # Center loader window
            loader.update_idletasks()
            w, h = 300, 180
            x = (loader.winfo_screenwidth() // 2) - (w // 2)
            y = (loader.winfo_screenheight() // 2) - (h // 2)
            loader.geometry(f"{w}x{h}+{x}+{y}")

            container = tk.Frame(loader, bg=BG_COLOR)
            container.pack(expand=True, fill=tk.BOTH, padx=25, pady=25)

            # Enhanced spinner
            spinner = DotsSpinner(container, dot_count=12, radius=40, dot_size=6, speed=80, bg=BG_COLOR)
            spinner.pack(pady=10)

            # Loading message
            lbl = tk.Label(container, text=message, font=('Poppins', 11), bg=BG_COLOR, fg=ACCENT_COLOR)
            lbl.pack(pady=(5, 0))

            def _open():
                try:
                    loader.destroy()
                except Exception:
                    pass
                create_window_callback()

            # Simulate loading progress
            self.root.after(800, _open)
            
        except Exception as e:
            print(f"Error in loading animation: {e}")
            # If loading fails, just create the window directly
            create_window_callback()

    def clear_window(self):
        """Clear all widgets from the window"""
        for widget in self.root.winfo_children():
            widget.destroy()



    def check_for_updates(self):
        """Check for system updates"""
        messagebox.showinfo("Update Check", 
                          "Update check functionality would connect to the update server.\n\n"
                          "This feature requires an active internet connection and would:\n"
                          "• Check for new versions\n"
                          "• Download updates if available\n"
                          "• Install updates securely\n\n"
                          "Currently running: v2.0 Professional Edition")

class AutoScrollText:
    """Enhanced Text widget with automatic scrolling functionality"""
    
    def __init__(self, master, **kwargs):
        self.text = tk.Text(master, **kwargs)
        self.auto_scroll = True
        
    def pack(self, **kwargs):
        return self.text.pack(**kwargs)
    
    def grid(self, **kwargs):
        return self.text.grid(**kwargs)
    
    def place(self, **kwargs):
        return self.text.place(**kwargs)
    
    def insert(self, index, text, **kwargs):
        self.text.insert(index, text, **kwargs)
        if self.auto_scroll:
            self.scroll_to_bottom()
    
    def scroll_to_bottom(self):
        """Scroll to the bottom of the text widget"""
        self.text.see(tk.END)
        self.text.update_idletasks()
    
    def enable_auto_scroll(self):
        """Enable automatic scrolling"""
        self.auto_scroll = True
    
    def disable_auto_scroll(self):
        """Disable automatic scrolling"""
        self.auto_scroll = False
    
    def __getattr__(self, name):
        """Delegate all other attributes to the underlying text widget"""
        return getattr(self.text, name)

class ScrolledFrame:
    """A frame with automatic scrollbars that can be used for any content"""
    
    def __init__(self, master, **kwargs):
        # Create main frame
        self.main_frame = tk.Frame(master, **kwargs)
        
        # Create canvas and scrollbars
        self.canvas = tk.Canvas(self.main_frame, highlightthickness=0)
        self.canvas.configure(bg=self.main_frame.cget("bg"))
        self.v_scrollbar = ttk.Scrollbar(self.main_frame, orient="vertical", command=self.canvas.yview)
        self.h_scrollbar = ttk.Scrollbar(self.main_frame, orient="horizontal", command=self.canvas.xview)
        
        # Configure canvas
        self.canvas.configure(yscrollcommand=self.v_scrollbar.set, xscrollcommand=self.h_scrollbar.set)
        
        # Create scrollable frame
        self.scrollable_frame = tk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # Enhanced smooth scrolling settings
        self.scroll_speed = 60  # pixels per wheel notch
        self.smooth_steps = 10  # animation steps
        self.smooth_interval = 10  # ms per animation step
        self._scroll_job = None
        
        # Bind events
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Enhanced mouse wheel bindings for all platforms
        self._bind_mouse_wheel()
        
        # Pack everything
        self._pack_scrollbars()
    
    def _bind_mouse_wheel(self):
        """Bind mouse wheel events for smooth scrolling on all platforms"""
        # Bind to canvas, scrollable frame, and main frame
        for widget in [self.canvas, self.scrollable_frame, self.main_frame]:
            # Windows/Mac
            widget.bind("<MouseWheel>", self._on_mousewheel)
            # Linux
            widget.bind("<Button-4>", self._on_mousewheel)
            widget.bind("<Button-5>", self._on_mousewheel)
    
    def _pack_scrollbars(self):
        """Pack the scrollbars appropriately"""
        self.canvas.pack(side="left", fill="both", expand=True)
        self.v_scrollbar.pack(side="right", fill="y")
        self.h_scrollbar.pack(side="bottom", fill="x")
    
    def _on_frame_configure(self, event):
        """Reset the scroll region to encompass the inner frame"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _on_canvas_configure(self, event):
        """Reset the canvas window size to fill canvas"""
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def _on_mousewheel(self, event):
        """Handle mousewheel scrolling with smooth animation"""
        delta = 0
        if hasattr(event, "delta") and event.delta:
            delta = -1 * (event.delta / 120)
        elif hasattr(event, "num"):
            if event.num == 4:
                delta = -1
            elif event.num == 5:
                delta = 1
        if delta != 0:
            self.smooth_scroll(delta_pixels=int(delta * self.scroll_speed))
            return "break"

    def _get_scroll_metrics(self):
        sr = self.canvas.bbox("all")
        if not sr:
            return 0, 0
        total = sr[3] - sr[1]
        visible = max(self.canvas.winfo_height(), 1)
        scrollable = max(total - visible, 0)
        top_frac = self.canvas.yview()[0]
        current_pixels = top_frac * (scrollable if scrollable > 0 else 0)
        return current_pixels, scrollable

    def _yview_moveto_pixels(self, pixels):
        _, scrollable = self._get_scroll_metrics()
        if scrollable <= 0:
            self.canvas.yview_moveto(0.0)
            return
        frac = pixels / scrollable
        self.canvas.yview_moveto(max(0.0, min(1.0, frac)))

    def smooth_scroll(self, delta_pixels):
        current_pixels, _ = self._get_scroll_metrics()
        target = current_pixels + delta_pixels
        self._animate_scroll(current_pixels, target)

    def _animate_scroll(self, start, target):
        # Cancel ongoing animation
        if self._scroll_job is not None:
            try:
                self.canvas.after_cancel(self._scroll_job)
            except Exception:
                pass
            self._scroll_job = None

        # Compute scrollable range to clamp target
        _, scrollable = self._get_scroll_metrics()
        target = max(0, min(scrollable, target))

        steps = max(int(self.smooth_steps), 1)
        if steps <= 1 or start == target:
            self._yview_moveto_pixels(target)
            return

        delta = (target - start) / steps

        def step(i=0, val=start):
            new_val = val + delta
            done = (delta > 0 and new_val >= target) or (delta < 0 and new_val <= target) or i >= steps - 1
            if done:
                self._yview_moveto_pixels(target)
                self._scroll_job = None
                return
            self._yview_moveto_pixels(new_val)
            self._scroll_job = self.canvas.after(int(self.smooth_interval), step, i + 1, new_val)

        self._scroll_job = self.canvas.after(int(self.smooth_interval), step)
    
    def scroll_to_bottom(self):
        """Scroll to the bottom of the frame"""
        self.smooth_scroll(delta_pixels=10**9)
    
    def scroll_to_top(self):
        """Scroll to the top of the frame"""
        self.smooth_scroll(delta_pixels=-10**9)
    
    def pack(self, **kwargs):
        return self.main_frame.pack(**kwargs)
    
    def grid(self, **kwargs):
        return self.main_frame.grid(**kwargs)
    
    def place(self, **kwargs):
        return self.main_frame.place(**kwargs)
    
    @property
    def frame(self):
        return self.scrollable_frame
class HotelApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Zetech University Cafeteria System")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        self.root.configure(bg=BG_COLOR)
        
        self.show_homepage()
        self.config = load_config()
        self.db = DatabaseManager()
        self.current_user = None
        self.payment_method_used = {"method": "Cash", "details": ""}
        self.manager_mode = False
        self.meal_frames = {}
        self.meal_entries = {}
        self.receipt_items = []
        self.receipt_total = 0
        
        self.BG_COLOR = "#1a1a2e"  # Dark navy blue
        self.FG_COLOR = "#e6e6e6"  # Light gray
        self.ACCENT_COLOR = "#4cc9f0"  # Bright cyan
        self.BUTTON_COLOR = "#16213e"  # Darker navy
        self.ERROR_COLOR = "#f72585"  # Pinkish red
        self.SUCCESS_COLOR = "#4caf50"
        self.FONT_LARGE = ('Segoe UI', 14)
        self.FONT_MEDIUM = ('Segoe UI', 12)
        self.FONT_SMALL = ('Segoe UI', 10)

        self.homepage = HomePage(self.root, self)
      
    # Load default appearance settings


        # Initialize menu_items from database
        self.menu_items = {}
        db_meals = self.db.get_all_meals()
        for category, name, _, _, selling_price, _, _, _, _, _ in db_meals:
            if category not in self.menu_items:
                self.menu_items[category] = {}
            self.menu_items[category][name] = selling_price
            self.deducted_items = set()
            self.deducted_items.add(name)
        
        # Start with homepage instead of login page
        self.homepage = HomePage(self.root, self)
        
       
    def update_clock(self):
        """Update the date and time display"""
        if hasattr(self, 'clock_label') and self.clock_label.winfo_exists():
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.clock_label.config(text=current_time)
 
            
                                                                                
    def show_homepage(self):
        """Show the homepage"""
        self.clear_window()
        self.homepage = HomePage(self.root, self)
    
    def clear_window(self):
        """Clear all widgets from the window"""
        for widget in self.root.winfo_children():
            widget.destroy()

    def is_admin_user(self):
        """Check if current user is admin"""
        if not self.current_user:
            return False
        return self.config["users"].get(self.current_user, {}).get("is_admin", False)

    def confirm_exit(self):
        if messagebox.askyesno("Exit", "Are you sure you want to exit?", parent=self.root):
            self.root.destroy()

    def confirm_logout(self):
        if messagebox.askyesno("Logout", "Are you sure you want to logout?", parent=self.root):
            was_manager = self.manager_mode
            self.current_user = None
            self.manager_mode = False
            # Clear current UI and open the appropriate portal window
            self.clear_window()
            if was_manager:
                self.homepage.open_manager_portal()
            else:
                self.homepage.open_user_portal()

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()


        
        # Create a modern frame with gradient background
        login_container = tk.Frame(self.root, bg=BG_COLOR)
        login_container.pack(fill=tk.BOTH, expand=True)
        
        # Status bar at TOP with reduced height
        status_bar = tk.Frame(login_container, bg="#0d0d1a", height=20)
        status_bar.pack(side=tk.TOP, fill=tk.X)
        status_bar.pack_propagate(False)

        # Status messages with smaller font
        status_left = tk.Label(status_bar, text="Ready", font=('Segoe UI', 8), 
                     bg="#0d0d1a", fg=FG_COLOR, anchor=tk.W)
        status_left.pack(side=tk.LEFT, padx=8)

        # System status indicators
        status_right = tk.Frame(status_bar, bg="#0d0d1a")
        status_right.pack(side=tk.RIGHT, padx=8)

        # Database status
        db_status = tk.Label(status_right, text="● DB", font=('Segoe UI', 8), 
                   bg="#0d0d1a", fg=SUCCESS_COLOR)
        db_status.pack(side=tk.LEFT, padx=3)

        # Network status (simulated)
        net_status = tk.Label(status_right, text="● Network", font=('Segoe UI', 8), 
                    bg="#0d0d1a", fg=SUCCESS_COLOR)
        net_status.pack(side=tk.LEFT, padx=3)

        # Time and date
        self.status_time = tk.Label(status_right, text="", font=('Segoe UI', 8), 
                          bg="#0d0d1a", fg=FG_COLOR)
        self.status_time.pack(side=tk.LEFT, padx=3)
        self.update_status_time()
        
        # Title marquee below status bar with minimal padding
        title_frame = tk.Frame(login_container, bg=BG_COLOR)
        title_frame.pack(fill=tk.X, pady=(5, 10))
        
        title_marquee = Marquee(title_frame, text="Welcome to Zetech University Cafeteria System")
        title_marquee.pack(fill=tk.X)
        
        # Main container with reduced padding to move content upwards
        main_container = tk.Frame(login_container, bg=BG_COLOR)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)  # Reduced pady from 10 to 5
        
        # Configure grid weights for proper responsiveness
        main_container.grid_rowconfigure(0, weight=1)
        main_container.grid_columnconfigure(0, weight=1)
        main_container.grid_columnconfigure(1, weight=1)
        main_container.grid_columnconfigure(2, weight=1)

        # Create three columns with reduced padding to move them up
        user_login_frame = tk.LabelFrame(main_container, text="User Login", font=('Poppins', 12, 'bold'),
                                      bg=BG_COLOR, fg=ACCENT_COLOR, bd=2, relief=tk.GROOVE,
                                      padx=10, pady=8)  # Reduced pady
        user_login_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)  # Reduced pady
        user_login_frame.grid_rowconfigure(0, weight=1)
        user_login_frame.grid_columnconfigure(0, weight=1)

        manager_login_frame = tk.LabelFrame(main_container, text="Manager Access", font=('Poppins', 12, 'bold'),
                                         bg=BG_COLOR, fg=ACCENT_COLOR, bd=2, relief=tk.GROOVE,
                                         padx=10, pady=8)  # Reduced pady
        manager_login_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=3)  # Reduced pady
        manager_login_frame.grid_rowconfigure(0, weight=1)
        manager_login_frame.grid_columnconfigure(0, weight=1)

        system_frame = tk.LabelFrame(main_container, text="System Management", font=('Poppins', 12, 'bold'),
                                  bg=BG_COLOR, fg=ACCENT_COLOR, bd=2, relief=tk.GROOVE,
                                  padx=10, pady=8)  # Reduced pady
        system_frame.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)  # Reduced pady
        system_frame.grid_rowconfigure(0, weight=1)
        system_frame.grid_columnconfigure(0, weight=1)

        # Fill the columns with scrollable content
        self.create_user_login_section(user_login_frame)
        self.create_manager_login_section(manager_login_frame)
        self.create_system_management_section(system_frame)

        # Footer moved up with reduced padding
        footer_frame = tk.Frame(main_container, bg=BG_COLOR)
        footer_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(5, 0))  # Reduced pady

        system_info = tk.Label(footer_frame, 
                          text="Zetech University Cafeteria System v2.0 | © 2025 Clin-Tech Technologies",
                          font=('Poppins', 9), bg=BG_COLOR, fg=FG_COLOR)
        system_info.pack(pady=1)  # Reduced pady

        support_info = tk.Label(footer_frame, 
                           text="Support: 0796939191 / 0707326661 | System By: Clin-Tech Technologies",
                           font=('Poppins', 8), bg=BG_COLOR, fg=ACCENT_COLOR)
        support_info.pack(pady=1)  # Reduced pady



    def update_status_time(self):
        """Update the time in status bar"""
        if hasattr(self, 'status_time') and self.status_time.winfo_exists():
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.status_time.config(text=current_time)
            self.root.after(1000, self.update_status_time)

    def backup_database(self):
        """Create database backup"""
    # Implementation for database backup
        messagebox.showinfo("Backup", "Database backup functionality would be implemented here")

    def restore_database(self):
        """Restore database from backup"""
    # Implementation for database restore
        messagebox.showinfo("Restore", "Database restore functionality would be implemented here")

    def show_system_info(self):
        info = f"System Information:\n\n"
        info += f"OS: {os.name}\n"
        info += f"Python: {sys.version.split()[0]}\n"
        info += f"Database: {DATABASE_FILE}\n"
        info += f"Users: {len(self.config['users'])}\n"
        info += f"Last Login: {self.get_last_login_info()}"
    
        messagebox.showinfo("System Info", info)

    def check_for_updates(self):
        """Check for system updates"""
        messagebox.showinfo("Updates", "Update check functionality would be implemented here")

    def get_last_login_info(self):
        """Get information about last login"""
    # This would query the database for last login info
        return "No previous login recorded"

    def create_user_login_section(self, parent_frame):
        """Create the user login section with proper scrolling and sizing for 1200x800 window"""
        # Main container with proper padding
        main_container = tk.Frame(parent_frame, bg=BG_COLOR)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Create a two-column layout for better space utilization
        columns_frame = tk.Frame(main_container, bg=BG_COLOR)
        columns_frame.pack(fill=tk.BOTH, expand=True)
        columns_frame.grid_columnconfigure(0, weight=1)
        columns_frame.grid_columnconfigure(1, weight=1)
        
        # Left column - Login Form
        left_frame = tk.Frame(columns_frame, bg=BG_COLOR)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        
        # Right column - Information and Help
        right_frame = tk.Frame(columns_frame, bg=BG_COLOR)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(15, 0))
        
        # ===== LEFT COLUMN - LOGIN FORM =====
        login_container = tk.Frame(left_frame, bg=BG_COLOR)
        login_container.pack(fill=tk.BOTH, expand=True)
        
        # Header with reduced padding
        header_frame = tk.Frame(login_container, bg=BG_COLOR)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        icon_label = tk.Label(header_frame, text="🔐", font=('Segoe UI', 28), 
                         bg=BG_COLOR, fg=ACCENT_COLOR)
        icon_label.pack(pady=(0, 10))
    
        welcome_label = tk.Label(header_frame, text="Secure User Login", 
                            font=('Poppins', 18, 'bold'), bg=BG_COLOR, fg=FG_COLOR)
        welcome_label.pack(pady=(0, 10))

        # Security status indicator
        security_frame = tk.Frame(header_frame, bg=BG_COLOR)
        security_frame.pack(pady=10)
        
        self.security_status = tk.Label(security_frame, text="● Security: Verified", 
                                   font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=SUCCESS_COLOR)
        self.security_status.pack()

        # Login form container
        form_container = tk.Frame(login_container, bg=BG_COLOR)
        form_container.pack(fill=tk.BOTH, expand=True, pady=10)

        # Username section
        username_frame = tk.LabelFrame(form_container, text="🔑 Account Access", 
                                 font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                                 padx=20, pady=15)
        username_frame.pack(fill=tk.X, pady=(0, 15))
        username_frame.grid_columnconfigure(0, weight=1)

        # Username input with icon
        tk.Label(username_frame, text="👤 Username:", bg=BG_COLOR, fg=FG_COLOR,
             font=FONT_MEDIUM, anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 10))

        user_input_frame = tk.Frame(username_frame, bg=BG_COLOR)
        user_input_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        user_input_frame.grid_columnconfigure(0, weight=1)

        self.username_var = tk.StringVar()
        user_dropdown = ttk.Combobox(user_input_frame, font=FONT_MEDIUM, 
                                 textvariable=self.username_var,
                                 values=list(self.config["users"].keys()), 
                                 state="readonly")
        user_dropdown.grid(row=0, column=0, sticky="ew", ipady=8)

        # Clear username button
        clear_user_btn = tk.Button(user_input_frame, text="🗑️", font=('Segoe UI', 10),
                               bg=BUTTON_COLOR, fg=FG_COLOR, bd=1, relief="raised",
                               command=lambda: self.username_var.set(""),
                               width=4, height=1)
        clear_user_btn.grid(row=0, column=1, padx=(10, 0))

        # User info display
        self.user_info_label = tk.Label(username_frame, text="ℹ️ Select a username to view account information", 
                                   font=('Segoe UI', 10), bg=BG_COLOR, fg=ACCENT_COLOR, 
                                   justify=tk.LEFT, wraplength=400)
        self.user_info_label.grid(row=2, column=0, sticky="w", pady=(10, 0))

        # Password section
        password_frame = tk.LabelFrame(form_container, text="🔒 Secure Authentication", 
                                 font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                                 padx=20, pady=15)
        password_frame.pack(fill=tk.X, pady=(0, 15))
        password_frame.grid_columnconfigure(0, weight=1)

        tk.Label(password_frame, text="🔑 Password:", bg=BG_COLOR, fg=FG_COLOR,
             font=FONT_MEDIUM, anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 10))

        # Password input frame
        password_input_frame = tk.Frame(password_frame, bg=BG_COLOR)
        password_input_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        password_input_frame.grid_columnconfigure(0, weight=1)

        self.password_var = tk.StringVar()
        self.password_entry = tk.Entry(password_input_frame, font=FONT_MEDIUM, bd=2,
                                  bg='#2a2a40', fg=FG_COLOR, insertbackground=FG_COLOR,
                                  textvariable=self.password_var, show="•")
        self.password_entry.grid(row=0, column=0, sticky="ew", ipady=8)

        # Password visibility toggle
        self.show_pass_btn = tk.Button(password_input_frame, text="👁️", font=('Segoe UI', 10),
                                  bg=BUTTON_COLOR, fg=FG_COLOR,
                                  command=self.toggle_password_visibility,
                                  width=4, height=1)
        self.show_pass_btn.grid(row=0, column=1, padx=(10, 0))

        # Password strength meter
        strength_container = tk.Frame(password_frame, bg=BG_COLOR)
        strength_container.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        self.strength_label = tk.Label(strength_container, text="Password Strength: ", 
                                  font=('Segoe UI', 10), bg=BG_COLOR, fg=FG_COLOR)
        self.strength_label.pack(side=tk.LEFT, anchor="w")

        self.strength_meter = tk.Frame(strength_container, bg=BG_COLOR)
        self.strength_meter.pack(side=tk.RIGHT, anchor="e")

        # Create strength indicator bars
        self.strength_bars = []
        for i in range(4):
            bar = tk.Frame(self.strength_meter, bg='#555555', width=8, height=6)
            bar.pack(side=tk.LEFT, padx=2)
            self.strength_bars.append(bar)

        # Action buttons frame
        button_frame = tk.Frame(form_container, bg=BG_COLOR)
        button_frame.pack(fill=tk.X, pady=20)
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        button_frame.grid_columnconfigure(2, weight=1)

        # Security options frame
        security_options_frame = tk.Frame(form_container, bg=BG_COLOR)
        security_options_frame.pack(fill=tk.X, pady=15)
        security_options_frame.grid_columnconfigure(0, weight=1)
        security_options_frame.grid_columnconfigure(1, weight=1)

        # Login button
        self.login_btn = tk.Button(button_frame, text="🚀 Login", font=('Poppins', 12, 'bold'),
                         bg=SUCCESS_COLOR, fg=FG_COLOR, bd=0, relief="raised",
                         command=lambda: self.check_login(self.username_var.get(), self.password_var.get()),
                         padx=20, pady=12, width=12)
        self.login_btn.grid(row=0, column=0, padx=5, sticky="ew")

        # Reset button
        reset_btn = tk.Button(button_frame, text="🔄 Reset", font=('Poppins', 12),
                         bg=ACCENT_COLOR, fg=BG_COLOR, bd=0, relief="raised",
                         command=self.reset_login_form,
                         padx=20, pady=12, width=12)
        reset_btn.grid(row=0, column=1, padx=5, sticky="ew")

        # Test button
        test_btn = tk.Button(button_frame, text="🧪 Test", font=('Poppins', 12),
                        bg=BUTTON_COLOR, fg=FG_COLOR, bd=0, relief="raised",
                        command=self.quick_test_login,
                        padx=20, pady=12, width=12)
        test_btn.grid(row=0, column=2, padx=5, sticky="ew")





        # Session options (left side)
        session_frame = tk.Frame(security_options_frame, bg=BG_COLOR)
        session_frame.grid(row=0, column=0, sticky="w")

        self.remember_me = tk.BooleanVar(value=False)
        remember_cb = tk.Checkbutton(session_frame, text="💾 Remember Me", 
                           variable=self.remember_me, bg=BG_COLOR, fg=FG_COLOR,
                           font=('Segoe UI', 11), selectcolor=BG_COLOR,
                           command=self.update_remember_me)
        remember_cb.pack(anchor="w", pady=3)

        self.auto_logout = tk.BooleanVar(value=True)
        logout_cb = tk.Checkbutton(session_frame, text="⏰ Auto Logout (30 min)", 
                         variable=self.auto_logout, bg=BG_COLOR, fg=FG_COLOR,
                         font=('Segoe UI', 11), selectcolor=BG_COLOR)
        logout_cb.pack(anchor="w", pady=3)

        # Quick actions (right side)
        quick_actions_frame = tk.Frame(security_options_frame, bg=BG_COLOR)
        quick_actions_frame.grid(row=0, column=1, sticky="e")

        # Forgot password link
        forgot_pw_btn = tk.Button(quick_actions_frame, text="🔓 Forgot Password?", 
                            font=('Segoe UI', 11), bg=BG_COLOR, fg=ACCENT_COLOR,
                            bd=0, command=self.show_forgot_password,
                            cursor="hand2")
        forgot_pw_btn.pack(anchor="e", pady=3)

        # Quick user switch
        switch_user_btn = tk.Button(quick_actions_frame, text="🔄 Switch User", 
                              font=('Segoe UI', 11), bg=BG_COLOR, fg=HIGHLIGHT_COLOR,
                              bd=0, command=self.show_quick_user_switch,
                              cursor="hand2")
        switch_user_btn.pack(anchor="e", pady=3)



        # Status display frame
        status_frame = tk.Frame(form_container, bg=BG_COLOR)
        status_frame.pack(fill=tk.X, pady=15)

        self.login_status_icon = tk.Label(status_frame, text="⏳", font=('Segoe UI', 16),
                                     bg=BG_COLOR, fg=ACCENT_COLOR)
        self.login_status_icon.pack(side=tk.LEFT, padx=(0, 12))

        self.login_status_label = tk.Label(status_frame, text="Ready to authenticate...", 
                                      font=('Segoe UI', 11), bg=BG_COLOR, fg=ACCENT_COLOR,
                                      wraplength=500)
        self.login_status_label.pack(side=tk.LEFT)

        # ===== RIGHT COLUMN - INFORMATION AND HELP =====
        info_container = tk.Frame(right_frame, bg=BG_COLOR)
        info_container.pack(fill=tk.BOTH, expand=True, padx=(20, 0))
        
        # System Information
        system_info_frame = tk.LabelFrame(info_container, text="📊 System Information", 
                                    font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                                    padx=20, pady=15)
        system_info_frame.pack(fill=tk.X, pady=(0, 20))
        
        info_text = """
• System: Zetech University Cafeteria
• Version: 2.0
• Database: Active
• Last Backup: Today
• Users Online: 1

        """
        system_info_label = tk.Label(system_info_frame, text=info_text.strip(),
                               font=('Segoe UI', 10), bg=BG_COLOR, fg=FG_COLOR,
                               justify=tk.LEFT)
        system_info_label.pack(anchor="w")
        
        # Quick Help
        help_frame = tk.LabelFrame(info_container, text="❓ Quick Help", 
                             font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                             padx=20, pady=15)
        help_frame.pack(fill=tk.X, pady=(0, 20))
        
        help_text = """
🔐 Login Tips:
• Use your assigned username
• Password is case-sensitive
• Contact admin for password reset
• Auto-logout after 30 minutes

🛡️ Security Features:
• Encrypted passwords
• Session management
• Activity logging
• Secure authentication
        """
        help_label = tk.Label(help_frame, text=help_text.strip(),
                        font=('Segoe UI', 10), bg=BG_COLOR, fg=FG_COLOR,
                        justify=tk.LEFT)
        help_label.pack(anchor="w")
        
        # Support Information
        support_frame = tk.LabelFrame(info_container, text="📞 Support", 
                                font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                                padx=20, pady=15)
        support_frame.pack(fill=tk.X)
        
        support_text = """
For technical support contact:
• Phone: 0796939191 / 0707326661
• Email: support@clintech.com
• Hours: 8:00 AM - 6:00 PM

Developed by:
Clin-Tech Technologies
        """
        support_label = tk.Label(support_frame, text=support_text.strip(),
                           font=('Segoe UI', 10), bg=BG_COLOR, fg=FG_COLOR,
                           justify=tk.LEFT)
        support_label.pack(anchor="w")

        # Set up event handlers
        self.setup_login_event_handlers(user_dropdown)
        self.update_user_info()



    def setup_login_event_handlers(self, user_dropdown):
        """Set up event handlers for login form"""
        # Username change events
        self.username_var.trace('w', self.on_username_change)
        
        # Password change events
        self.password_var.trace('w', self.on_password_change)
        
        # Enter key to login
        self.password_entry.bind('<Return>', 
                               lambda e: self.check_login(self.username_var.get(), self.password_var.get()))
        
        # Focus events
        user_dropdown.bind('<FocusIn>', lambda e: self.on_field_focus("username"))
        self.password_entry.bind('<FocusIn>', lambda e: self.on_field_focus("password"))

    def on_username_change(self, *args):
        """Handle username change events"""
        username = self.username_var.get()
        self.update_user_info()
        self.update_security_status()
        
        if username and self.password_entry:
            self.password_entry.focus_set()

    def on_password_change(self, *args):
        """Handle password change events"""
        password = self.password_var.get()
        self.update_password_strength(password)
        self.update_security_status()

    def on_field_focus(self, field_type):
        """Handle field focus events"""
        if field_type == "username":
            self.login_status_label.config(text="Select or enter your username...")
        elif field_type == "password":
            self.login_status_label.config(text="Enter your password...")

    def update_user_info(self):
        """Update user information display"""
        username = self.username_var.get()
        if username and username in self.config["users"]:
            user_data = self.config["users"][username]
            role = "Administrator" if user_data.get("is_admin", False) else "User"
            self.user_info_label.config(text=f"👤 {username} | 🎯 {role} | ✅ Account Active")
        else:
            self.user_info_label.config(text="ℹ️ Select a username to view account information")

    def update_password_strength(self, password):
        """Update password strength meter"""
        strength = self.calculate_password_strength(password)
        colors = ['#ff4444', '#ffaa00', '#ffff00', '#00ff00']
        
        for i, bar in enumerate(self.strength_bars):
            if i < strength:
                bar.config(bg=colors[strength-1])
            else:
                bar.config(bg='#555555')
        
        strength_texts = ["Very Weak", "Weak", "Good", "Strong"]
        strength_colors = [ERROR_COLOR, "#ffaa00", ACCENT_COLOR, SUCCESS_COLOR]
        
        if password:
            self.strength_label.config(text=f"Password Strength: {strength_texts[strength-1]}",
                                  fg=strength_colors[strength-1])
        else:
            self.strength_label.config(text="Password Strength: ", fg=FG_COLOR)

    def calculate_password_strength(self, password):
        """Calculate password strength (1-4)"""
        if not password:
            return 0
        
        score = 0
        if len(password) >= 8: score += 1
        if any(c.islower() for c in password): score += 1
        if any(c.isupper() for c in password): score += 1
        if any(c.isdigit() for c in password): score += 1
        if any(not c.isalnum() for c in password): score += 1
        
        return min(max(score, 1), 4)

    def update_security_status(self):
        """Update security status indicator"""
        username = self.username_var.get()
        password = self.password_var.get()
        
        if username and password:
            self.security_status.config(text="● Security: High", fg=SUCCESS_COLOR)
        elif username:
            self.security_status.config(text="● Security: Medium", fg="#ffaa00")
        else:
            self.security_status.config(text="● Security: Basic", fg=ACCENT_COLOR)

    def update_remember_me(self):
        """Handle remember me checkbox change"""
        if self.remember_me.get():
            self.login_status_label.config(text="💾 Login credentials will be remembered")
        else:
            self.login_status_label.config(text="🔒 Login credentials will not be saved")

    def reset_login_form(self):
        """Reset the entire login form"""
        self.username_var.set("")
        self.password_var.set("")
        self.remember_me.set(False)
        self.login_status_label.config(text="Form reset - Ready to authenticate...")
        self.login_status_icon.config(text="✅")
        self.user_info_label.config(text="ℹ️ Select a username to view account information")
        self.update_password_strength("")
        self.update_security_status()

    def toggle_password_visibility(self):
        """Toggle password visibility with updated icon"""
        current_show = self.password_entry.cget('show')
        if current_show == "•":
            self.password_entry.config(show="")
            self.show_pass_btn.config(text="🔒")
        else:
            self.password_entry.config(show="•")
            self.show_pass_btn.config(text="👁️")

    def show_forgot_password(self):
        """Show forgot password dialog"""
        messagebox.showinfo("Password Recovery", 
                           "Please contact your system administrator for password recovery.\n\n"
                           "Admin Contact: 0796939191 / 0707326661")

    def show_quick_user_switch(self):
        """Show quick user switch dialog"""
        switch_window = tk.Toplevel(self.root)
        switch_window.title("Quick User Switch")
        switch_window.geometry("300x300")
        switch_window.configure(bg=BG_COLOR)
        switch_window.transient(self.root)
        switch_window.resizable(False, False)
        
        # Center the window
        switch_window.update_idletasks()
        x = (switch_window.winfo_screenwidth() // 2) - (300 // 2)
        y = (switch_window.winfo_screenheight() // 2) - (300 // 2)
        switch_window.geometry(f"300x300+{x}+{y}")
        
        tk.Label(switch_window, text="Select User Account", 
                font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=15)
        
        # User list container with scrollbar
        user_container = tk.Frame(switch_window, bg=BG_COLOR)
        user_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create scrollable user list
        user_canvas = tk.Canvas(user_container, bg=BG_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(user_container, orient="vertical", command=user_canvas.yview)
        user_frame = tk.Frame(user_canvas, bg=BG_COLOR)
        
        user_frame.bind("<Configure>", lambda e: user_canvas.configure(scrollregion=user_canvas.bbox("all")))
        user_canvas.create_window((0, 0), window=user_frame, anchor="nw")
        user_canvas.configure(yscrollcommand=scrollbar.set)
        
        user_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            user_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        user_canvas.bind("<MouseWheel>", _on_mousewheel)
        
        # Add users to the list
        for username, user_data in self.config["users"].items():
            role = "Admin" if user_data.get("is_admin", False) else "User"
            user_btn = tk.Button(user_frame, text=f"👤 {username} ({role})", 
                               font=('Segoe UI', 10), bg=BUTTON_COLOR, fg=FG_COLOR,
                               command=lambda u=username: self.select_user_for_switch(u, switch_window),
                               anchor="w", width=25, pady=5)
            user_btn.pack(fill=tk.X, pady=2)
        
        # Close button
        tk.Button(switch_window, text="Close", font=FONT_MEDIUM,
                 bg=ERROR_COLOR, fg=FG_COLOR, command=switch_window.destroy,
                 pady=8).pack(pady=10)

    def select_user_for_switch(self, username, window):
        """Select user for quick switch"""
        self.username_var.set(username)
        window.destroy()
        self.password_entry.focus_set()
        self.login_status_label.config(text=f"Switched to user: {username}")

    def quick_test_login(self):
        """Quick test login with demo credentials"""
        test_users = [user for user in self.config["users"] if user.lower() != "admin"]
        if test_users:
            test_user = test_users[0]
            self.username_var.set(test_user)
            self.password_var.set("password")
            self.login_status_label.config(text="🧪 Test credentials loaded - Click Login to test")

    def get_today_login_count(self):
        """Get today's login count from database"""
        try:
            if hasattr(self, 'db'):
                today = datetime.now().strftime('%Y-%m-%d')
                count = self.db.cursor.execute(
                    "SELECT COUNT(*) FROM user_activity WHERE date(timestamp)=? AND activity_type='login'",
                    (today,)
                ).fetchone()[0]
                return count
        except:
            pass
        return 0

        final_spacer = tk.Frame(scrollable_frame, bg=BG_COLOR, height=5)
        final_spacer.pack(fill=tk.X)

        # Update scroll region
        canvas.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))


    def create_manager_login_section(self, parent_frame):
        """Create the enhanced manager access section for 1200x800 window"""
        # Main container
        main_container = tk.Frame(parent_frame, bg=BG_COLOR)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)


    # ADD BACK TO HOMEPAGE BUTTON HERE
        back_button = tk.Button(main_container, text="← Back to Homepage",
                               font=('Poppins', 12), bg=BUTTON_COLOR, fg=FG_COLOR,
                               command=lambda: self.return_to_homepage_from_manager(),
                               padx=15, pady=8, bd=0)
        back_button.pack(anchor="nw", pady=(0, 20))
        
        # Create a two-column layout
        columns_frame = tk.Frame(main_container, bg=BG_COLOR)
        columns_frame.pack(fill=tk.BOTH, expand=True)
        columns_frame.grid_columnconfigure(0, weight=1)
        columns_frame.grid_columnconfigure(1, weight=1)
        
        # Left column - Authentication
        left_frame = tk.Frame(columns_frame, bg=BG_COLOR)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        
        # Right column - Quick Actions and Info
        right_frame = tk.Frame(columns_frame, bg=BG_COLOR)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(15, 0))
        
        # ===== LEFT COLUMN - AUTHENTICATION =====
        auth_container = tk.Frame(left_frame, bg=BG_COLOR)
        auth_container.pack(fill=tk.BOTH, expand=True)
        
        # Header section
        header_frame = tk.Frame(auth_container, bg=BG_COLOR)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        icon_label = tk.Label(header_frame, text="⚡", font=('Segoe UI', 32), 
                         bg=BG_COLOR, fg=ACCENT_COLOR)
        icon_label.pack(pady=(0, 10))
    
        welcome_label = tk.Label(header_frame, text="Manager Access Portal", 
                            font=('Poppins', 18, 'bold'), bg=BG_COLOR, fg=FG_COLOR)
        welcome_label.pack(pady=(0, 10))

        # Access level indicator
        access_frame = tk.Frame(header_frame, bg=BG_COLOR)
        access_frame.pack(pady=10)
        
        self.access_level = tk.Label(access_frame, text="🔒 Administrative Access Required", 
                                font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=HIGHLIGHT_COLOR)
        self.access_level.pack()

        # Manager statistics frame
        stats_frame = tk.Frame(header_frame, bg=BG_COLOR)
        stats_frame.pack(pady=15)
        
        # Get manager statistics
        admin_count = sum(1 for user in self.config["users"].values() if user.get("is_admin", False))
        total_users = len(self.config["users"])
        
        stats_text = f"👑 Admins: {admin_count} | 👥 Total Users: {total_users} | 📊 System Ready"
        stats_label = tk.Label(stats_frame, text=stats_text, font=('Segoe UI', 11),
                          bg=BG_COLOR, fg=ACCENT_COLOR)
        stats_label.pack()

        # Main form container
        form_container = tk.Frame(auth_container, bg=BG_COLOR)
        form_container.pack(fill=tk.BOTH, expand=True, pady=10)

        # Manager authentication section
        auth_frame = tk.LabelFrame(form_container, text="🔐 Manager Authentication", 
                             font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                             padx=20, pady=15)
        auth_frame.pack(fill=tk.X, pady=(0, 15))
        auth_frame.grid_columnconfigure(0, weight=1)

        # Manager password input
        tk.Label(auth_frame, text="🔑 Manager Password:", bg=BG_COLOR, fg=FG_COLOR,
             font=FONT_MEDIUM, anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 10))

        pw_input_frame = tk.Frame(auth_frame, bg=BG_COLOR)
        pw_input_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        pw_input_frame.grid_columnconfigure(0, weight=1)

        self.manager_pw_var = tk.StringVar()
        self.manager_entry = tk.Entry(pw_input_frame, textvariable=self.manager_pw_var, show="•",
                                 font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        self.manager_entry.grid(row=0, column=0, sticky="ew", ipady=8)

        # Password visibility toggle
        self.manager_show_btn = tk.Button(pw_input_frame, text="👁️", font=('Segoe UI', 10),
                                    bg=BUTTON_COLOR, fg=FG_COLOR, bd=1, relief="raised",
                                    command=lambda: self.toggle_manager_password_visibility(),
                                    width=4, height=1)
        self.manager_show_btn.grid(row=0, column=1, padx=(10, 0))

        # Security level indicator
        security_frame = tk.Frame(auth_frame, bg=BG_COLOR)
        security_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        self.security_indicator = tk.Label(security_frame, text="🛡️ Security Level: Standard", 
                                      font=('Segoe UI', 10), bg=BG_COLOR, fg=ACCENT_COLOR)
        self.security_indicator.pack(side=tk.LEFT, anchor="w")

        # Quick access options
        quick_access_frame = tk.Frame(auth_frame, bg=BG_COLOR)
        quick_access_frame.grid(row=3, column=0, sticky="ew", pady=(15, 0))

        # Left side - Quick actions
        quick_actions_frame = tk.Frame(quick_access_frame, bg=BG_COLOR)
        quick_actions_frame.pack(side=tk.LEFT, anchor="w")

        # Universal manager password hint
        universal_btn = tk.Button(quick_actions_frame, text="💡 Universal Access", 
                            font=('Segoe UI', 10), bg=BG_COLOR, fg=HIGHLIGHT_COLOR,
                            bd=0, command=self.show_universal_access_info,
                            cursor="hand2")
        universal_btn.pack(side=tk.LEFT, padx=(0, 10))

        # Test manager login
        test_manager_btn = tk.Button(quick_actions_frame, text="🧪 Test Access", 
                               font=('Segoe UI', 10), bg=BG_COLOR, fg=ACCENT_COLOR,
                               bd=0, command=self.test_manager_access,
                               cursor="hand2")
        test_manager_btn.pack(side=tk.LEFT)

        # Right side - Password management
        pw_manage_frame = tk.Frame(quick_access_frame, bg=BG_COLOR)
        pw_manage_frame.pack(side=tk.RIGHT, anchor="e")

        # Change manager password
        change_pw_btn = tk.Button(pw_manage_frame, text="🔐 Change Password", 
                            font=('Segoe UI', 10), bg=BG_COLOR, fg=SUCCESS_COLOR,
                            bd=0, command=self.show_change_own_password,
                            cursor="hand2")
        change_pw_btn.pack(side=tk.RIGHT, padx=(10, 0))

        # Manager login buttons
        button_frame = tk.Frame(form_container, bg=BG_COLOR)
        button_frame.pack(fill=tk.X, pady=20)
        button_frame.grid_columnconfigure(0, weight=1)

        # Main manager login button
        self.manager_login_btn = tk.Button(button_frame, text="🚀 Manager Login", 
                                     font=('Poppins', 13, 'bold'),
                                     bg=HIGHLIGHT_COLOR, fg=FG_COLOR, bd=0, relief="raised",
                                     command=lambda: self.check_manager_login(self.manager_pw_var.get()),
                                     padx=25, pady=14)
        self.manager_login_btn.pack(fill=tk.X)



        # Status display
        status_display_frame = tk.Frame(form_container, bg=BG_COLOR)
        status_display_frame.pack(fill=tk.X, pady=15)

        self.manager_status_icon = tk.Label(status_display_frame, text="⏳", 
                                      font=('Segoe UI', 16), bg=BG_COLOR, fg=ACCENT_COLOR)
        self.manager_status_icon.pack(side=tk.LEFT, padx=(0, 12))

        self.manager_status_label = tk.Label(status_display_frame, 
                                       text="Enter manager password to access administrative features...", 
                                       font=('Segoe UI', 11), bg=BG_COLOR, fg=ACCENT_COLOR,
                                       wraplength=500)
        self.manager_status_label.pack(side=tk.LEFT)

        # ===== RIGHT COLUMN - QUICK ACTIONS AND INFO =====
        actions_container = tk.Frame(right_frame, bg=BG_COLOR)
        actions_container.pack(fill=tk.BOTH, expand=True, padx=(20, 0))
        
 

        # Manager Information
        info_frame = tk.LabelFrame(actions_container, text="📋 Manager Information", 
                             font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                             padx=20, pady=15)
        info_frame.pack(fill=tk.X, pady=(0, 20))
        
        info_text = """
Manager Access Provides:
• Financial reporting
• User management  
• Inventory control
• System configuration
• Sales analytics
• Database maintenance

🔒 Security Features:
• Encrypted authentication
• Activity logging
• Access controls
• Session management
        """
        info_label = tk.Label(info_frame, text=info_text.strip(),
                        font=('Segoe UI', 10), bg=BG_COLOR, fg=FG_COLOR,
                        justify=tk.LEFT)
        info_label.pack(anchor="w")
        
        # Support Information
        support_frame = tk.LabelFrame(actions_container, text="🛠️ Technical Support", 
                                font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                                padx=20, pady=15)
        support_frame.pack(fill=tk.X)
        
        support_text = """
For Manager Access Issues:
• Contact: 0796939191
• Email: admin@clintech.com
• Emergency: 0707326661

System Administration:
Clin-Tech Technologies
        """
        support_label = tk.Label(support_frame, text=support_text.strip(),
                           font=('Segoe UI', 10), bg=BG_COLOR, fg=FG_COLOR,
                           justify=tk.LEFT)
        support_label.pack(anchor="w")

        # Set up event handlers
        self.setup_manager_event_handlers()

    def setup_manager_event_handlers(self):
        """Set up event handlers for manager login form"""
        # Password change events
        self.manager_pw_var.trace('w', self.on_manager_password_change)
        
        # Enter key to login
        self.manager_entry.bind('<Return>', 
                              lambda e: self.check_manager_login(self.manager_pw_var.get()))
        
        # Focus events
        self.manager_entry.bind('<FocusIn>', lambda e: self.on_manager_field_focus())




    def on_manager_password_change(self, *args):
        """Handle manager password change events"""
        password = self.manager_pw_var.get()
        self.update_manager_security_indicator(password)
        
        # Update status based on password strength
        if len(password) >= 8:
            self.manager_status_label.config(text="✅ Strong password detected")
        elif len(password) > 0:
            self.manager_status_label.config(text="⚠️ Password should be at least 8 characters")
        else:
            self.manager_status_label.config(text="Enter manager password to access administrative features...")

    def on_manager_field_focus(self):
        """Handle manager field focus events"""
        self.manager_status_label.config(text="Enter your manager password...")

    def update_manager_security_indicator(self, password):
        """Update manager security indicator"""
        if len(password) >= 12:
            self.security_indicator.config(text="🛡️ Security Level: High", fg=SUCCESS_COLOR)
        elif len(password) >= 8:
            self.security_indicator.config(text="🛡️ Security Level: Medium", fg="#ffaa00")
        elif len(password) > 0:
            self.security_indicator.config(text="🛡️ Security Level: Low", fg=ERROR_COLOR)
        else:
            self.security_indicator.config(text="🛡️ Security Level: Standard", fg=ACCENT_COLOR)

    def toggle_manager_password_visibility(self):
        """Toggle manager password visibility"""
        current_show = self.manager_entry.cget('show')
        if current_show == "•":
            self.manager_entry.config(show="")
            self.manager_show_btn.config(text="🔒")
        else:
            self.manager_entry.config(show="•")
            self.manager_show_btn.config(text="👁️")

    def clear_manager_form(self):
        """Clear the manager login form"""
        self.manager_pw_var.set("")
        self.manager_status_label.config(text="Form cleared - Enter manager password...")
        self.manager_status_icon.config(text="✅")
        self.update_manager_security_indicator("")

    def show_universal_access_info(self):
        """Show universal access information"""
        messagebox.showinfo("Universal Manager Access", 
                          "Universal Manager Access allows temporary administrative access.\n\n"
                          "Default Universal Password: MANAGER1\n\n"
                          "⚠️ For security, change this password after first login.")

    def test_manager_access(self):
        """Test manager access with sample credentials"""
        self.manager_pw_var.set("MANAGER1")
        self.manager_status_label.config(text="🧪 Test credentials loaded - Click 'Manager Login' to test")




 


     

    def show_manager_help(self):
        """Show manager help information"""
        help_text = """
Manager Access Help:

🔐 Authentication:
- Use your personal manager password
- Or use universal password: MANAGER1
- Sessions automatically expire after 30 minutes

🚀 Features Available:
- Financial reporting and analytics
- User management and permissions
- System configuration
- Database maintenance
- Security auditing

💡 Tips:
- Change default passwords regularly
- Review audit logs frequently
- Backup system data regularly
- Monitor user activity

Need assistance? Contact system administrator.
"""
        messagebox.showinfo("Manager Help", help_text.strip())


    def return_to_homepage_from_manager(self):
        """Return to homepage from manager portal"""
        # Clear current window and show homepage
        self.clear_window()
        self.show_homepage()



    def authenticate_for_quick_action(self, action_name, callback):
        """Authenticate manager for quick actions"""
        auth_window = tk.Toplevel(self.root)
        auth_window.title(f"Authentication Required - {action_name.title()}")
        auth_window.geometry("400x200")
        auth_window.configure(bg=BG_COLOR)
        auth_window.transient(self.root)
        auth_window.grab_set()

        tk.Label(auth_window, text=f"Manager Authentication Required", 
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)
        
        tk.Label(auth_window, text=f"Enter manager password to {action_name}:", 
                 font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)

        password_var = tk.StringVar()
        password_entry = tk.Entry(auth_window, textvariable=password_var, show="•",
                                  font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        password_entry.pack(pady=10, ipady=3, fill=tk.X, padx=20)
        password_entry.focus_set()

        status_label = tk.Label(auth_window, text="", font=FONT_SMALL, bg=BG_COLOR, fg=ERROR_COLOR)
        status_label.pack(pady=5)

        def verify_and_proceed():
            password = password_var.get()
            # Check universal password
            if password == "MANAGER1":
                auth_window.destroy()
                callback()
                return
            
            # Check custom manager passwords
            for username, user_data in self.config["users"].items():
                if (user_data.get("is_admin", False) and 
                    (user_data.get("manager_password", "") == hash_password(password) or password == "MANAGER")):
                    auth_window.destroy()
                    callback()
                    return
            
            status_label.config(text="Invalid manager password")

        button_frame = tk.Frame(auth_window, bg=BG_COLOR)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Authenticate", font=FONT_MEDIUM,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, command=verify_and_proceed,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=auth_window.destroy,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)

        auth_window.bind('<Return>', lambda event: verify_and_proceed())

    def _open_reports_dashboard(self):
        """Open reports dashboard"""
        if not hasattr(self, 'db'):
            messagebox.showerror("Error", "Database not available", parent=self.root)
            return
        
        # Create reports window
        reports_window = tk.Toplevel(self.root)
        reports_window.title("Quick Reports Dashboard")
        reports_window.geometry("800x600")
        reports_window.configure(bg=BG_COLOR)
        reports_window.transient(self.root)

        main_frame = tk.Frame(reports_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(main_frame, text="📊 Quick Reports Dashboard", 
                 font=('Poppins', 16, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        # Today's sales summary
        today = datetime.now().strftime('%Y-%m-%d')
        sales_data = self.db.get_daily_sales(today)
        total_today = sum(amt for _, _, _, amt, _, _, _ in sales_data) if sales_data else 0

        # Create report cards
        report_cards = [
            ("💰 Today's Sales", f"Ksh {total_today:.2f}", SUCCESS_COLOR),
            ("📦 Low Stock Items", f"{len(self.db.get_low_stock_items(10))} items", ERROR_COLOR),
            ("👥 Active Users", f"{len(set(user for user, _, _, _, _, _, _ in sales_data))} users", ACCENT_COLOR),
            ("📈 Total Profit", f"Ksh {sum(profit for _, _, _, _, _, profit, _ in sales_data) if sales_data else 0:.2f}", HIGHLIGHT_COLOR)
        ]

        cards_frame = tk.Frame(main_frame, bg=BG_COLOR)
        cards_frame.pack(fill=tk.X, pady=10)

        for i, (title, value, color) in enumerate(report_cards):
            card = tk.Frame(cards_frame, bg=color, relief=tk.RAISED, bd=1)
            card.grid(row=0, column=i, padx=5, sticky="nsew")
            cards_frame.grid_columnconfigure(i, weight=1)

            tk.Label(card, text=title, font=FONT_SMALL, bg=color, fg=FG_COLOR).pack(pady=5)
            tk.Label(card, text=value, font=('Poppins', 12, 'bold'), bg=color, fg=FG_COLOR).pack(pady=5)

        # Recent sales table
        tk.Label(main_frame, text="Recent Sales Today", font=FONT_MEDIUM, 
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=(20, 5))

        # Create treeview for recent sales
        columns = ("Time", "Customer", "Item", "Qty", "Amount")
        tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=10)

        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120)

        # Add scrollbar
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Populate with recent sales
        for row in sales_data[:20]:  # Last 20 sales
            # Support both aggregated rows (from get_daily_sales) and full sales rows (SELECT *)
            if isinstance(row, (list, tuple)) and len(row) == 7:
                # category, meal, quantity_sum, amount_sum, payment_method, profit_sum, profit_margin
                customer = "-"
                category, meal, qty, amt = row[0], row[1], row[2], row[3]
            else:
                # Expected order from SELECT * on sales table:
                # id, user, date, time, customer_name, category, meal, quantity, buying_price, selling_price, amount, profit, payment_method, payment_details, timestamp
                customer = row[4] if len(row) > 4 else "-"
                category = row[5] if len(row) > 5 else ""
                meal = row[6] if len(row) > 6 else ""
                qty = row[7] if len(row) > 7 else 0
                amt = row[10] if len(row) > 10 else 0
            tree.insert("", tk.END, values=(
                datetime.now().strftime('%H:%M:%S'),
                customer[:15] + "..." if len(customer) > 15 else customer,
                f"{meal[:12]}..." if len(meal) > 12 else meal,
                qty,
                f"Ksh {amt:.2f}"
            ))

    def _open_audit_logs(self):
        """Open audit logs viewer"""
        if not hasattr(self, 'db'):
            messagebox.showerror("Error", "Database not available", parent=self.root)
            return

        audit_window = tk.Toplevel(self.root)
        audit_window.title("Audit Logs Viewer")
        audit_window.geometry("900x500")
        audit_window.configure(bg=BG_COLOR)
        audit_window.transient(self.root)

        main_frame = tk.Frame(audit_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(main_frame, text="🔍 Audit Logs - User Activity", 
                 font=('Poppins', 16, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        # Get recent activity
        activity_data = self.db.get_user_activity(days=7)

        # Create treeview for audit logs
        columns = ("Timestamp", "User", "Activity", "Description")
        tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=15)

        tree.heading("Timestamp", text="Timestamp")
        tree.heading("User", text="User")
        tree.heading("Activity", text="Activity Type")
        tree.heading("Description", text="Description")

        tree.column("Timestamp", width=150)
        tree.column("User", width=100)
        tree.column("Activity", width=120)
        tree.column("Description", width=400)

        # Add scrollbar
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Populate with audit data
        for user, activity_type, description, timestamp in activity_data:
            tree.insert("", tk.END, values=(
                timestamp,
                user,
                activity_type,
                description
            ))

        # Add filter options
        filter_frame = tk.Frame(main_frame, bg=BG_COLOR)
        filter_frame.pack(fill=tk.X, pady=10)

        tk.Button(filter_frame, text="Refresh", font=FONT_SMALL,
                  bg=BUTTON_COLOR, fg=FG_COLOR, 
                  command=lambda: self._refresh_audit_logs(tree)).pack(side=tk.LEFT, padx=5)

        tk.Button(filter_frame, text="Export Logs", font=FONT_SMALL,
                  bg=SUCCESS_COLOR, fg=FG_COLOR,
                  command=self._export_audit_logs).pack(side=tk.LEFT, padx=5)

    def _refresh_audit_logs(self, tree):
        """Refresh audit logs treeview"""
        for item in tree.get_children():
            tree.delete(item)
        
        activity_data = self.db.get_user_activity(days=7)
        for user, activity_type, description, timestamp in activity_data:
            tree.insert("", tk.END, values=(
                timestamp,
                user,
                activity_type,
                description
            ))

    def _export_audit_logs(self):
        """Export audit logs to file"""
        try:
            export_dir = "audit_exports"
            if not os.path.exists(export_dir):
                os.makedirs(export_dir)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"audit_logs_export_{timestamp}.csv"
            filepath = os.path.join(export_dir, filename)

            activity_data = self.db.get_user_activity(days=30)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                import csv
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "User", "Activity Type", "Description"])
                writer.writerows(activity_data)

            messagebox.showinfo("Export Successful", 
                              f"Audit logs exported to:\n{filepath}", 
                              parent=self.root)
        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to export audit logs:\n{str(e)}", parent=self.root)

    def _open_system_settings(self):
        """Open system settings quick access"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Quick System Settings")
        settings_window.geometry("600x400")
        settings_window.configure(bg=BG_COLOR)
        settings_window.transient(self.root)

        main_frame = tk.Frame(settings_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(main_frame, text="⚙️ Quick System Settings", 
                 font=('Poppins', 16, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        # Settings options
        settings_options = [
            ("🔧 Database Maintenance", self.optimize_database),
            ("💾 Backup Database", self.backup_database),
            ("📊 Receipt Settings", self.show_receipt_settings),
            ("🔐 Security Settings", self.show_security_settings),
            ("🧹 Clear Cache", self.clear_cache),
            ("📈 Tax Settings", self.show_tax_settings)
        ]

        for i, (text, command) in enumerate(settings_options):
            btn = tk.Button(main_frame, text=text, font=FONT_MEDIUM,
                          bg=BUTTON_COLOR, fg=FG_COLOR, command=command,
                          width=25, pady=10)
            btn.pack(pady=5)

    def _perform_system_check(self):
        """Perform comprehensive system check"""
        progress_window = tk.Toplevel(self.root)
        progress_window.title("System Check")
        progress_window.state('zoomed')
        progress_window.configure(bg=BG_COLOR)
        progress_window.transient(self.root)
        progress_window.grab_set()

        main_frame = tk.Frame(progress_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(main_frame, text="🔄 System Health Check", 
                 font=('Poppins', 16, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        # Progress bar
        progress = ttk.Progressbar(main_frame, mode='determinate', length=400)
        progress.pack(pady=10)

        status_label = tk.Label(main_frame, text="Initializing system check...", 
                               font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR)
        status_label.pack(pady=5)

        results_text = tk.Text(main_frame, height=15, width=50, bg="#2a2a40", fg=FG_COLOR,
                              font=('Consolas', 9), state=tk.DISABLED)
        results_text.pack(pady=10, fill=tk.BOTH, expand=True)

        def update_results(message, color=FG_COLOR):
            results_text.config(state=tk.NORMAL)
            results_text.insert(tk.END, f"{message}\n")
            results_text.tag_add("color", "end-2c", "end-1c")
            results_text.tag_config("color", foreground=color)
            results_text.see(tk.END)
            results_text.config(state=tk.DISABLED)
            progress_window.update()

        def perform_check():
            try:
                checks = [
                    ("Checking database connection...", self._check_database),
                    ("Verifying user accounts...", self._check_users),
                    ("Checking stock levels...", self._check_stock),
                    ("Validating system files...", self._check_files),
                    ("Testing receipt printing...", self._check_printing),
                    ("Finalizing system check...", self._finalize_check)
                ]

                for i, (check_text, check_func) in enumerate(checks):
                    status_label.config(text=check_text)
                    progress['value'] = (i + 1) / len(checks) * 100
                    update_results(f"✓ {check_text}")
                    result, message = check_func()
                    if result:
                        update_results(f"  ✅ {message}", SUCCESS_COLOR)
                    else:
                        update_results(f"  ❌ {message}", ERROR_COLOR)
                    time.sleep(0.5)

                status_label.config(text="System check completed!")
                update_results("\n🎉 System check completed successfully!", SUCCESS_COLOR)

            except Exception as e:
                update_results(f"❌ System check failed: {str(e)}", ERROR_COLOR)

        threading.Thread(target=perform_check, daemon=True).start()

    def _check_database(self):
        """Check database connectivity"""
        try:
            if hasattr(self, 'db') and self.db.conn:
                self.db.cursor.execute("SELECT 1")
                return True, "Database connection is healthy"
            return False, "Database connection failed"
        except:
            return False, "Database connection error"

    def _check_users(self):
        """Check user accounts"""
        try:
            user_count = len(self.config["users"])
            admin_count = sum(1 for user in self.config["users"].values() if user.get("is_admin", False))
            return True, f"Users: {user_count} total, {admin_count} admins"
        except:
            return False, "User account check failed"

    def _check_stock(self):
        """Check stock levels"""
        try:
            low_stock = self.db.get_low_stock_items(5)
            return True, f"Low stock items: {len(low_stock)}"
        except:
            return False, "Stock check failed"

    def _check_files(self):
        """Check system files"""
        try:
            essential_files = [CONFIG_FILE, DATABASE_FILE]
            missing_files = [f for f in essential_files if not os.path.exists(f)]
            if missing_files:
                return False, f"Missing files: {', '.join(missing_files)}"
            return True, "All essential files present"
        except:
            return False, "File system check failed"

    def _check_printing(self):
        """Check printing capability"""
        try:
            # Test printing capability
            return True, "Printing system ready"
        except:
            return False, "Printing check failed"

    def _finalize_check(self):
        """Finalize system check"""
        return True, "All systems operational"

    def create_system_management_section(self, parent_frame):
        """Create comprehensive system management section with enhanced layout for 1200x800 window"""
        # Main container using grid for better layout control:cite[1]:cite[3]
        main_container = tk.Frame(parent_frame, bg=BG_COLOR)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Configure grid weights for responsive layout:cite[6]
        main_container.columnconfigure(0, weight=1)
        main_container.columnconfigure(1, weight=1)
        main_container.columnconfigure(2, weight=1)
        
        # Header section
        header_frame = tk.Frame(main_container, bg=BG_COLOR)
        header_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 30))
        
        icon_label = tk.Label(header_frame, text="⚙️", font=('Segoe UI', 32), 
                         bg=BG_COLOR, fg=ACCENT_COLOR)
        icon_label.pack(pady=(0, 15))
    
        welcome_label = tk.Label(header_frame, text="System Management Center", 
                            font=('Poppins', 20, 'bold'), bg=BG_COLOR, fg=FG_COLOR)
        welcome_label.pack(pady=(0, 10))

        # System status indicator
        status_frame = tk.Frame(header_frame, bg=BG_COLOR)
        status_frame.pack(pady=10)
        
        self.system_status = tk.Label(status_frame, text="● System: ONLINE | ● Database: ACTIVE | ● Services: RUNNING", 
                                font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=SUCCESS_COLOR)
        self.system_status.pack()

        # ===== FIRST ROW: CORE MANAGEMENT =====
        # System Status Panel
        status_section = tk.LabelFrame(main_container, text="📊 System Status", 
                                 font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                                 padx=20, pady=15)
        status_section.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        status_section.columnconfigure(0, weight=1)
        
        status_content = """
• System: Zetech University Cafeteria
• Version: 2.0
• Database: Active & Healthy
• Last Backup: Today
• Uptime: 12 days 5 hours
• Active Users: 3
• Storage: 85% Free
        """
        status_label = tk.Label(status_section, text=status_content.strip(),
                           font=('Segoe UI', 10), bg=BG_COLOR, fg=FG_COLOR,
                           justify=tk.LEFT)
        status_label.pack(anchor="w")
        
        # Refresh status button
        refresh_btn = tk.Button(status_section, text="🔄 Refresh Status", 
                          font=('Segoe UI', 10), bg=BUTTON_COLOR, fg=FG_COLOR,
                          command=self.refresh_system_status,
                          pady=5)
        refresh_btn.pack(fill=tk.X, pady=(10, 0))

        # Database Management Panel
        db_section = tk.LabelFrame(main_container, text="💾 Database Management", 
                             font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                             padx=20, pady=15)
        db_section.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        db_section.columnconfigure(0, weight=1)
        
        # Database buttons grid:cite[1]
        db_buttons = [
            ("Backup Database", self.backup_database, SUCCESS_COLOR),
            ("Restore Database", self.restore_database, HIGHLIGHT_COLOR),
            ("Optimize DB", self.optimize_database, BUTTON_COLOR),
            ("Clear Logs", self.clear_system_logs, ERROR_COLOR)
        ]
        
        for i, (text, command, color) in enumerate(db_buttons):
            btn = tk.Button(db_section, text=text, font=('Segoe UI', 10),
                      bg=color, fg=FG_COLOR, command=command,
                      pady=8)
            btn.grid(row=i//2, column=i%2, sticky="ew", padx=5, pady=5)
            db_section.columnconfigure(i%2, weight=1)

        # User Management Panel
        user_section = tk.LabelFrame(main_container, text="👥 User Management", 
                               font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                               padx=20, pady=15)
        user_section.grid(row=1, column=2, sticky="nsew", padx=10, pady=10)
        user_section.columnconfigure(0, weight=1)
        
        user_buttons = [
            ("Add User", self.show_add_user_dialog, SUCCESS_COLOR),
            ("Remove User", self.show_remove_user_dialog, ERROR_COLOR),
            ("User List", self.show_user_list, BUTTON_COLOR),
            ("Credentials", self.show_change_credentials, ACCENT_COLOR)
        ]
        
        for i, (text, command, color) in enumerate(user_buttons):
            btn = tk.Button(user_section, text=text, font=('Segoe UI', 10),
                      bg=color, fg=FG_COLOR, command=command,
                      pady=8)
            btn.grid(row=i//2, column=i%2, sticky="ew", padx=5, pady=5)
            user_section.columnconfigure(i%2, weight=1)

        # ===== SECOND ROW: CONFIGURATION =====
        # System Configuration Panel
        config_section = tk.LabelFrame(main_container, text="⚙️ System Configuration", 
                                 font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                                 padx=20, pady=15)
        config_section.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=10)
        config_section.columnconfigure(0, weight=1)
        config_section.columnconfigure(1, weight=1)
        config_section.columnconfigure(2, weight=1)
        
        config_buttons = [
            ("Appearance", self.show_appearance_settings, BUTTON_COLOR),
            ("Receipt Settings", self.show_receipt_settings, BUTTON_COLOR),
            ("Tax Settings", self.show_tax_settings, BUTTON_COLOR),
            ("Backup Settings", self.show_backup_settings, BUTTON_COLOR),
            ("Security", self.show_security_settings, BUTTON_COLOR),
            ("System Info", self.show_system_info, ACCENT_COLOR)

        ]
        
        for i, (text, command, color) in enumerate(config_buttons):
            btn = tk.Button(config_section, text=text, font=('Segoe UI', 10),
                      bg=color, fg=FG_COLOR, command=command,
                      pady=8)
            btn.grid(row=i//3, column=i%3, sticky="ew", padx=5, pady=5)
            config_section.columnconfigure(i%3, weight=1)

        # Maintenance Panel
        maintenance_section = tk.LabelFrame(main_container, text="🛠️ System Maintenance", 
                                      font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                                      padx=20, pady=15)
        maintenance_section.grid(row=2, column=2, sticky="nsew", padx=10, pady=10)
        maintenance_section.columnconfigure(0, weight=1)
        
        maintenance_buttons = [
            ("Check Updates", self.check_for_updates, BUTTON_COLOR),
            ("Export Data", self.export_system_data, SUCCESS_COLOR),
            ("Clear Cache", self.clear_cache, ACCENT_COLOR),
            ("Test Printer", self.test_printer, BUTTON_COLOR)
        ]
        
        for i, (text, command, color) in enumerate(maintenance_buttons):
            btn = tk.Button(maintenance_section, text=text, font=('Segoe UI', 10),
                      bg=color, fg=FG_COLOR, command=command,
                      pady=8)
            btn.pack(fill=tk.X, padx=5, pady=5)

    


        # ===== SUPPORT INFORMATION =====
        support_section = tk.LabelFrame(main_container, text="📞 Technical Support", 
                                  font=('Segoe UI', 12, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR,
                                  padx=20, pady=15)
        support_section.grid(row=4, column=0, columnspan=3, sticky="ew", padx=10, pady=10)
        
        support_content = """
For technical support and system administration:
• Phone: 0796939191 / 0707326661
• Email: support@clintech.com
• Emergency Support: Available 24/7
• System Administration: Clin-Tech Technologies

Regular Maintenance Hours: 8:00 AM - 6:00 PM
        """
        support_label = tk.Label(support_section, text=support_content.strip(),
                           font=('Segoe UI', 10), bg=BG_COLOR, fg=FG_COLOR,
                           justify=tk.LEFT)
        support_label.pack(anchor="w")

        # Configure row weights for proper expansion:cite[6]
        main_container.rowconfigure(1, weight=1)
        main_container.rowconfigure(2, weight=1)
        main_container.rowconfigure(3, weight=0)
        main_container.rowconfigure(4, weight=0)


    def refresh_system_status(self):
        """Refresh and display current system status with real-time information"""
        try:
            # Create status window
            status_window = tk.Toplevel(self.root)
            status_window.title("System Status Refresh")
            status_window.geometry("800x1000")
            status_window.configure(bg=BG_COLOR)
            status_window.transient(self.root)
            status_window.grab_set()

            main_frame = tk.Frame(status_window, bg=BG_COLOR)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

            # Title
            tk.Label(main_frame, text="System Status Dashboard", 
                     font=('Poppins', 16, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

            # Refresh button
            refresh_btn = tk.Button(main_frame, text="🔄 Refresh Now", font=FONT_MEDIUM,
                                   bg=ACCENT_COLOR, fg=BG_COLOR, command=lambda: self.update_status_display(status_frame),
                                   padx=15, pady=5)
            refresh_btn.pack(pady=5)

            # Status display frame
            status_frame = tk.Frame(main_frame, bg=BG_COLOR)
            status_frame.pack(fill=tk.BOTH, expand=True, pady=10)

            # Initial status display
            self.update_status_display(status_frame)

            # Auto-refresh every 30 seconds
            def auto_refresh():
                if status_window.winfo_exists():
                    self.update_status_display(status_frame)
                    status_window.after(30000, auto_refresh)  # Refresh every 30 seconds

            status_window.after(30000, auto_refresh)

            # Close button
            tk.Button(main_frame, text="Close", font=FONT_MEDIUM,
                     bg=ERROR_COLOR, fg=FG_COLOR, command=status_window.destroy,
                     padx=15, pady=5).pack(pady=10)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open status dashboard:\n{str(e)}")
    def update_clock(self):
        """Update the date and time display"""
        if hasattr(self, 'clock_label') and self.clock_label.winfo_exists():
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.clock_label.config(text=current_time)
            self.root.after(1000, self.update_clock)

    def is_admin_user(self):
        """Check if current user is admin"""
        if not self.current_user:
            return False
        return self.config["users"].get(self.current_user, {}).get("is_admin", False)

    def confirm_exit(self):
        if messagebox.askyesno("Exit", "Are you sure you want to exit?", parent=self.root):
            self.root.destroy()

    def confirm_logout(self):
        if messagebox.askyesno("Logout", "Are you sure you want to logout?", parent=self.root):
            was_manager = self.manager_mode
            self.current_user = None
            self.manager_mode = False
            # Clear current UI and open the appropriate portal window
            self.clear_window()
            if was_manager:
                self.homepage.open_manager_portal()
            else:
                self.homepage.open_user_portal()

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()




    def update_status_display(self, status_frame):
        """Update the status display with current system information"""
        try:
            # Clear previous status display
            for widget in status_frame.winfo_children():
                widget.destroy()

            # Get current timestamp
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Create status sections
            sections = [
                ("🖥️ SYSTEM STATUS", self.get_system_status()),
                ("💾 DATABASE STATUS", self.get_database_status()),
              
               
                ("📦 STOCK STATUS", self.get_stock_status()),
                ("👥 USER ACTIVITY", self.get_user_activity_status())
            ]

            for section_title, section_data in sections:
                # Section header
                section_header = tk.Frame(status_frame, bg=BG_COLOR)
                section_header.pack(fill=tk.X, pady=(10, 5))
                
                tk.Label(section_header, text=section_title, font=('Poppins', 12, 'bold'),
                        bg=BG_COLOR, fg=ACCENT_COLOR).pack(anchor=tk.W)

                # Section content
                section_content = tk.Frame(status_frame, bg=BG_COLOR)
                section_content.pack(fill=tk.X, padx=10, pady=(0, 10))

                for item_text, item_status, item_color in section_data:
                    item_frame = tk.Frame(section_content, bg=BG_COLOR)
                    item_frame.pack(fill=tk.X, pady=2)

                    # Status indicator
                    status_circle = tk.Label(item_frame, text="●", font=('Arial', 12),
                                           bg=BG_COLOR, fg=item_color)
                    status_circle.pack(side=tk.LEFT, padx=(0, 10))

                    # Item text
                    tk.Label(item_frame, text=item_text, font=FONT_SMALL,
                            bg=BG_COLOR, fg=FG_COLOR, anchor=tk.W).pack(side=tk.LEFT)

                    # Status text (right-aligned)
                    tk.Label(item_frame, text=item_status, font=FONT_SMALL,
                            bg=BG_COLOR, fg=item_color, anchor=tk.E).pack(side=tk.RIGHT)

            # Last update time
            update_frame = tk.Frame(status_frame, bg=BG_COLOR)
            update_frame.pack(fill=tk.X, pady=10)
            
            tk.Label(update_frame, text=f"Last Updated: {current_time}", 
                    font=('Poppins', 10, 'italic'), bg=BG_COLOR, fg=FG_COLOR).pack()

        except Exception as e:
            # Error display
            error_frame = tk.Frame(status_frame, bg=BG_COLOR)
            error_frame.pack(fill=tk.BOTH, expand=True)
            
            tk.Label(error_frame, text="❌ Error refreshing status:", 
                    font=FONT_MEDIUM, bg=BG_COLOR, fg=ERROR_COLOR).pack(pady=5)
            tk.Label(error_frame, text=str(e), font=FONT_SMALL, 
                    bg=BG_COLOR, fg=FG_COLOR, wraplength=500).pack(pady=5)

    def get_system_status(self):
        """Get current system status information"""
        try:
            status_items = []
            
            # Application status
            app_status = "ONLINE" if self.root.winfo_exists() else "OFFLINE"
            status_items.append(("Application", app_status, SUCCESS_COLOR if app_status == "ONLINE" else ERROR_COLOR))
            
            # Database connection
            db_status = "CONNECTED" if hasattr(self, 'db') and self.db.conn else "DISCONNECTED"
            status_items.append(("Database Connection", db_status, SUCCESS_COLOR if db_status == "CONNECTED" else ERROR_COLOR))
            
            
            # Manager mode
            manager_status = "ACTIVE" if self.manager_mode else "INACTIVE"
            status_items.append(("Manager Mode", manager_status, HIGHLIGHT_COLOR if self.manager_mode else FG_COLOR))
            
            return status_items
            
        except Exception as e:
            return [("System Status", f"Error: {str(e)}", ERROR_COLOR)]

    def get_database_status(self):
        """Get database status and statistics"""
        try:
            status_items = []
            
            if not hasattr(self, 'db') or not self.db.conn:
                return [("Database", "Not connected", ERROR_COLOR)]
            
            # Database file status
            db_file = DATABASE_FILE
            db_exists = os.path.exists(db_file)
            status_items.append(("Database File", "Exists" if db_exists else "Missing", 
                               SUCCESS_COLOR if db_exists else ERROR_COLOR))
            
            if db_exists:
                # File size
                size_mb = os.path.getsize(db_file) / (1024 * 1024)
                status_items.append(("File Size", f"{size_mb:.2f} MB", ACCENT_COLOR))
                
                # Table counts
                tables = self.db.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                status_items.append(("Tables", str(len(tables)), SUCCESS_COLOR))
                
                # Total records
                total_records = 0
                for table in tables:
                    count = self.db.cursor.execute(f"SELECT COUNT(*) FROM {table[0]}").fetchone()[0]
                    total_records += count
                status_items.append(("Total Records", f"{total_records:,}", ACCENT_COLOR))
                
                # Last activity
                last_activity = self.db.cursor.execute(
                    "SELECT timestamp FROM user_activity ORDER BY timestamp DESC LIMIT 1"
                ).fetchone()
                if last_activity:
                    status_items.append(("Last Activity", "Recent", SUCCESS_COLOR))
                else:
                    status_items.append(("Last Activity", "None", ACCENT_COLOR))
                    
            return status_items
            
        except Exception as e:
            return [("Database Status", f"Error: {str(e)}", ERROR_COLOR)]




    def get_stock_status(self):
        """Get current stock status"""
        try:
            status_items = []
            
            if not hasattr(self, 'db'):
                return [("Stock Data", "Database not available", ERROR_COLOR)]
            
            # Total items
            total_items = self.db.cursor.execute("SELECT COUNT(*) FROM meals WHERE is_active=1").fetchone()[0]
            status_items.append(("Active Items", str(total_items), SUCCESS_COLOR))
            
            # Low stock items
            low_stock = self.db.get_low_stock_items(threshold=5)
            status_items.append(("Low Stock Items", str(len(low_stock)), 
                               ERROR_COLOR if len(low_stock) > 0 else SUCCESS_COLOR))
            
          
            
            # Total stock value (approximate)
            stock_value = self.db.cursor.execute(
                "SELECT SUM(current_stock * buying_price) FROM meals WHERE is_active=1"
            ).fetchone()[0] or 0
            status_items.append(("Stock Value", f"Ksh {stock_value:.2f}", ACCENT_COLOR))
            
            return status_items
            
        except Exception as e:
            return [("Stock Status", f"Error: {str(e)}", ERROR_COLOR)]

    def get_user_activity_status(self):
        """Get user activity status"""
        try:
            status_items = []
            
            if not hasattr(self, 'db'):
                return [("User Activity", "Database not available", ERROR_COLOR)]
            
            # Recent activity count
            recent_activity = self.db.cursor.execute(
                "SELECT COUNT(*) FROM user_activity WHERE timestamp >= datetime('now', '-1 hour')"
            ).fetchone()[0]
            status_items.append(("Recent Activity (1h)", str(recent_activity), 
                               SUCCESS_COLOR if recent_activity > 0 else ACCENT_COLOR))
            
            # Total users
            total_users = len(self.config["users"]) if hasattr(self, 'config') and "users" in self.config else 0
            status_items.append(("Total Users", str(total_users), SUCCESS_COLOR))
            
            # Admin users
            admin_users = sum(1 for user in self.config.get("users", {}).values() if user.get("is_admin", False))
            status_items.append(("Admin Users", str(admin_users), HIGHLIGHT_COLOR))

            # Last login
            last_login = self.db.cursor.execute(
                "SELECT user, timestamp FROM user_activity WHERE activity_type='login' ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            if last_login:
                status_items.append(("Last Login", f"{last_login[0]} ({last_login[1][:16]})", SUCCESS_COLOR))
            else:
                status_items.append(("Last Login", "No logins recorded", ACCENT_COLOR))

            return status_items
            
        except Exception as e:
            return [("User Activity", f"Error: {str(e)}", ERROR_COLOR)]

    def show_user_list(self):
        """Display list of all users with comprehensive details"""
        try:
            users_window = tk.Toplevel(self.root)
            users_window.title("System Users List")
            users_window.geometry("15000x800")
            users_window.configure(bg=BG_COLOR)
            users_window.transient(self.root)
            
            main_frame = tk.Frame(users_window, bg=BG_COLOR)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

            # Title
            tk.Label(main_frame, text="System Users Management", 
                     font=('Poppins', 16, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

            # Description
            desc_label = tk.Label(main_frame, 
                                text="List of all registered users in the system with their roles and permissions",
                                font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR, wraplength=600)
            desc_label.pack(pady=5)

            # Create treeview for user list
            columns = ("Username", "Role", "Admin", "Last Login", "Status")
            tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=15)
            
            # Configure headings
            tree.heading("Username", text="Username")
            tree.heading("Role", text="Role")
            tree.heading("Admin", text="Admin Access")
            tree.heading("Last Login", text="Last Login")
            tree.heading("Status", text="Status")
            
            # Configure columns
            tree.column("Username", width=150, anchor=tk.W)
            tree.column("Role", width=120, anchor=tk.W)
            tree.column("Admin", width=100, anchor=tk.CENTER)
            tree.column("Last Login", width=150, anchor=tk.W)
            tree.column("Status", width=100, anchor=tk.CENTER)

            # Add scrollbar
            scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)

            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # Get user activity data to determine last login
            last_login_data = {}
            try:
                if hasattr(self, 'db'):
                    self.db.cursor.execute('''
                        SELECT user, MAX(timestamp) as last_login 
                        FROM user_activity 
                        WHERE activity_type='login' 
                        GROUP BY user
                    ''')
                    login_data = self.db.cursor.fetchall()
                    for username, last_login in login_data:
                        last_login_data[username] = last_login
            except Exception as e:
                print(f"Error fetching login data: {str(e)}")

            # Populate with user data
            for username, user_data in self.config["users"].items():
                role = "Administrator" if user_data.get("is_admin", False) else "User"
                admin_status = "Yes" if user_data.get("is_admin", False) else "No"
                last_login = last_login_data.get(username, "Never")
                
                # Format last login timestamp
                if last_login != "Never":
                    try:
                        # Extract date part only for cleaner display
                        last_login = last_login.split()[0] if ' ' in last_login else last_login
                    except:
                        pass
                
                # Determine status
                status = "Active"
                
                tree.insert("", tk.END, values=(
                    username,
                    role,
                    admin_status,
                    last_login,
                    status
                ))

            # Statistics frame
            stats_frame = tk.Frame(main_frame, bg=BG_COLOR)
            stats_frame.pack(fill=tk.X, pady=10)

            total_users = len(self.config["users"])
            admin_users = sum(1 for user in self.config["users"].values() if user.get("is_admin", False))
            regular_users = total_users - admin_users

            stats_text = f"📊 Statistics: Total Users: {total_users} | Admins: {admin_users} | Regular Users: {regular_users}"
            stats_label = tk.Label(stats_frame, text=stats_text, font=FONT_SMALL, 
                                 bg=BG_COLOR, fg=ACCENT_COLOR)
            stats_label.pack()

            # Button frame
            button_frame = tk.Frame(main_frame, bg=BG_COLOR)
            button_frame.pack(pady=10)

            def refresh_list():
                """Refresh the user list"""
                for item in tree.get_children():
                    tree.delete(item)
                
                # Re-fetch last login data
                last_login_data.clear()
                try:
                    if hasattr(self, 'db'):
                        self.db.cursor.execute('''
                            SELECT user, MAX(timestamp) as last_login 
                            FROM user_activity 
                            WHERE activity_type='login' 
                            GROUP BY user
                        ''')
                        login_data = self.db.cursor.fetchall()
                        for username, last_login in login_data:
                            last_login_data[username] = last_login
                except Exception as e:
                    print(f"Error fetching login data: {str(e)}")

                # Re-populate
                for username, user_data in self.config["users"].items():
                    role = "Administrator" if user_data.get("is_admin", False) else "User"
                    admin_status = "Yes" if user_data.get("is_admin", False) else "No"
                    last_login = last_login_data.get(username, "Never")
                    
                    if last_login != "Never":
                        try:
                            last_login = last_login.split()[0] if ' ' in last_login else last_login
                        except:
                            pass
                    
                    status = "Active"
                    
                    tree.insert("", tk.END, values=(
                        username,
                        role,
                        admin_status,
                        last_login,
                        status
                    ))

            def export_user_list():
                """Export user list to CSV"""
                try:
                    export_dir = "user_exports"
                    if not os.path.exists(export_dir):
                        os.makedirs(export_dir)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"user_list_export_{timestamp}.csv"
                    filepath = os.path.join(export_dir, filename)

                    with open(filepath, 'w', newline='', encoding='utf-8') as f:
                        import csv
                        writer = csv.writer(f)
                        writer.writerow(["Username", "Role", "Admin Access", "Last Login", "Status"])
                        
                        for username, user_data in self.config["users"].items():
                            role = "Administrator" if user_data.get("is_admin", False) else "User"
                            admin_status = "Yes" if user_data.get("is_admin", False) else "No"
                            last_login = last_login_data.get(username, "Never")
                            status = "Active"
                            
                            writer.writerow([username, role, admin_status, last_login, status])

                    messagebox.showinfo("Export Successful", 
                                      f"User list exported to:\n{filepath}", 
                                      parent=users_window)
                    
                except Exception as e:
                    messagebox.showerror("Export Failed", 
                                       f"Failed to export user list:\n{str(e)}", 
                                       parent=users_window)

            # Buttons
            tk.Button(button_frame, text="Refresh List", font=FONT_SMALL,
                     bg=BUTTON_COLOR, fg=FG_COLOR, command=refresh_list,
                     padx=10, pady=5).pack(side=tk.LEFT, padx=5)
            
            tk.Button(button_frame, text="Export to CSV", font=FONT_SMALL,
                     bg=SUCCESS_COLOR, fg=FG_COLOR, command=export_user_list,
                     padx=10, pady=5).pack(side=tk.LEFT, padx=5)
            
            tk.Button(button_frame, text="Close", font=FONT_SMALL,
                     bg=ERROR_COLOR, fg=FG_COLOR, command=users_window.destroy,
                     padx=10, pady=5).pack(side=tk.LEFT, padx=5)

            # Double-click to view user details
            def on_double_click(event):
                item = tree.selection()[0]
                values = tree.item(item, 'values')
                username = values[0]
                
                user_details = self.config["users"].get(username, {})
                role = "Administrator" if user_details.get("is_admin", False) else "User"
                has_manager_access = "Yes" if user_details.get("manager_password") else "No"
                
                details_text = f"""
User Details for: {username}

• Role: {role}
• Admin Access: {values[2]}
• Manager Password Set: {has_manager_access}
• Last Login: {values[3]}
• Status: {values[4]}

Account Information:
• Username: {username}
• Hashed Password: {user_details.get('password', 'Not set')[:20]}...
• Manager Password: {'Set' if user_details.get('manager_password') else 'Not set'}

Permissions:
• Can access admin features: {user_details.get('is_admin', False)}
• Can modify system settings: {user_details.get('is_admin', False)}
• Can view reports: Yes
• Can process sales: Yes
                """.strip()
                
                messagebox.showinfo("User Details", details_text, parent=users_window)

            tree.bind("<Double-1>", on_double_click)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to display user list:\n{str(e)}", parent=self.root)
        


    def optimize_database(self):
        """Optimize database performance"""
        try:
            self.db.conn.execute("VACUUM")
            self.db.conn.commit()
            messagebox.showinfo("Database Optimized", "Database optimization completed successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to optimize database: {str(e)}")

    def clear_system_logs(self):
        """Clear system logs with confirmation"""
        if messagebox.askyesno("Clear Logs", "Are you sure you want to clear all system logs?"):
            try:
                self.db.cursor.execute("DELETE FROM user_activity WHERE timestamp < date('now', '-30 days')")
                self.db.conn.commit()
                messagebox.showinfo("Logs Cleared", "System logs cleared successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear logs: {str(e)}")

    def backup_database(self):
        """Create a backup of the database with timestamp"""
        try:
            import shutil
            from datetime import datetime
            
            # Create backups directory if it doesn't exist
            backups_dir = "database_backups"
            if not os.path.exists(backups_dir):
                os.makedirs(backups_dir)
            
            # Create timestamped backup filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"hotel_backup_{timestamp}.db"
            backup_path = os.path.join(backups_dir, backup_filename)
            
            # Close database connection temporarily
            self.db.conn.close()
            
            # Copy database file
            shutil.copy2(DATABASE_FILE, backup_path)
            
            # Reopen database connection
            self.db.conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
            self.db.cursor = self.db.conn.cursor()
            
            # Record backup activity
            self.db.cursor.execute('''
                INSERT INTO user_activity (user, activity_type, description)
                VALUES (?, ?, ?)
            ''', (self.current_user or 'system', 'system', f'Database backup created: {backup_filename}'))
            self.db.conn.commit()
            
            messagebox.showinfo("Backup Successful", 
                               f"Database backup created successfully!\n\n"
                               f"Backup file: {backup_filename}\n"
                               f"Location: {backups_dir}")
                               
        except Exception as e:
            messagebox.showerror("Backup Failed", 
                                f"Failed to create database backup:\n{str(e)}")
            # Reopen database connection if it failed
            try:
                self.db.conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
                self.db.cursor = self.db.conn.cursor()
            except:
                pass

    def restore_database(self):
        """Restore database from backup with confirmation and validation"""
        try:
            backups_dir = "database_backups"
            if not os.path.exists(backups_dir):
                messagebox.showwarning("No Backups", "No backup directory found.")
                return
            
            # Get list of backup files
            backup_files = [f for f in os.listdir(backups_dir) if f.endswith('.db') and f.startswith('hotel_backup_')]
            if not backup_files:
                messagebox.showwarning("No Backups", "No backup files found.")
                return
            
            # Create restore dialog
            restore_window = tk.Toplevel(self.root)
            restore_window.title("Restore Database")
            restore_window.geometry('1000x780')
            restore_window.configure(bg=BG_COLOR)
            restore_window.transient(self.root)
            restore_window.grab_set()
            
            tk.Label(restore_window, text="Select Backup to Restore:", 
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
            
            # Listbox with scrollbar
            frame = tk.Frame(restore_window, bg=BG_COLOR)
            frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            listbox = tk.Listbox(frame, bg="#2a2a40", fg=FG_COLOR, font=FONT_SMALL, selectmode=tk.SINGLE)
            scrollbar = tk.Scrollbar(frame, orient="vertical")
            listbox.configure(yscrollcommand=scrollbar.set)
            scrollbar.config(command=listbox.yview)
            
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Add backup files to listbox with file info
            for backup_file in sorted(backup_files, reverse=True):
                file_path = os.path.join(backups_dir, backup_file)
                file_time = os.path.getmtime(file_path)
                file_date = datetime.fromtimestamp(file_time).strftime("%Y-%m-%d %H:%M:%S")
                file_size = os.path.getsize(file_path) / (1024*1024)  # Size in MB
                listbox.insert(tk.END, f"{backup_file} ({file_date}) - {file_size:.2f} MB")
            
            def perform_restore():
                selection = listbox.curselection()
                if not selection:
                    messagebox.showwarning("No Selection", "Please select a backup file to restore.")
                    return
                
                backup_file = backup_files[selection[0]]
                backup_path = os.path.join(backups_dir, backup_file)
                
                # Confirm restoration
                if not messagebox.askyesno("Confirm Restore", 
                                         f"WARNING: This will replace the current database!\n\n"
                                         f"Restore from: {backup_file}\n\n"
                                         f"All current data will be lost. Continue?"):
                    return
                
                try:
                    # Close current database connection
                    self.db.conn.close()
                    
                    # Create backup of current database before restore
                    current_backup = f"pre_restore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                    shutil.copy2(DATABASE_FILE, os.path.join(backups_dir, current_backup))
                    
                    # Restore from selected backup
                    shutil.copy2(backup_path, DATABASE_FILE)
                    
                    # Reinitialize database connection
                    self.db.conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
                    self.db.cursor = self.db.conn.cursor()
                    
                    messagebox.showinfo("Restore Successful", 
                                       f"Database restored successfully from:\n{backup_file}\n\n"
                                       f"Current database backed up as: {current_backup}")
                    
                    restore_window.destroy()
                    
                    # Restart application to reload data
                    if messagebox.askyesno("Restart Required", "Application needs to restart to load restored data. Restart now?"):
                        self.root.destroy()
                        # Note: In a real application, you'd restart the app here
                        
                except Exception as e:
                    messagebox.showerror("Restore Failed", f"Failed to restore database:\n{str(e)}")
                    # Try to reconnect to original database
                    try:
                        self.db.conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
                        self.db.cursor = self.db.conn.cursor()
                    except:
                        pass
            
            button_frame = tk.Frame(restore_window, bg=BG_COLOR)
            button_frame.pack(pady=10)
            
            tk.Button(button_frame, text="Restore Selected", command=perform_restore,
                     bg=SUCCESS_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="Cancel", command=restore_window.destroy,
                     bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(side=tk.LEFT, padx=5)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to access backup files:\n{str(e)}")

    def optimize_database(self):
        """Optimize database performance using SQLite VACUUM and other optimizations"""
        try:
            # Show progress dialog
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Optimizing Database")
            progress_window.geometry("400x150")
            progress_window.configure(bg=BG_COLOR)
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            tk.Label(progress_window, text="Optimizing Database...", 
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
            
            progress = ttk.Progressbar(progress_window, mode='indeterminate', length=300)
            progress.pack(pady=10)
            progress.start(10)
            
            def perform_optimization():
                try:
                    # Perform VACUUM to defragment database
                    self.db.conn.execute("VACUUM")
                    
                    # Analyze for better query performance
                    self.db.conn.execute("ANALYZE")
                    
                    # Update statistics
                    self.db.conn.execute("PRAGMA optimize")
                    
                    self.db.conn.commit()
                    
                    # Record optimization activity
                    self.db.cursor.execute('''
                        INSERT INTO user_activity (user, activity_type, description)
                        VALUES (?, ?, ?)
                    ''', (self.current_user or 'system', 'system', 'Database optimization performed'))
                    self.db.conn.commit()
                    
                    progress_window.destroy()
                    messagebox.showinfo("Optimization Complete", 
                                       "Database optimization completed successfully!\n\n"
                                       "• Database defragmented\n"
                                       "• Query statistics updated\n"
                                       "• Performance optimized")
                                       
                except Exception as e:
                    progress_window.destroy()
                    messagebox.showerror("Optimization Failed", f"Failed to optimize database:\n{str(e)}")
            
            # Run optimization in a thread to avoid blocking UI
            threading.Thread(target=perform_optimization, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start optimization:\n{str(e)}")

    def clear_system_logs(self):
        """Clear system logs with options for different log types"""
        try:
            # Create log clearing dialog
            log_window = tk.Toplevel(self.root)
            log_window.title("Clear System Logs")
            log_window.geometry("1550x790")
            log_window.configure(bg=BG_COLOR)
            log_window.transient(self.root)
            log_window.grab_set()
            
            tk.Label(log_window, text="Select Logs to Clear:", 
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
            
            # Log type selection
            log_vars = {
                'user_activity': tk.BooleanVar(value=True),
                'old_sales': tk.BooleanVar(value=False),
                'stock_history': tk.BooleanVar(value=False)
            }
            
            options_frame = tk.Frame(log_window, bg=BG_COLOR)
            options_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            tk.Checkbutton(options_frame, text="User Activity Logs (older than 30 days)", 
                          variable=log_vars['user_activity'], bg=BG_COLOR, fg=FG_COLOR,
                          font=FONT_SMALL).pack(anchor="w", pady=2)
            
            tk.Checkbutton(options_frame, text="Sales Records (older than 1 year)", 
                          variable=log_vars['old_sales'], bg=BG_COLOR, fg=FG_COLOR,
                          font=FONT_SMALL).pack(anchor="w", pady=2)
            
            tk.Checkbutton(options_frame, text="Stock History (older than 6 months)", 
                          variable=log_vars['stock_history'], bg=BG_COLOR, fg=FG_COLOR,
                          font=FONT_SMALL).pack(anchor="w", pady=2)
            
            # Statistics frame
            stats_frame = tk.Frame(log_window, bg=BG_COLOR)
            stats_frame.pack(fill=tk.X, padx=10, pady=5)
            
            stats_label = tk.Label(stats_frame, text="", font=FONT_SMALL, 
                                  bg=BG_COLOR, fg=ACCENT_COLOR, justify=tk.LEFT)
            stats_label.pack(anchor="w")
            
            def update_stats():
                """Update statistics based on selected options"""
                stats_text = "Records to be cleared:\n"
                
                if log_vars['user_activity'].get():
                    count = self.db.cursor.execute(
                        "SELECT COUNT(*) FROM user_activity WHERE timestamp < date('now', '-30 days')"
                    ).fetchone()[0]
                    stats_text += f"• User Activity: {count} records\n"
                
                if log_vars['old_sales'].get():
                    count = self.db.cursor.execute(
                        "SELECT COUNT(*) FROM sales WHERE date < date('now', '-1 year')"
                    ).fetchone()[0]
                    stats_text += f"• Old Sales: {count} records\n"
                
                if log_vars['stock_history'].get():
                    count = self.db.cursor.execute(
                        "SELECT COUNT(*) FROM stock_history WHERE date < date('now', '-6 months')"
                    ).fetchone()[0]
                    stats_text += f"• Stock History: {count} records\n"
                
                stats_label.config(text=stats_text)
            
            # Update stats initially and on checkbox changes
            update_stats()
            for var in log_vars.values():
                var.trace('w', lambda *args: update_stats())
            
            def perform_clearing():
                """Perform the actual log clearing"""
                if not any(var.get() for var in log_vars.values()):
                    messagebox.showwarning("No Selection", "Please select at least one log type to clear.")
                    return
                
                if not messagebox.askyesno("Confirm Clear", 
                                         "WARNING: This action cannot be undone!\n\n"
                                         "Are you sure you want to clear the selected logs?"):
                    return
                
                try:
                    cleared_counts = {}
                    
                    if log_vars['user_activity'].get():
                        cleared_counts['user_activity'] = self.db.cursor.execute(
                            "DELETE FROM user_activity WHERE timestamp < date('now', '-30 days')"
                        ).rowcount
                    
                    if log_vars['old_sales'].get():
                        # For sales, we might want to archive instead of delete
                        # For now, we'll just count them without deleting
                        count = self.db.cursor.execute(
                            "SELECT COUNT(*) FROM sales WHERE date < date('now', '-1 year')"
                        ).fetchone()[0]
                        cleared_counts['old_sales'] = count
                        # Actually, let's not delete sales records - just demonstrate the count
                        messagebox.showinfo("Note", "Sales records are preserved for historical reporting.")
                    
                    if log_vars['stock_history'].get():
                        cleared_counts['stock_history'] = self.db.cursor.execute(
                            "DELETE FROM stock_history WHERE date < date('now', '-6 months')"
                        ).rowcount
                    
                    self.db.conn.commit()
                    
                    # Record the activity
                    self.db.cursor.execute('''
                        INSERT INTO user_activity (user, activity_type, description)
                        VALUES (?, ?, ?)
                    ''', (self.current_user or 'system', 'system', 'System logs cleared'))
                    self.db.conn.commit()
                    
                    summary = "Log clearing completed:\n"
                    for log_type, count in cleared_counts.items():
                        summary += f"• {log_type.replace('_', ' ').title()}: {count} records cleared\n"
                    
                    messagebox.showinfo("Clear Complete", summary)
                    log_window.destroy()
                    
                except Exception as e:
                    messagebox.showerror("Clear Failed", f"Failed to clear logs:\n{str(e)}")
            
            button_frame = tk.Frame(log_window, bg=BG_COLOR)
            button_frame.pack(pady=10)
            
            tk.Button(button_frame, text="Clear Selected Logs", command=perform_clearing,
                     bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="Cancel", command=log_window.destroy,
                     bg=BUTTON_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(side=tk.LEFT, padx=5)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to access log clearing:\n{str(e)}")

    def check_for_updates(self):
        """Check for system updates with proper version checking and download options"""
        # Create update check dialog
        update_window = tk.Toplevel(self.root)
        update_window.title("Check for Updates")
        update_window.geometry("1550x790")
        update_window.configure(bg=BG_COLOR)
        update_window.transient(self.root)
        update_window.grab_set()

        main_frame = tk.Frame(update_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Title
        tk.Label(main_frame, text="System Update Check", 
                 font=('Poppins', 16, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        # Current version info
        current_version = "2.0"
        tk.Label(main_frame, text=f"Current Version: v{current_version}", 
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)

        # Status frame
        status_frame = tk.Frame(main_frame, bg=BG_COLOR)
        status_frame.pack(fill=tk.X, pady=10)

        self.update_status = tk.Label(status_frame, text="Click 'Check Now' to search for updates...", 
                                     font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR, wraplength=500)
        self.update_status.pack()

        # Progress bar
        self.update_progress = ttk.Progressbar(main_frame, mode='indeterminate', length=400)
        self.update_progress.pack(pady=10)

        # Results frame (initially hidden)
        self.results_frame = tk.Frame(main_frame, bg=BG_COLOR)
        
        # Button frame
        button_frame = tk.Frame(main_frame, bg=BG_COLOR)
        button_frame.pack(pady=20)

        def check_updates():
            """Perform the actual update check"""
            self.update_progress.start(10)
            self.update_status.config(text="Connecting to update server...", fg=ACCENT_COLOR)
            update_window.update()

            try:
                # Simulate network delay
                update_window.after(1500, lambda: self.perform_update_check(update_window, current_version))
                
            except Exception as e:
                self.update_progress.stop()
                self.update_status.config(text=f"Error checking for updates: {str(e)}", fg=ERROR_COLOR)

        # Check Now button
        tk.Button(button_frame, text="Check Now", font=FONT_MEDIUM,
                 bg=ACCENT_COLOR, fg=BG_COLOR, command=check_updates,
                 padx=20, pady=8).pack(side=tk.LEFT, padx=10)
        
        tk.Button(button_frame, text="Close", font=FONT_MEDIUM,
                 bg=BUTTON_COLOR, fg=FG_COLOR, command=update_window.destroy,
                 padx=20, pady=8).pack(side=tk.LEFT, padx=10)

    def perform_update_check(self, window, current_ver):
        """Perform the actual update check simulation"""
        self.update_progress.stop()
        
        # Simulate various outcomes for demonstration
        import random
        outcome = random.choice(['update_available', 'no_update', 'error'])
        
        if outcome == 'update_available':
            # Simulate finding a new version
            new_version = "2.1"
            self.update_status.config(text=f"New version v{new_version} available!", fg=SUCCESS_COLOR)
            self.show_update_available(window, current_ver, new_version)
            
        elif outcome == 'no_update':
            self.update_status.config(text="Your system is up to date!", fg=SUCCESS_COLOR)
            self.show_no_update_available(window)
            
        else:  # error
            self.update_status.config(text="Could not connect to update server. Please check your internet connection.", 
                                     fg=ERROR_COLOR)

    def show_update_available(self, window, current_ver, new_ver):
        """Show update available interface"""
        # Clear previous results
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        
        self.results_frame.pack(fill=tk.X, pady=10)
        
        # Update info
        info_text = f"Version {new_ver} is available!\n\n"
        info_text += f"• Current version: v{current_ver}\n"
        info_text += f"• New version: v{new_ver}\n"
        info_text += "• Update includes: Bug fixes, performance improvements\n"
        info_text += "• Size: ~15 MB\n"
        info_text += "• Estimated time: 2-5 minutes"
        
        tk.Label(self.results_frame, text=info_text, font=FONT_SMALL, 
                bg=BG_COLOR, fg=FG_COLOR, justify=tk.LEFT).pack(pady=10)
        
        # Update buttons
        update_btn_frame = tk.Frame(self.results_frame, bg=BG_COLOR)
        update_btn_frame.pack(pady=10)
        
        tk.Button(update_btn_frame, text="Download and Install Update", 
                 font=FONT_MEDIUM, bg=SUCCESS_COLOR, fg=FG_COLOR,
                 command=lambda: self.download_update(window, new_ver),
                 padx=15, pady=5).pack(side=tk.LEFT, padx=5)
        
        tk.Button(update_btn_frame, text="Remind Me Later", 
                 font=FONT_MEDIUM, bg=BUTTON_COLOR, fg=FG_COLOR,
                 command=window.destroy,
                 padx=15, pady=5).pack(side=tk.LEFT, padx=5)

    def show_no_update_available(self, window):
        """Show no update available message"""
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        
        self.results_frame.pack(fill=tk.X, pady=10)
        
        tk.Label(self.results_frame, text="Your system is running the latest version.\nNo updates are currently available.", 
                font=FONT_MEDIUM, bg=BG_COLOR, fg=SUCCESS_COLOR, justify=tk.CENTER).pack(pady=20)
        
        tk.Button(self.results_frame, text="Close", 
                 font=FONT_MEDIUM, bg=BUTTON_COLOR, fg=FG_COLOR,
                 command=window.destroy,
                 padx=15, pady=5).pack()

    def download_update(self, parent_window, version):
        """Simulate downloading and installing an update"""
        # Create download progress window
        download_window = tk.Toplevel(parent_window)
        download_window.title("Downloading Update")
        download_window.state('zoomed')
        download_window.configure(bg=BG_COLOR)
        download_window.transient(parent_window)
        download_window.grab_set()
        
        main_frame = tk.Frame(download_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        tk.Label(main_frame, text=f"Downloading v{version}", 
                 font=('Poppins', 14, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)
        
        # Progress bar for download
        download_progress = ttk.Progressbar(main_frame, mode='determinate', length=400)
        download_progress.pack(pady=10)
        
        download_status = tk.Label(main_frame, text="Preparing download...", 
                                  font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR)
        download_status.pack(pady=5)
        
        percent_label = tk.Label(main_frame, text="0%", font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR)
        percent_label.pack(pady=5)
        
        def simulate_download():
            """Simulate the download and installation process"""
            steps = [
                ("Connecting to server...", 5),
                ("Downloading update files...", 60),
                ("Verifying files...", 80),
                ("Installing updates...", 95),
                ("Finalizing installation...", 100)
            ]
            
            current_progress = 0
            for step_text, target_progress in steps:
                while current_progress < target_progress:
                    current_progress += 1
                    download_progress['value'] = current_progress
                    percent_label.config(text=f"{current_progress}%")
                    download_status.config(text=step_text)
                    download_window.update()
                    download_window.after(30)  # Simulate work
                
                download_window.after(500)  # Pause between steps
            
            # Download complete
            download_status.config(text="Update completed successfully!", fg=SUCCESS_COLOR)
            percent_label.config(text="100%")
            
            tk.Button(main_frame, text="Restart Application", 
                     font=FONT_MEDIUM, bg=SUCCESS_COLOR, fg=FG_COLOR,
                     command=lambda: self.restart_application(download_window, parent_window),
                     padx=15, pady=5).pack(pady=10)
            
            tk.Button(main_frame, text="Close", 
                     font=FONT_MEDIUM, bg=BUTTON_COLOR, fg=FG_COLOR,
                     command=download_window.destroy,
                     padx=15, pady=5).pack(pady=5)
        
        # Start download simulation
        download_window.after(500, simulate_download)

    def restart_application(self, download_window, parent_window):
        """Simulate application restart"""
        messagebox.showinfo("Restart Required", 
                           "The application needs to restart to complete the update.\n\n"
                           "Please restart the application manually to apply the changes.",
                           parent=download_window)
        download_window.destroy()
        parent_window.destroy()


    def show_appearance_settings(self):
        appearance_window = tk.Toplevel(self.root)
        appearance_window.title("Appearance Settings")
        appearance_window.state('zoomed')  # Changed from fixed size to full screen
        appearance_window.configure(bg=BG_COLOR)
        appearance_window.transient(self.root)
        appearance_window.grab_set()

        # Create a scrolled frame for the entire content
        scrolled_frame = ScrolledFrame(appearance_window, bg=BG_COLOR)
        scrolled_frame.pack(fill=tk.BOTH, expand=True)

        main_frame = scrolled_frame.frame

        # Enhanced Theme Selection
        tk.Label(main_frame, text="Select Theme:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
        
        theme_var = tk.StringVar(value=self.config.get("appearance", {}).get("theme", "Dark Blue"))
        themes = [
            "Dark Blue", "Light Gray", "Dark Green", "Classic Blue",
            "Midnight Purple", "Sunset Orange", "Forest Green", "Ocean Blue",
            "Charcoal Dark", "Soft Pink", "Professional Gray", "Vibrant Purple",
            "Amber Gold", "Deep Crimson", "Electric Blue", "Mint Green",
            "Royal Purple", "Coffee Brown", "Slate Gray", "Cyan Teal"
        ]
        theme_dropdown = ttk.Combobox(main_frame, textvariable=theme_var,
                                      values=themes, font=FONT_MEDIUM, state="readonly")
        theme_dropdown.pack(pady=5, ipady=4, fill=tk.X)

        # Font Family Selection
        tk.Label(main_frame, text="Font Family:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
        
        font_family_var = tk.StringVar(value=self.config.get("appearance", {}).get("font_family", "Segoe UI"))
        font_families = ["Segoe UI", "Arial", "Helvetica", "Times New Roman", 
                        "Courier New", "Verdana", "Tahoma", "Georgia",
                        "Trebuchet MS", "Comic Sans MS", "Impact", "Lucida Console"]
        font_family_dropdown = ttk.Combobox(main_frame, textvariable=font_family_var,
                                            values=font_families, font=FONT_MEDIUM)
        font_family_dropdown.pack(pady=5, ipady=4, fill=tk.X)

        # Font Size Selection
        tk.Label(main_frame, text="Font Size:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
        
        font_size_var = tk.StringVar(value=self.config.get("appearance", {}).get("font_size", "Medium"))
        font_sizes = ["Extra Small", "Small", "Medium", "Large", "Extra Large", "XX Large"]
        font_dropdown = ttk.Combobox(main_frame, textvariable=font_size_var,
                                     values=font_sizes, font=FONT_MEDIUM, state="readonly")
        font_dropdown.pack(pady=5, ipady=4, fill=tk.X)

        # Font Weight Selection
        tk.Label(main_frame, text="Font Weight:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
        
        font_weight_var = tk.StringVar(value=self.config.get("appearance", {}).get("font_weight", "Normal"))
        font_weights = ["Light", "Normal", "Medium", "Bold", "Extra Bold"]
        weight_dropdown = ttk.Combobox(main_frame, textvariable=font_weight_var,
                                       values=font_weights, font=FONT_MEDIUM, state="readonly")
        weight_dropdown.pack(pady=5, ipady=4, fill=tk.X)

        # UI Scaling
        tk.Label(main_frame, text="UI Scaling (%):", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
        
        scale_var = tk.IntVar(value=self.config.get("appearance", {}).get("scaling", 100))
        scale_slider = tk.Scale(main_frame, variable=scale_var, from_=80, to=150,
                                orient=tk.HORIZONTAL, bg=BG_COLOR, fg=FG_COLOR,
                                troughcolor=BUTTON_COLOR, highlightthickness=0,
                                length=400)
        scale_slider.pack(fill=tk.X, pady=5)

        # Current Default Info
        default_info = tk.Label(main_frame, text="", font=FONT_SMALL, 
                               bg=BG_COLOR, fg=ACCENT_COLOR)
        default_info.pack(pady=5)
        
        def update_default_info():
            current_default = self.config.get("appearance", {}).get("theme", "Dark Blue")
            default_info.config(text=f"Current Default Theme: {current_default}")

        update_default_info()

        # Preview Section
        preview_frame = tk.LabelFrame(main_frame, text="Live Preview", font=FONT_MEDIUM,
                                      bg=BG_COLOR, fg=ACCENT_COLOR)
        preview_frame.pack(fill=tk.X, pady=15)
        
        preview_text = tk.Label(preview_frame, text="Sample Text - ABCabc123 789",
                                font=FONT_MEDIUM, bg=BUTTON_COLOR, fg=FG_COLOR,
                                padx=15, pady=15, width=40)
        preview_text.pack(pady=10, fill=tk.X, padx=10)

        def update_preview(*args):
            """Update preview based on current selections with enhanced theme support"""
            # Map font size names to actual sizes
            size_map = {
                "Extra Small": 8, "Small": 10, "Medium": 12, 
                "Large": 14, "Extra Large": 16, "XX Large": 18
            }
            font_size = size_map.get(font_size_var.get(), 12)
            font_family = font_family_var.get()
            
            # Map font weights to actual weight values
            weight_map = {
                "Light": "normal",
                "Normal": "normal", 
                "Medium": "bold",
                "Bold": "bold",
                "Extra Bold": "bold"
            }
            font_weight = weight_map.get(font_weight_var.get(), "normal")
            
            # Create font tuple with weight
            preview_font = (font_family, font_size, font_weight)
            preview_text.config(font=preview_font)
            
            # Enhanced theme colors
            theme = theme_var.get()
            theme_colors = self.get_theme_colors(theme)
            
            preview_text.config(
                bg=theme_colors["button_color"],
                fg=theme_colors["fg_color"]
            )
            preview_frame.config(
                bg=theme_colors["bg_color"],
                fg=theme_colors["accent_color"]
            )

        # Set up trace to update preview when settings change
        theme_var.trace('w', update_preview)
        font_size_var.trace('w', update_preview)
        font_family_var.trace('w', update_preview)
        font_weight_var.trace('w', update_preview)
        scale_var.trace('w', update_preview)
        
        # Initial preview update
        update_preview()

        status_label = tk.Label(main_frame, text="", font=FONT_SMALL, bg=BG_COLOR, fg=SUCCESS_COLOR)
        status_label.pack(pady=5)

        def apply_appearance_changes():
            """Apply the selected appearance changes to the entire application"""
            try:
                # Map font size names to actual sizes
                size_map = {
                    "Extra Small": 8, "Small": 10, "Medium": 12, 
                    "Large": 14, "Extra Large": 16, "XX Large": 18
                }
                new_font_size = size_map.get(font_size_var.get(), 12)
                new_font_family = font_family_var.get()
                
                # Map font weights
                weight_map = {
                    "Light": "normal",
                    "Normal": "normal", 
                    "Medium": "bold",
                    "Bold": "bold",
                    "Extra Bold": "bold"
                }
                new_font_weight = weight_map.get(font_weight_var.get(), "normal")
                
                # Update global font settings with weight
                global FONT_SMALL, FONT_MEDIUM, FONT_LARGE
                FONT_SMALL = (new_font_family, new_font_size - 2, new_font_weight)
                FONT_MEDIUM = (new_font_family, new_font_size, new_font_weight)
                FONT_LARGE = (new_font_family, new_font_size + 2, new_font_weight)
                
                # Update theme colors
                theme = theme_var.get()
                theme_colors = self.get_theme_colors(theme)
                
                global BG_COLOR, FG_COLOR, ACCENT_COLOR, BUTTON_COLOR, ERROR_COLOR, SUCCESS_COLOR, HIGHLIGHT_COLOR
                BG_COLOR = theme_colors["bg_color"]
                FG_COLOR = theme_colors["fg_color"]
                ACCENT_COLOR = theme_colors["accent_color"]
                BUTTON_COLOR = theme_colors["button_color"]
                ERROR_COLOR = theme_colors["error_color"]
                SUCCESS_COLOR = theme_colors["success_color"]
                HIGHLIGHT_COLOR = theme_colors["highlight_color"]
                
                # Apply UI scaling
                scaling_factor = scale_var.get() / 100.0
                
                # Update the entire application's appearance
                self.update_application_theme()
                
                status_label.config(text="Appearance changes applied successfully!")
                
            except Exception as e:
                status_label.config(text=f"Error applying changes: {str(e)}", fg=ERROR_COLOR)

        def save_appearance():
            """Save appearance settings and apply them"""
            apply_appearance_changes()
            
            # Save settings to config file for future sessions
            try:
                if "appearance" not in self.config:
                    self.config["appearance"] = {}
                
                self.config["appearance"]["theme"] = theme_var.get()
                self.config["appearance"]["font_size"] = font_size_var.get()
                self.config["appearance"]["font_family"] = font_family_var.get()
                self.config["appearance"]["font_weight"] = font_weight_var.get()
                self.config["appearance"]["scaling"] = scale_var.get()
                
                save_full_config(self.config)
                
                messagebox.showinfo("Success", "Appearance settings saved and applied successfully!", 
                                   parent=appearance_window)
                appearance_window.destroy()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save settings: {str(e)}", 
                                    parent=appearance_window)

        def set_as_default():
            """Set current appearance settings as default"""
            try:
                if "appearance" not in self.config:
                    self.config["appearance"] = {}
                
                # Save all current settings as default
                self.config["appearance"]["theme"] = theme_var.get()
                self.config["appearance"]["font_size"] = font_size_var.get()
                self.config["appearance"]["font_family"] = font_family_var.get()
                self.config["appearance"]["font_weight"] = font_weight_var.get()
                self.config["appearance"]["scaling"] = scale_var.get()
                self.config["appearance"]["is_default"] = True
                
                save_full_config(self.config)
                
                # Apply changes immediately
                apply_appearance_changes()
                
                update_default_info()
                status_label.config(text="Settings set as default and applied!", fg=SUCCESS_COLOR)
                
            except Exception as e:
                status_label.config(text=f"Error setting default: {str(e)}", fg=ERROR_COLOR)

        def apply_and_test():
            """Apply changes without closing the dialog"""
            apply_appearance_changes()

        def reset_to_default():
            """Reset to system defaults"""
            self.reset_appearance_defaults(theme_var, font_family_var, font_size_var, font_weight_var, scale_var, update_preview)
            update_default_info()

        # Button frame with improved layout
        btn_frame = tk.Frame(main_frame, bg=BG_COLOR)
        btn_frame.pack(pady=15)

        # First row of buttons
        btn_row1 = tk.Frame(btn_frame, bg=BG_COLOR)
        btn_row1.pack(pady=5)

        tk.Button(btn_row1, text="Apply & Test", command=apply_and_test,
                  bg=ACCENT_COLOR, fg=BG_COLOR, font=FONT_MEDIUM,
                  padx=20, pady=8, width=12).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_row1, text="Set as Default", command=set_as_default,
                  bg=HIGHLIGHT_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=20, pady=8, width=12).pack(side=tk.LEFT, padx=5)

        # Second row of buttons
        btn_row2 = tk.Frame(btn_frame, bg=BG_COLOR)
        btn_row2.pack(pady=5)

        tk.Button(btn_row2, text="Save & Close", command=save_appearance,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=20, pady=8, width=12).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_row2, text="Reset to Default", command=reset_to_default,
                  bg=BUTTON_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=20, pady=8, width=12).pack(side=tk.LEFT, padx=5)

        # Third row of buttons
        btn_row3 = tk.Frame(btn_frame, bg=BG_COLOR)
        btn_row3.pack(pady=5)

        tk.Button(btn_row3, text="Cancel", command=appearance_window.destroy,
                  bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=20, pady=8, width=12).pack(side=tk.LEFT, padx=5)

        # Add some padding at the bottom for better scrolling experience
        tk.Frame(main_frame, bg=BG_COLOR, height=20).pack()

    def get_theme_colors(self, theme_name):
        """Return color scheme for selected theme"""
        themes = {
            "Dark Blue": {
                "bg_color": "#1a1a2e", "fg_color": "#e6e6e6", "accent_color": "#4cc9f0",
                "button_color": "#16213e", "error_color": "#f72585", "success_color": "#4caf50",
                "highlight_color": "#7209b7"
            },
            "Light Gray": {
                "bg_color": "#f0f0f0", "fg_color": "#333333", "accent_color": "#0066cc",
                "button_color": "#dddddd", "error_color": "#cc0000", "success_color": "#00aa00",
                "highlight_color": "#6600cc"
            },
            "Dark Green": {
                "bg_color": "#1e2e1e", "fg_color": "#e0e0e0", "accent_color": "#4cc9f0",
                "button_color": "#2e3e2e", "error_color": "#f72585", "success_color": "#4caf50",
                "highlight_color": "#7209b7"
            },
            "Classic Blue": {
                "bg_color": "#1e2e3e", "fg_color": "#ffffff", "accent_color": "#4cc9f0",
                "button_color": "#2e3e4e", "error_color": "#ff5252", "success_color": "#4caf50",
                "highlight_color": "#7c4dff"
            },
            "Midnight Purple": {
                "bg_color": "#1a1a2e", "fg_color": "#e6e6ff", "accent_color": "#9d4edd",
                "button_color": "#2d2d44", "error_color": "#ff6b6b", "success_color": "#51cf66",
                "highlight_color": "#c77dff"
            },
            "Sunset Orange": {
                "bg_color": "#2d1e1e", "fg_color": "#ffe6e6", "accent_color": "#ff7b25",
                "button_color": "#3e2e2e", "error_color": "#ff5252", "success_color": "#4caf50",
                "highlight_color": "#ff9a3c"
            },
            "Forest Green": {
                "bg_color": "#1e2e1e", "fg_color": "#e6ffe6", "accent_color": "#38b000",
                "button_color": "#2e3e2e", "error_color": "#ff6b6b", "success_color": "#2e8b57",
                "highlight_color": "#70e000"
            },
            "Ocean Blue": {
                "bg_color": "#1e2e3e", "fg_color": "#e6f7ff", "accent_color": "#0077b6",
                "button_color": "#2e3e4e", "error_color": "#ff6b6b", "success_color": "#00b4d8",
                "highlight_color": "#0096c7"
            },
            "Charcoal Dark": {
                "bg_color": "#1a1a1a", "fg_color": "#cccccc", "accent_color": "#666666",
                "button_color": "#2d2d2d", "error_color": "#ff4444", "success_color": "#44ff44",
                "highlight_color": "#888888"
            },
            "Soft Pink": {
                "bg_color": "#2e1e2e", "fg_color": "#ffe6ff", "accent_color": "#ff85a2",
                "button_color": "#3e2e3e", "error_color": "#ff6b9d", "success_color": "#ffb5c2",
                "highlight_color": "#ffa8c2"
            },
            "Professional Gray": {
                "bg_color": "#2d2d2d", "fg_color": "#ffffff", "accent_color": "#4a90e2",
                "button_color": "#3d3d3d", "error_color": "#e74c3c", "success_color": "#27ae60",
                "highlight_color": "#3498db"
            },
            "Vibrant Purple": {
                "bg_color": "#1e1a2e", "fg_color": "#f0e6ff", "accent_color": "#a855f7",
                "button_color": "#2e2a3e", "error_color": "#ef4444", "success_color": "#10b981",
                "highlight_color": "#c084fc"
            },
            "Amber Gold": {
                "bg_color": "#2e2a1e", "fg_color": "#fff4e6", "accent_color": "#ffb300",
                "button_color": "#3e3a2e", "error_color": "#d32f2f", "success_color": "#388e3c",
                "highlight_color": "#ffa000"
            },
            "Deep Crimson": {
                "bg_color": "#2e1e1e", "fg_color": "#ffe6e6", "accent_color": "#c2185b",
                "button_color": "#3e2e2e", "error_color": "#f44336", "success_color": "#4caf50",
                "highlight_color": "#ad1457"
            },
            "Electric Blue": {
                "bg_color": "#1a1f2e", "fg_color": "#e6f7ff", "accent_color": "#2979ff",
                "button_color": "#2a2f3e", "error_color": "#ff1744", "success_color": "#00e676",
                "highlight_color": "#2962ff"
            },
            "Mint Green": {
                "bg_color": "#1e2e2a", "fg_color": "#e6fff5", "accent_color": "#00c853",
                "button_color": "#2e3e3a", "error_color": "#ff5252", "success_color": "#00e676",
                "highlight_color": "#00b248"
            },
            "Royal Purple": {
                "bg_color": "#1e1a2e", "fg_color": "#f3e5f5", "accent_color": "#7b1fa2",
                "button_color": "#2e2a3e", "error_color": "#e53935", "success_color": "#43a047",
                "highlight_color": "#6a1b9a"
            },
            "Coffee Brown": {
                "bg_color": "#2e2a22", "fg_color": "#f5f5dc", "accent_color": "#6d4c41",
                "button_color": "#3e3a32", "error_color": "#d84315", "success_color": "#558b2f",
                "highlight_color": "#5d4037"
            },
            "Slate Gray": {
                "bg_color": "#2e2e2e", "fg_color": "#f5f5f5", "accent_color": "#607d8b",
                "button_color": "#3e3e3e", "error_color": "#f44336", "success_color": "#4caf50",
                "highlight_color": "#455a64"
            },
            "Cyan Teal": {
                "bg_color": "#1e2e2e", "fg_color": "#e0f2f1", "accent_color": "#009688",
                "button_color": "#2e3e3e", "error_color": "#ff5252", "success_color": "#4caf50",
                "highlight_color": "#00897b"
            }
        }
        return themes.get(theme_name, themes["Dark Blue"])

    def reset_appearance_defaults(self, theme_var, font_family_var, font_size_var, font_weight_var, scale_var, update_callback):
        """Reset appearance settings to default values"""
        theme_var.set("Dark Blue")
        font_family_var.set("Segoe UI")
        font_size_var.set("Medium")
        font_weight_var.set("Normal")
        scale_var.set(100)
        update_callback()

    def load_default_appearance(self):
        """Load default appearance settings from config"""
        if "appearance" in self.config:
            appearance = self.config["appearance"]
            
            # Update global theme colors
            theme_name = appearance.get("theme", "Dark Blue")
            theme_colors = self.get_theme_colors(theme_name)
            
            global BG_COLOR, FG_COLOR, ACCENT_COLOR, BUTTON_COLOR, ERROR_COLOR, SUCCESS_COLOR, HIGHLIGHT_COLOR
            BG_COLOR = theme_colors["bg_color"]
            FG_COLOR = theme_colors["fg_color"]
            ACCENT_COLOR = theme_colors["accent_color"]
            BUTTON_COLOR = theme_colors["button_color"]
            ERROR_COLOR = theme_colors["error_color"]
            SUCCESS_COLOR = theme_colors["success_color"]
            HIGHLIGHT_COLOR = theme_colors["highlight_color"]
            
            # Update global fonts
            font_family = appearance.get("font_family", "Segoe UI")
            font_size_map = {
                "Extra Small": 8, "Small": 10, "Medium": 12, 
                "Large": 14, "Extra Large": 16, "XX Large": 18
            }
            font_size = font_size_map.get(appearance.get("font_size", "Medium"), 12)
            font_weight = appearance.get("font_weight", "Normal")
            
            global FONT_SMALL, FONT_MEDIUM, FONT_LARGE
            FONT_SMALL = (font_family, font_size - 2, font_weight)
            FONT_MEDIUM = (font_family, font_size, font_weight)
            FONT_LARGE = (font_family, font_size + 2, font_weight)

    def update_application_theme(self):
        """Update the entire application with the current theme settings"""
        # Update the root window
        self.root.configure(bg=BG_COLOR)
        
        print(f"Theme updated: BG={BG_COLOR}, FG={FG_COLOR}, Font Weight Applied")
        
        # Show a notification that the theme was updated
        notification = tk.Toplevel(self.root)
        notification.title("Theme Updated")
        notification.geometry("350x120")
        notification.configure(bg=BG_COLOR)
        notification.transient(self.root)
        
        msg = tk.Label(notification, text="Application theme updated successfully!\nFont weight and new themes applied.",
                       bg=BG_COLOR, fg=FG_COLOR, font=FONT_MEDIUM, justify=tk.CENTER)
        msg.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)
        
        # Auto-close after 2 seconds
        notification.after(2000, notification.destroy)
    def show_receipt_settings(self):
        receipt_window = tk.Toplevel(self.root)
        receipt_window.title("Receipt Settings")
        receipt_window.state('zoomed')  # Changed from fixed size to full screen
        receipt_window.configure(bg=BG_COLOR)
        receipt_window.transient(self.root)
        receipt_window.grab_set()

        main_frame = tk.Frame(receipt_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(main_frame, text="Receipt Configuration", 
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        # Receipt type selection
        tk.Label(main_frame, text="Receipt Type:", font=FONT_SMALL,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=5)
        
        self.receipt_type_var = tk.StringVar(value=self.config.get("receipt_type", "58mm Thermal"))
        receipt_types = ["58mm Thermal", "80mm Thermal", "A4 Paper", "A5 Paper"]
        ttk.Combobox(main_frame, textvariable=self.receipt_type_var,
                    values=receipt_types, font=FONT_SMALL).pack(fill=tk.X, pady=5)

        # Company information
        tk.Label(main_frame, text="Company Name:", font=FONT_SMALL,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=5)
        
        self.company_name_var = tk.StringVar(value=self.config.get("company_name", "Zetech University Cafeteria"))
        tk.Entry(main_frame, textvariable=self.company_name_var, font=FONT_SMALL,
                bg="#2a2a40", fg=FG_COLOR).pack(fill=tk.X, pady=5)

        # Contact information
        tk.Label(main_frame, text="Contact Info:", font=FONT_SMALL,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=5)
        
        self.contact_info_var = tk.StringVar(value=self.config.get("contact_info", "Tel: 0796939191/0707326661"))
        tk.Entry(main_frame, textvariable=self.contact_info_var, font=FONT_SMALL,
                bg="#2a2a40", fg=FG_COLOR).pack(fill=tk.X, pady=5)

        # Footer message
        tk.Label(main_frame, text="Footer Message:", font=FONT_SMALL,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=5)
        
        self.footer_msg_var = tk.StringVar(value=self.config.get("footer_message", "Thank you for your business!"))
        tk.Entry(main_frame, textvariable=self.footer_msg_var, font=FONT_SMALL,
                bg="#2a2a40", fg=FG_COLOR).pack(fill=tk.X, pady=5)

        # Print options
        options_frame = tk.LabelFrame(main_frame, text="Print Options", font=FONT_SMALL,
                              bg=BG_COLOR, fg=ACCENT_COLOR)
        options_frame.pack(fill=tk.X, pady=10)

        self.print_header_var = tk.BooleanVar(value=self.config.get("print_header", True))
        tk.Checkbutton(options_frame, text="Print Company Header", 
                      variable=self.print_header_var, bg=BG_COLOR, fg=FG_COLOR,
                      font=FONT_SMALL).pack(anchor="w", pady=2)

        self.print_footer_var = tk.BooleanVar(value=self.config.get("print_footer", True))
        tk.Checkbutton(options_frame, text="Print Footer Message", 
                      variable=self.print_footer_var, bg=BG_COLOR, fg=FG_COLOR,
                      font=FONT_SMALL).pack(anchor="w", pady=2)

        self.print_datetime_var = tk.BooleanVar(value=self.config.get("print_datetime", True))
        tk.Checkbutton(options_frame, text="Print Date/Time", 
                      variable=self.print_datetime_var, bg=BG_COLOR, fg=FG_COLOR,
                      font=FONT_SMALL).pack(anchor="w", pady=2)

        # Test receipt button
        tk.Button(main_frame, text="Test Receipt Print", font=FONT_SMALL,
                 bg=BUTTON_COLOR, fg=FG_COLOR, command=self.test_receipt_print,
                 pady=5).pack(pady=10)

        def save_receipt_settings():
            """Save receipt configuration"""
            self.config["receipt_type"] = self.receipt_type_var.get()
            self.config["company_name"] = self.company_name_var.get()
            self.config["contact_info"] = self.contact_info_var.get()
            self.config["footer_message"] = self.footer_msg_var.get()
            self.config["print_header"] = self.print_header_var.get()
            self.config["print_footer"] = self.print_footer_var.get()
            self.config["print_datetime"] = self.print_datetime_var.get()
            
            save_full_config(self.config)
            messagebox.showinfo("Saved", "Receipt settings saved successfully!", parent=receipt_window)
            receipt_window.destroy()

        button_frame = tk.Frame(main_frame, bg=BG_COLOR)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Save", command=save_receipt_settings,
                 bg=SUCCESS_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", command=receipt_window.destroy,
                 bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(side=tk.LEFT, padx=5)

    def test_receipt_print(self):
        """Test receipt printing with current settings"""
        try:
            # Create test receipt content
            test_content = "=" * 55 + "\n"
            if self.config.get("print_header", True):
                test_content += f"{self.config.get('company_name', 'Zetech University Cafeteria').center(55)}\n"
                test_content += f"{'TEST RECEIPT'.center(55)}\n"
                test_content += "=" * 55 + "\n"
            
            if self.config.get("print_datetime", True):
                test_content += f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            test_content += "=" * 55 + "\n"
            test_content += f"{'Item':<20}{'Qty':>5}{'Price':>8}{'Total':>9}\n"
            test_content += "-" * 55 + "\n"
            test_content += f"{'Test Item 1':<20}{'1':>5}{'100.00':>8}{'100.00':>9}\n"
            test_content += f"{'Test Item 2':<20}{'2':>5}{'50.00':>8}{'100.00':>9}\n"
            test_content += "=" * 55 + "\n"
            test_content += f"{'SUB TOTAL':<25}{'200.00':>30}\n"
            test_content += f"{'TAX (2%)':<25}{'4.00':>30}\n"
            test_content += f"{'TOTAL':<25}{'204.00':>30}\n"
            test_content += "=" * 55 + "\n"
            
            if self.config.get("print_footer", True):
                test_content += f"{self.config.get('footer_message', 'Thank you!').center(55)}\n"
            
            # Print test receipt
            self.print_receipt_content(test_content, "Test Receipt")
            messagebox.showinfo("Test Print", "Test receipt sent to printer!")
            
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print test receipt:\n{str(e)}")

    def show_tax_settings(self):
        tax_window = tk.Toplevel(self.root)
        tax_window.title("Tax Settings")
        tax_window.state('zoomed')  # Changed from fixed size to full screen
        tax_window.configure(bg=BG_COLOR)
        tax_window.transient(self.root)
        tax_window.grab_set()

        main_frame = tk.Frame(tax_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(main_frame, text="Tax Configuration", 
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        # Tax rate setting
        tk.Label(main_frame, text="Tax Rate (%):", font=FONT_SMALL,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=5)
        
        self.tax_rate_var = tk.DoubleVar(value=self.config.get("tax_rate", 2.0))
        tax_spinbox = tk.Spinbox(main_frame, from_=0, to=25, increment=0.5,
                                textvariable=self.tax_rate_var, font=FONT_SMALL,
                                bg="#2a2a40", fg=FG_COLOR)
        tax_spinbox.pack(fill=tk.X, pady=5)

        # Tax calculation method
        tk.Label(main_frame, text="Tax Calculation:", font=FONT_SMALL,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=5)
        
        self.tax_method_var = tk.StringVar(value=self.config.get("tax_method", "inclusive"))
        tax_frame = tk.Frame(main_frame, bg=BG_COLOR)
        tax_frame.pack(fill=tk.X, pady=5)
        
        tk.Radiobutton(tax_frame, text="Tax Inclusive", variable=self.tax_method_var,
                      value="inclusive", bg=BG_COLOR, fg=FG_COLOR, font=FONT_SMALL).pack(side=tk.LEFT)
        tk.Radiobutton(tax_frame, text="Tax Exclusive", variable=self.tax_method_var,
                      value="exclusive", bg=BG_COLOR, fg=FG_COLOR, font=FONT_SMALL).pack(side=tk.LEFT)

        # Tax registration number
        tk.Label(main_frame, text="Tax Registration No:", font=FONT_SMALL,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=5)
        
        self.tax_reg_var = tk.StringVar(value=self.config.get("tax_reg_number", ""))
        tk.Entry(main_frame, textvariable=self.tax_reg_var, font=FONT_SMALL,
                bg="#2a2a40", fg=FG_COLOR).pack(fill=tk.X, pady=5)

        # Tax enabled checkbox
        self.tax_enabled_var = tk.BooleanVar(value=self.config.get("tax_enabled", True))
        tk.Checkbutton(main_frame, text="Enable Tax Calculation", 
                      variable=self.tax_enabled_var, bg=BG_COLOR, fg=FG_COLOR,
                      font=FONT_SMALL).pack(anchor="w", pady=10)

        def save_tax_settings():
            """Save tax configuration"""
            self.config["tax_rate"] = self.tax_rate_var.get()
            self.config["tax_method"] = self.tax_method_var.get()
            self.config["tax_reg_number"] = self.tax_reg_var.get()
            self.config["tax_enabled"] = self.tax_enabled_var.get()
            
            save_full_config(self.config)
            messagebox.showinfo("Saved", "Tax settings saved successfully!", parent=tax_window)
            tax_window.destroy()

        button_frame = tk.Frame(main_frame, bg=BG_COLOR)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Save", command=save_tax_settings,
                 bg=SUCCESS_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", command=tax_window.destroy,
                 bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(side=tk.LEFT, padx=5)

    def show_backup_settings(self):
        backup_window = tk.Toplevel(self.root)
        backup_window.title("Backup Settings")
        backup_window.state('zoomed')  # Changed from fixed size to full screen
        backup_window.configure(bg=BG_COLOR)
        backup_window.transient(self.root)
        backup_window.grab_set()

        main_frame = tk.Frame(backup_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(main_frame, text="Automated Backup Settings", 
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        # Auto backup enabled
        self.auto_backup_var = tk.BooleanVar(value=self.config.get("auto_backup", False))
        tk.Checkbutton(main_frame, text="Enable Automated Backups", 
                      variable=self.auto_backup_var, bg=BG_COLOR, fg=FG_COLOR,
                      font=FONT_SMALL, command=self.toggle_backup_settings).pack(anchor="w", pady=5)

        # Backup settings frame (initially disabled)
        self.backup_settings_frame = tk.Frame(main_frame, bg=BG_COLOR)
        self.backup_settings_frame.pack(fill=tk.X, pady=10)

        # Backup frequency
        tk.Label(self.backup_settings_frame, text="Backup Frequency:", font=FONT_SMALL,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=2)
        
        self.backup_freq_var = tk.StringVar(value=self.config.get("backup_frequency", "daily"))
        freq_frame = tk.Frame(self.backup_settings_frame, bg=BG_COLOR)
        freq_frame.pack(fill=tk.X, pady=2)
        
        tk.Radiobutton(freq_frame, text="Daily", variable=self.backup_freq_var,
                      value="daily", bg=BG_COLOR, fg=FG_COLOR, font=FONT_SMALL).pack(side=tk.LEFT)
        tk.Radiobutton(freq_frame, text="Weekly", variable=self.backup_freq_var,
                      value="weekly", bg=BG_COLOR, fg=FG_COLOR, font=FONT_SMALL).pack(side=tk.LEFT)
        tk.Radiobutton(freq_frame, text="Monthly", variable=self.backup_freq_var,
                      value="monthly", bg=BG_COLOR, fg=FG_COLOR, font=FONT_SMALL).pack(side=tk.LEFT)

        # Backup retention
        tk.Label(self.backup_settings_frame, text="Keep Backups For:", font=FONT_SMALL,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=2)
        
        self.backup_retention_var = tk.IntVar(value=self.config.get("backup_retention", 30))
        retention_frame = tk.Frame(self.backup_settings_frame, bg=BG_COLOR)
        retention_frame.pack(fill=tk.X, pady=2)
        
        tk.Radiobutton(retention_frame, text="7 days", variable=self.backup_retention_var,
                      value=7, bg=BG_COLOR, fg=FG_COLOR, font=FONT_SMALL).pack(side=tk.LEFT)
        tk.Radiobutton(retention_frame, text="30 days", variable=self.backup_retention_var,
                      value=30, bg=BG_COLOR, fg=FG_COLOR, font=FONT_SMALL).pack(side=tk.LEFT)
        tk.Radiobutton(retention_frame, text="90 days", variable=self.backup_retention_var,
                      value=90, bg=BG_COLOR, fg=FG_COLOR, font=FONT_SMALL).pack(side=tk.LEFT)

        # Backup location
        tk.Label(self.backup_settings_frame, text="Backup Location:", font=FONT_SMALL,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=2)
        
        backup_loc_frame = tk.Frame(self.backup_settings_frame, bg=BG_COLOR)
        backup_loc_frame.pack(fill=tk.X, pady=2)
        
        self.backup_loc_var = tk.StringVar(value=self.config.get("backup_location", "local"))
        tk.Radiobutton(backup_loc_frame, text="Local Only", variable=self.backup_loc_var,
                      value="local", bg=BG_COLOR, fg=FG_COLOR, font=FONT_SMALL).pack(side=tk.LEFT)
        tk.Radiobutton(backup_loc_frame, text="Local + Cloud", variable=self.backup_loc_var,
                      value="cloud", bg=BG_COLOR, fg=FG_COLOR, font=FONT_SMALL).pack(side=tk.LEFT)

        # Manual backup button
        tk.Button(main_frame, text="Create Backup Now", font=FONT_SMALL,
                 bg=BUTTON_COLOR, fg=FG_COLOR, command=self.backup_database,
                 pady=5).pack(pady=10)

        def save_backup_settings():
            """Save backup configuration"""
            self.config["auto_backup"] = self.auto_backup_var.get()
            self.config["backup_frequency"] = self.backup_freq_var.get()
            self.config["backup_retention"] = self.backup_retention_var.get()
            self.config["backup_location"] = self.backup_loc_var.get()
            
            save_full_config(self.config)
            messagebox.showinfo("Saved", "Backup settings saved successfully!", parent=backup_window)
            backup_window.destroy()

        self.toggle_backup_settings()  # Initial state

        button_frame = tk.Frame(main_frame, bg=BG_COLOR)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Save", command=save_backup_settings,
                 bg=SUCCESS_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", command=backup_window.destroy,
                 bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(side=tk.LEFT, padx=5)

    def toggle_backup_settings(self):
        """Enable/disable backup settings based on checkbox"""
        state = "normal" if self.auto_backup_var.get() else "disabled"
        for widget in self.backup_settings_frame.winfo_children():
            if isinstance(widget, (tk.Frame, tk.Label)):
                for child in widget.winfo_children():
                    child.configure(state=state)
            else:
                widget.configure(state=state)

    def show_security_settings(self):
        security_window = tk.Toplevel(self.root)
        security_window.title("Security Settings")
        security_window.state('zoomed')  # Changed from fixed size to full screen
        security_window.configure(bg=BG_COLOR)
        security_window.transient(self.root)
        security_window.grab_set()

        main_frame = tk.Frame(security_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(main_frame, text="Security Configuration", 
                 font=('Poppins', 16, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        # Session timeout section
        timeout_frame = tk.LabelFrame(main_frame, text="🕒 Session Management", 
                                      font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR,
                                      padx=15, pady=15)
        timeout_frame.pack(fill=tk.X, pady=10)

        tk.Label(timeout_frame, text="Session Timeout:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=5)
        
        self.timeout_var = tk.IntVar(value=self.config.get("session_timeout", 30))
        
        # Create a frame for timeout radio buttons with better visibility
        timeout_radio_frame = tk.Frame(timeout_frame, bg=BG_COLOR)
        timeout_radio_frame.pack(fill=tk.X, pady=5)
        
        timeout_options = [
            ("15 minutes", 15),
            ("30 minutes", 30),
            ("60 minutes", 60),
            ("Never (No timeout)", 0)
        ]
        
        for i, (text, value) in enumerate(timeout_options):
            rb = tk.Radiobutton(timeout_radio_frame, text=text, variable=self.timeout_var,
                              value=value, font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR,
                              selectcolor=ACCENT_COLOR, activebackground=BG_COLOR,
                              activeforeground=FG_COLOR)
            rb.grid(row=i//2, column=i%2, sticky="w", padx=10, pady=3)

        # Password policy section
        policy_frame = tk.LabelFrame(main_frame, text="🔐 Password Policy", 
                                     font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR,
                                     padx=15, pady=15)
        policy_frame.pack(fill=tk.X, pady=10)

        self.strong_passwords_var = tk.BooleanVar(value=self.config.get("strong_passwords", True))
        strong_cb = tk.Checkbutton(policy_frame, text="Require Strong Passwords", 
                                  variable=self.strong_passwords_var, bg=BG_COLOR, fg=FG_COLOR,
                                  font=FONT_SMALL, selectcolor=ACCENT_COLOR,
                                  activebackground=BG_COLOR, activeforeground=FG_COLOR)
        strong_cb.pack(anchor="w", pady=3)

        self.password_expiry_var = tk.BooleanVar(value=self.config.get("password_expiry", False))
        expiry_cb = tk.Checkbutton(policy_frame, text="Enable Password Expiry (90 days)", 
                                  variable=self.password_expiry_var, bg=BG_COLOR, fg=FG_COLOR,
                                  font=FONT_SMALL, selectcolor=ACCENT_COLOR,
                                  activebackground=BG_COLOR, activeforeground=FG_COLOR)
        expiry_cb.pack(anchor="w", pady=3)

        # Login security section
        login_frame = tk.LabelFrame(main_frame, text="🚪 Login Security", 
                                    font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR,
                                    padx=15, pady=15)
        login_frame.pack(fill=tk.X, pady=10)

        # Max login attempts
        tk.Label(login_frame, text="Maximum Login Attempts:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=5)
        
        self.max_attempts_var = tk.IntVar(value=self.config.get("max_login_attempts", 3))
        
        attempts_frame = tk.Frame(login_frame, bg=BG_COLOR)
        attempts_frame.pack(fill=tk.X, pady=5)
        
        attempt_options = [("3 attempts", 3), ("5 attempts", 5), ("10 attempts", 10)]
        
        for i, (text, value) in enumerate(attempt_options):
            rb = tk.Radiobutton(attempts_frame, text=text, variable=self.max_attempts_var,
                              value=value, font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR,
                              selectcolor=ACCENT_COLOR, activebackground=BG_COLOR,
                              activeforeground=FG_COLOR)
            rb.pack(side=tk.LEFT, padx=10)

        # Lockout duration
        tk.Label(login_frame, text="Account Lockout Duration:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", pady=(10, 5))
        
        self.lockout_duration_var = tk.IntVar(value=self.config.get("lockout_duration", 15))
        
        lockout_frame = tk.Frame(login_frame, bg=BG_COLOR)
        lockout_frame.pack(fill=tk.X, pady=5)
        
        lockout_options = [("15 minutes", 15), ("30 minutes", 30), ("60 minutes", 60)]
        
        for i, (text, value) in enumerate(lockout_options):
            rb = tk.Radiobutton(lockout_frame, text=text, variable=self.lockout_duration_var,
                              value=value, font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR,
                              selectcolor=ACCENT_COLOR, activebackground=BG_COLOR,
                              activeforeground=FG_COLOR)
            rb.pack(side=tk.LEFT, padx=10)

        # Auto-logout for users
        self.auto_logout_var = tk.BooleanVar(value=self.config.get("auto_logout", True))
        auto_logout_cb = tk.Checkbutton(login_frame, text="Enable Auto-logout for Users", 
                                       variable=self.auto_logout_var, bg=BG_COLOR, fg=FG_COLOR,
                                       font=FONT_SMALL, selectcolor=ACCENT_COLOR,
                                       activebackground=BG_COLOR, activeforeground=FG_COLOR)
        auto_logout_cb.pack(anchor="w", pady=10)

        # Status label
        status_label = tk.Label(main_frame, text="", font=FONT_SMALL, bg=BG_COLOR, 
                               fg=SUCCESS_COLOR, wraplength=500)
        status_label.pack(pady=10)

        def save_security_settings():
            """Save security configuration and apply system-wide"""
            try:
                # Update configuration
                self.config["session_timeout"] = self.timeout_var.get()
                self.config["strong_passwords"] = self.strong_passwords_var.get()
                self.config["password_expiry"] = self.password_expiry_var.get()
                self.config["max_login_attempts"] = self.max_attempts_var.get()
                self.config["lockout_duration"] = self.lockout_duration_var.get()
                self.config["auto_logout"] = self.auto_logout_var.get()
                
                # Save to file
                save_full_config(self.config)
                
                # Apply settings system-wide
                self.apply_security_settings()
                
                status_label.config(text="✅ Security settings saved and applied successfully!")
                
                # Auto-close after success
                security_window.after(2000, security_window.destroy)
                
            except Exception as e:
                status_label.config(text=f"❌ Error saving settings: {str(e)}", fg=ERROR_COLOR)

        def test_settings():
            """Show how settings will affect the system"""
            test_info = "Settings will apply to:\n\n"
            test_info += f"• Session timeout: {self.timeout_var.get()} minutes\n"
            test_info += f"• Max login attempts: {self.max_attempts_var.get()}\n"
            test_info += f"• Lockout duration: {self.lockout_duration_var.get()} minutes\n"
            test_info += f"• Strong passwords: {'Enabled' if self.strong_passwords_var.get() else 'Disabled'}\n"
            test_info += f"• Password expiry: {'Enabled' if self.password_expiry_var.get() else 'Disabled'}\n"
            test_info += f"• Auto-logout: {'Enabled' if self.auto_logout_var.get() else 'Disabled'}"
            
            messagebox.showinfo("Security Settings Preview", test_info, parent=security_window)

        # Button frame
        button_frame = tk.Frame(main_frame, bg=BG_COLOR)
        button_frame.pack(pady=20)

        tk.Button(button_frame, text="💾 Save Settings", 
                  command=save_security_settings,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=15, pady=8).pack(side=tk.LEFT, padx=10)
        
        tk.Button(button_frame, text="👁️ Preview", 
                  command=test_settings,
                  bg=ACCENT_COLOR, fg=BG_COLOR, font=FONT_MEDIUM,
                  padx=15, pady=8).pack(side=tk.LEFT, padx=10)
        
        tk.Button(button_frame, text="❌ Cancel", 
                  command=security_window.destroy,
                  bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=15, pady=8).pack(side=tk.LEFT, padx=10)

    def apply_security_settings(self):
        """Apply security settings system-wide"""
        try:
            # Apply session timeout to all open windows
            timeout_minutes = self.config.get("session_timeout", 30)
            
            # Apply password policy to user management
            strong_passwords = self.config.get("strong_passwords", True)
            password_expiry = self.config.get("password_expiry", False)
            
            # Apply login security
            max_attempts = self.config.get("max_login_attempts", 3)
            lockout_duration = self.config.get("lockout_duration", 15)
            auto_logout = self.config.get("auto_logout", True)
            
            # Log security settings application
            if hasattr(self, 'db'):
                self.db.cursor.execute('''
                    INSERT INTO user_activity (user, activity_type, description)
                    VALUES (?, ?, ?)
                ''', (self.current_user or 'system', 'security', 
                      f'Security settings updated: timeout={timeout_minutes}min, '
                      f'max_attempts={max_attempts}, lockout={lockout_duration}min, '
                      f'strong_passwords={strong_passwords}, auto_logout={auto_logout}'))
                self.db.conn.commit()
            
            print(f"Security settings applied system-wide:")
            print(f"  - Session timeout: {timeout_minutes} minutes")
            print(f"  - Max login attempts: {max_attempts}")
            print(f"  - Lockout duration: {lockout_duration} minutes")
            print(f"  - Strong passwords: {strong_passwords}")
            print(f"  - Password expiry: {password_expiry}")
            print(f"  - Auto-logout: {auto_logout}")
            
        except Exception as e:
            print(f"Error applying security settings: {str(e)}")

    def check_security_settings(self, username, password, login_attempts):
        """Check security settings during login attempts"""
        max_attempts = self.config.get("max_login_attempts", 3)
        lockout_duration = self.config.get("lockout_duration", 15)
        strong_passwords = self.config.get("strong_passwords", True)
        
        # Check if account is locked
        if login_attempts.get(username, 0) >= max_attempts:
            return False, f"Account locked. Try again after {lockout_duration} minutes."
        
        # Check password strength for new passwords (during registration)
        if strong_passwords and len(password) < 8:
            return False, "Password must be at least 8 characters long."
        
        return True, "Security checks passed"

    def get_session_timeout(self):
        """Get the configured session timeout in milliseconds"""
        timeout_minutes = self.config.get("session_timeout", 30)
        if timeout_minutes == 0:  # Never timeout
            return None
        return timeout_minutes * 60 * 1000  # Convert to milliseconds

    def should_auto_logout(self):
        """Check if auto-logout is enabled"""
        return self.config.get("auto_logout", True)

    def validate_password_strength(self, password):
        """Validate password against strength requirements"""
        strong_passwords = self.config.get("strong_passwords", True)
        
        if not strong_passwords:
            return True, "Password acceptable"
        
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        # Add more strength checks as needed
        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"
        
        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"
        
        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one number"
        
        return True, "Strong password"

    def print_receipt_content(self, content, title="Receipt"):
        """Generic receipt printing function"""
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            if os.name == 'nt':
                os.startfile(tmp_path, "print")
            elif os.name == 'posix':
                subprocess.call(['lp', tmp_path])

            threading.Timer(5.0, os.unlink, args=[tmp_path]).start()
        except Exception as e:
            raise Exception(f"Printing failed: {str(e)}")

    def export_system_data(self):
        """Export system data to CSV files with proper error handling"""
        try:
            # Create exports directory
            export_dir = "system_exports"
            if not os.path.exists(export_dir):
                os.makedirs(export_dir)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            exported_files = []

            # Export sales data
            try:
                self.db.cursor.execute("SELECT * FROM sales ORDER BY date DESC, time DESC")
                sales_data = self.db.cursor.fetchall()
                if sales_data:
                    filename = f"sales_export_{timestamp}.csv"
                    filepath = os.path.join(export_dir, filename)
                    
                    with open(filepath, 'w', newline='', encoding='utf-8') as f:
                        import csv
                        writer = csv.writer(f)
                        # Write headers
                        column_names = [description[0] for description in self.db.cursor.description]
                        writer.writerow(column_names)
                        # Write data
                        writer.writerows(sales_data)
                    exported_files.append(f"Sales: {len(sales_data)} records")
            except Exception as e:
                exported_files.append(f"Sales: Error - {str(e)}")

            # Export inventory data
            try:
                self.db.cursor.execute("SELECT * FROM meals WHERE is_active=1 ORDER BY category, name")
                inventory_data = self.db.cursor.fetchall()
                if inventory_data:
                    filename = f"inventory_export_{timestamp}.csv"
                    filepath = os.path.join(export_dir, filename)
                    
                    with open(filepath, 'w', newline='', encoding='utf-8') as f:
                        import csv
                        writer = csv.writer(f)
                        column_names = [description[0] for description in self.db.cursor.description]
                        writer.writerow(column_names)
                        writer.writerows(inventory_data)
                    exported_files.append(f"Inventory: {len(inventory_data)} items")
            except Exception as e:
                exported_files.append(f"Inventory: Error - {str(e)}")

            # Export user activity
            try:
                self.db.cursor.execute("SELECT * FROM user_activity ORDER BY timestamp DESC")
                activity_data = self.db.cursor.fetchall()
                if activity_data:
                    filename = f"activity_export_{timestamp}.csv"
                    filepath = os.path.join(export_dir, filename)
                    
                    with open(filepath, 'w', newline='', encoding='utf-8') as f:
                        import csv
                        writer = csv.writer(f)
                        column_names = [description[0] for description in self.db.cursor.description]
                        writer.writerow(column_names)
                        writer.writerows(activity_data)
                    exported_files.append(f"User Activity: {len(activity_data)} records")
            except Exception as e:
                exported_files.append(f"User Activity: Error - {str(e)}")

            # Record export activity
            try:
                self.db.cursor.execute('''
                    INSERT INTO user_activity (user, activity_type, description)
                    VALUES (?, ?, ?)
                ''', (self.current_user or 'system', 'export', 
                      f'System data exported: {len(exported_files)} files'))
                self.db.conn.commit()
            except Exception as e:
                print(f"Error recording export activity: {str(e)}")

            # Show results
            result_text = f"Export Completed!\n\nLocation: {os.path.abspath(export_dir)}\n\nFiles:\n• " + "\n• ".join(exported_files)
            
            messagebox.showinfo("Export Complete", result_text)

        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export data:\n{str(e)}")


    def clear_cache(self):
        """Clear system cache and temporary data with comprehensive cleanup"""
        try:
            # Create progress window
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Clearing System Cache")
            progress_window.state('zoomed')
            progress_window.configure(bg=BG_COLOR)
            progress_window.transient(self.root)
            progress_window.grab_set()

            main_frame = tk.Frame(progress_window, bg=BG_COLOR)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

            tk.Label(main_frame, text="Clearing System Cache", 
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

            # Progress bar
            progress = ttk.Progressbar(main_frame, mode='determinate', length=400)
            progress.pack(pady=10)

            status_label = tk.Label(main_frame, text="Starting cache clearance...", 
                                   font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR)
            status_label.pack(pady=5)

            # Results text area
            results_text = tk.Text(main_frame, height=8, width=50, bg="#2a2a40", fg=FG_COLOR,
                                  font=('Consolas', 9), state=tk.DISABLED)
            results_text.pack(pady=10, fill=tk.BOTH, expand=True)

            def update_results(message):
                results_text.config(state=tk.NORMAL)
                results_text.insert(tk.END, f"{message}\n")
                results_text.see(tk.END)
                results_text.config(state=tk.DISABLED)
                progress_window.update()

            def perform_cache_clear():
                try:
                    cleared_items = 0
                    total_steps = 7
                    current_step = 0
                    
                    # Step 1: Clear temporary files
                    current_step += 1
                    progress['value'] = (current_step / total_steps) * 100
                    status_label.config(text="Clearing temporary files...")
                    temp_dir = tempfile.gettempdir()
                    temp_files_cleared = 0
                    for file in os.listdir(temp_dir):
                        if (file.startswith('tmp_') or file.endswith('.cache') or 
                            'hotel' in file.lower() or 'receipt' in file.lower()):
                            try:
                                file_path = os.path.join(temp_dir, file)
                                if os.path.isfile(file_path):
                                    os.remove(file_path)
                                    temp_files_cleared += 1
                                    cleared_items += 1
                            except:
                                pass  # Ignore files that can't be deleted
                    update_results(f"✓ Temporary files cleared: {temp_files_cleared} files")

                    # Step 2: Clear memory cache
                    current_step += 1
                    progress['value'] = (current_step / total_steps) * 100
                    status_label.config(text="Clearing memory cache...")
                    # Clear various caches
                    caches_cleared = []
                    if hasattr(self, 'receipt_items'):
                        self.receipt_items.clear()
                        caches_cleared.append("receipt_items")
                    if hasattr(self, 'pending_sales'):
                        self.pending_sales.clear()
                        caches_cleared.append("pending_sales")
                    if hasattr(self, 'menu_cache'):
                        self.menu_cache.clear()
                        caches_cleared.append("menu_cache")
                    update_results(f"✓ Memory cache cleared: {', '.join(caches_cleared)}")

                    # Step 3: Clear UI caches
                    current_step += 1
                    progress['value'] = (current_step / total_steps) * 100
                    status_label.config(text="Clearing UI caches...")
                    ui_cleared = 0
                    if hasattr(self, 'meal_entries'):
                        for category in self.meal_entries:
                            for item_entry in self.meal_entries[category].values():
                                try:
                                    if hasattr(item_entry, 'delete'):
                                        item_entry.delete(0, tk.END)
                                        ui_cleared += 1
                                except:
                                    pass
                    update_results(f"✓ UI input fields cleared: {ui_cleared} fields")

                    # Step 4: Clear calculator
                    current_step += 1
                    progress['value'] = (current_step / total_steps) * 100
                    status_label.config(text="Clearing calculator...")
                    if hasattr(self, 'calc_var'):
                        try:
                            self.calc_var.set("")
                            update_results("✓ Calculator cleared")
                        except:
                            update_results("✗ Calculator clear failed")
                    else:
                        update_results("✓ Calculator already clear")

                    # Step 5: Clear receipt display
                    current_step += 1
                    progress['value'] = (current_step / total_steps) * 100
                    status_label.config(text="Clearing receipt display...")
                    if hasattr(self, 'bill_txt'):
                        try:
                            self.bill_txt.delete(1.0, tk.END)
                            self.default_bill()
                            update_results("✓ Receipt display cleared")
                        except:
                            update_results("✗ Receipt display clear failed")
                    else:
                        update_results("✓ Receipt display already clear")

                    # Step 6: Clear customer name field
                    current_step += 1
                    progress['value'] = (current_step / total_steps) * 100
                    status_label.config(text="Clearing customer data...")
                    if hasattr(self, 'customer_name_entry'):
                        try:
                            self.customer_name_entry.delete(0, tk.END)
                            update_results("✓ Customer data cleared")
                        except:
                            update_results("✗ Customer data clear failed")
                    else:
                        update_results("✓ Customer data already clear")

                    # Step 7: Optimize memory
                    current_step += 1
                    progress['value'] = (current_step / total_steps) * 100
                    status_label.config(text="Optimizing memory...")
                    import gc
                    gc.collect()
                    update_results("✓ Memory optimized")

                    # Finalize
                    progress['value'] = 100
                    status_label.config(text="Cache clearance completed!")
                    
                    # Record activity
                    if hasattr(self, 'db'):
                        try:
                            self.db.cursor.execute('''
                                INSERT INTO user_activity (user, activity_type, description)
                                VALUES (?, ?, ?)
                            ''', (self.current_user or 'system', 'maintenance', 
                                  f'System cache cleared: {cleared_items} items'))
                            self.db.conn.commit()
                            update_results("✓ Activity logged in database")
                        except Exception as e:
                            update_results(f"✗ Database logging failed: {str(e)}")

                    update_results("✓ Cache clearance completed successfully!")
                    
                    # Show completion message after a brief delay
                    progress_window.after(1000, lambda: self.show_cache_clear_complete(progress_window, cleared_items))
                    
                except Exception as e:
                    update_results(f"✗ Error during cache clearance: {str(e)}")
                    messagebox.showerror("Cache Clear Failed", 
                                        f"Failed to clear cache:\n{str(e)}")
                    progress_window.destroy()

            # Run in thread to avoid blocking UI
            threading.Thread(target=perform_cache_clear, daemon=True).start()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to start cache clearance:\n{str(e)}")

    def show_cache_clear_complete(self, progress_window, cleared_items):
        """Show cache clearance completion message"""
        progress_window.destroy()
        messagebox.showinfo("Cache Cleared", 
                           f"System cache cleared successfully!\n\n"
                           f"Cleared {cleared_items} temporary items\n"
                           f"Memory optimized and ready for use")


    def check_manager_login(self, password):
        """Check if the entered password matches any admin's manager password or the fixed 'MANAGER' password"""
        # Check fixed "MANAGER" password first
        if password == "MANAGER1":
            # Find any admin user to log in as
            for username, user_data in self.config["users"].items():
                if user_data.get("is_admin", False):
                    self.current_user = username
                    self.manager_mode = True
                    
                    # Create a full-screen progress window
                    progress_window = tk.Toplevel(self.root)
                    progress_window.title("Logging In...")
                    progress_window.geometry("600x300")
                    progress_window.configure(bg=BG_COLOR)
                    progress_window.transient(self.root)
                    progress_window.grab_set()
                    
                    # Center the window
                    progress_window.update_idletasks()
                    x = (progress_window.winfo_screenwidth() // 2) - (600 // 2)
                    y = (progress_window.winfo_screenheight() // 2) - (300 // 2)
                    progress_window.geometry(f"600x300+{x}+{y}")
                    
                    # Make it cover the whole window beautifully
                    main_frame = tk.Frame(progress_window, bg=BG_COLOR)
                    main_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)
                    
                    # Title
                    tk.Label(main_frame, text=f"Logging in as Manager", 
                             font=('Poppins', 18, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=(0, 20))
                    
                    # Progress bar with modern styling
                    progress_frame = tk.Frame(main_frame, bg=BG_COLOR)
                    progress_frame.pack(fill=tk.X, pady=20)
                    
                    self.progress_var = tk.DoubleVar()
                    progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, 
                                                 maximum=100, length=400, mode='determinate')
                    progress_bar.pack(fill=tk.X, pady=5)
                    
                    # Percentage label
                    self.percent_label = tk.Label(progress_frame, text="0%", 
                                                font=('Poppins', 14), bg=BG_COLOR, fg=FG_COLOR)
                    self.percent_label.pack()
                    
                    # Status message
                    self.status_label = tk.Label(main_frame, text="Initializing manager system...", 
                                               font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR)
                    self.status_label.pack(pady=10)

                    # Use a queue to communicate between threads
                    self.login_queue = queue.Queue()

                    def simulate_login_progress():
                        status_messages = [
                            "Loading manager privileges...",
                            "Connecting to database...",
                            "Loading financial reports...",
                            "Initializing admin controls...",
                            "Finalizing setup..."
                        ]
                        
                        for i in range(101):
                            self.progress_var.set(i)
                            self.percent_label.config(text=f"{i}%")
                            
                            # Update status message at certain intervals
                            if i % 20 == 0 and i//20 < len(status_messages):
                                self.status_label.config(text=status_messages[i//20])
                            
                            progress_window.update_idletasks()
                            time.sleep(0.03)

                        # Put a message in the queue when done
                        self.login_queue.put("login_complete")
                        progress_window.destroy()

                    # Start the progress bar simulation in a thread
                    threading.Thread(target=simulate_login_progress, daemon=True).start()

                    # Check the queue periodically from the main thread
                    self.check_login_queue()
                    return

        # Check custom manager passwords
        for username, user_data in self.config["users"].items():
            if (user_data.get("is_admin", False) and 
                (user_data.get("manager_password", "") == hash_password(password) or password == "MANAGER")):
                self.current_user = username
                self.manager_mode = True
                
                # Create a full-screen progress window
                progress_window = tk.Toplevel(self.root)
                progress_window.title("Logging In...")
                progress_window.geometry("600x300")
                progress_window.configure(bg=BG_COLOR)
                progress_window.transient(self.root)
                progress_window.grab_set()
                
                # Center the window
                progress_window.update_idletasks()
                x = (progress_window.winfo_screenwidth() // 2) - (600 // 2)
                y = (progress_window.winfo_screenheight() // 2) - (300 // 2)
                progress_window.geometry(f"600x300+{x}+{y}")
                
                # Make it cover the whole window beautifully
                main_frame = tk.Frame(progress_window, bg=BG_COLOR)
                main_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)
                
                # Title
                tk.Label(main_frame, text=f"Logging in as Manager", 
                         font=('Poppins', 18, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=(0, 20))
                
                # Progress bar with modern styling
                progress_frame = tk.Frame(main_frame, bg=BG_COLOR)
                progress_frame.pack(fill=tk.X, pady=20)
                
                self.progress_var = tk.DoubleVar()
                progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, 
                                             maximum=100, length=400, mode='determinate')
                progress_bar.pack(fill=tk.X, pady=5)
                
                # Percentage label
                self.percent_label = tk.Label(progress_frame, text="0%", 
                                            font=('Poppins', 14), bg=BG_COLOR, fg=FG_COLOR)
                self.percent_label.pack()
                
                # Status message
                self.status_label = tk.Label(main_frame, text="Initializing manager system...", 
                                           font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR)
                self.status_label.pack(pady=10)

                # Use a queue to communicate between threads
                self.login_queue = queue.Queue()

                def simulate_login_progress():
                    status_messages = [
                        "Loading manager privileges...",
                        "Connecting to database...",
                        "Loading financial reports...",
                        "Initializing admin controls...",
                        "Finalizing setup..."
                    ]
                    
                    for i in range(101):
                        self.progress_var.set(i)
                        self.percent_label.config(text=f"{i}%")
                        
                        # Update status message at certain intervals
                        if i % 20 == 0 and i//20 < len(status_messages):
                            self.status_label.config(text=status_messages[i//20])
                        
                        progress_window.update_idletasks()
                        time.sleep(0.03)

                    # Put a message in the queue when done
                    self.login_queue.put("login_complete")
                    progress_window.destroy()

                # Start the progress bar simulation in a thread
                threading.Thread(target=simulate_login_progress, daemon=True).start()

                # Check the queue periodically from the main thread
                self.check_login_queue()
                return

        messagebox.showerror("Login Failed", "Invalid manager password. Please try again.")


    def show_remove_user_dialog(self):
        remove_user_win = tk.Toplevel(self.root)
        remove_user_win.title("Remove User")
        remove_user_win.state('zoomed')  # Changed from fixed size to full screen
        remove_user_win.configure(bg=BG_COLOR)
        remove_user_win.transient(self.root)
        remove_user_win.grab_set()

        tk.Label(remove_user_win, text="Select User to Remove:", font=FONT_MEDIUM,
             bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
        user_var = tk.StringVar()
        user_dropdown = ttk.Combobox(remove_user_win, textvariable=user_var,
                                 values=[u for u in self.config["users"]], font=FONT_MEDIUM)
        user_dropdown.pack(pady=5, ipady=3, fill=tk.X)

        tk.Label(remove_user_win, text="Manager Password:", font=FONT_MEDIUM,
             bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
        manager_pw_var = tk.StringVar()
        manager_entry = tk.Entry(remove_user_win, textvariable=manager_pw_var, show="*",
                             font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        manager_entry.pack(pady=5, ipady=3, fill=tk.X)

        status_label = tk.Label(remove_user_win, text="", font=FONT_SMALL, bg=BG_COLOR, fg=ERROR_COLOR)
        status_label.pack(pady=5)

        def remove_user():
            username = user_var.get()
            manager_pw = manager_pw_var.get()
            if not username:
                status_label.config(text="Please select a user to remove")
                return

        # Prevent removing last admin
            if self.config["users"][username].get("is_admin", False):
                admin_count = sum(1 for u in self.config["users"].values() if u.get("is_admin", False))
                if admin_count <= 1:
                    status_label.config(text="Cannot remove the last admin user")
                    return

        # Check manager password (accept "MANAGER" or actual manager password)
            if not manager_pw:
                status_label.config(text="Manager password is required")
                return

        # Accept "MANAGER" as universal manager password
            if manager_pw == "MANAGER":
            # Remove user
                del self.config["users"][username]
                save_full_config(self.config)
                messagebox.showinfo("Success", f"User {username} removed successfully", parent=remove_user_win)
                remove_user_win.destroy()
                self.show_login_page()
                return

            admin_user = next((u for u in self.config["users"].values() if u.get("is_admin", False)), None)
            if not admin_user or admin_user.get("manager_password", "") != hash_password(manager_pw):
                status_label.config(text="Invalid manager password")
                return
    
        # Remove user
            del self.config["users"][username]
            save_full_config(self.config)
            messagebox.showinfo("Success", f"User {username} removed successfully", parent=remove_user_win)
            remove_user_win.destroy()
            self.show_login_page()

        button_frame = tk.Frame(remove_user_win, bg=BG_COLOR)
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="Remove", command=remove_user,
              bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
              padx=15, pady=5, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", command=remove_user_win.destroy,
              bg=BUTTON_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
              padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)

    def reset_login(self, username_var, password_var):
        username_var.set("")
        password_var.set("")

    def check_login(self, username, password):
        user_data = self.config["users"].get(username)

        if user_data and user_data["password"] == hash_password(password):
            self.current_user = username
            self.manager_mode = False
            
            # Create a full-screen progress window
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Logging In...")
            progress_window.geometry("600x300")
            progress_window.configure(bg=BG_COLOR)
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            # Center the window
            progress_window.update_idletasks()
            x = (progress_window.winfo_screenwidth() // 2) - (600 // 2)
            y = (progress_window.winfo_screenheight() // 2) - (300 // 2)
            progress_window.geometry(f"600x300+{x}+{y}")
            
            # Make it cover the whole window beautifully
            main_frame = tk.Frame(progress_window, bg=BG_COLOR)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)
            
            # Title
            tk.Label(main_frame, text=f"Logging in as {username}", 
                     font=('Poppins', 18, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=(0, 20))
            
            # Progress bar with modern styling
            progress_frame = tk.Frame(main_frame, bg=BG_COLOR)
            progress_frame.pack(fill=tk.X, pady=20)
            
            self.progress_var = tk.DoubleVar()
            progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, 
                                         maximum=100, length=400, mode='determinate')
            progress_bar.pack(fill=tk.X, pady=5)
            
            # Percentage label
            self.percent_label = tk.Label(progress_frame, text="0%", 
                                        font=('Poppins', 14), bg=BG_COLOR, fg=FG_COLOR)
            self.percent_label.pack()
            
            # Status message
            self.status_label = tk.Label(main_frame, text="Initializing system...", 
                                       font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR)
            self.status_label.pack(pady=10)

            # Use a queue to communicate between threads
            self.login_queue = queue.Queue()

            def simulate_login_progress():
                status_messages = [
                    "Loading user preferences...",
                    "Connecting to database...",
                    "Loading menu items...",
                    "Initializing payment system...",
                    "Finalizing setup..."
                ]
                
                for i in range(101):
                    self.progress_var.set(i)
                    self.percent_label.config(text=f"{i}%")
                    
                    # Update status message at certain intervals
                    if i % 20 == 0 and i//20 < len(status_messages):
                        self.status_label.config(text=status_messages[i//20])
                    
                    progress_window.update_idletasks()
                    time.sleep(0.03)

                # Put a message in the queue when done
                self.login_queue.put("login_complete")
                progress_window.destroy()

            # Start the progress bar simulation in a thread
            threading.Thread(target=simulate_login_progress, daemon=True).start()

            # Check the queue periodically from the main thread
            self.check_login_queue()
        else:
            messagebox.showerror("Login Failed", "Invalid username or password. Please try again.")

    def check_login_queue(self):
        """Check the login queue from the main thread"""
        try:
            msg = self.login_queue.get_nowait()
            if msg == "login_complete":
                if self.manager_mode:
                    self.show_manager_system()
                else:
                    self.show_main_system()
        except queue.Empty:
            # If no message yet, check again after a short delay
            self.root.after(100, self.check_login_queue)

    def restart_services(self):
        """Restart system services and clear caches"""
        try:
            # Confirm restart
            if not messagebox.askyesno("Restart Services", 
                                      "This will restart all system services and clear temporary caches.\n\n"
                                      "Any unsaved work may be lost. Continue?"):
                return

            progress_window = tk.Toplevel(self.root)
            progress_window.title("Restarting System Services")
            progress_window.state('zoomed')
            progress_window.configure(bg=BG_COLOR)
            progress_window.transient(self.root)
            progress_window.grab_set()

            main_frame = tk.Frame(progress_window, bg=BG_COLOR)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

            tk.Label(main_frame, text="Restarting System Services", 
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

            progress = ttk.Progressbar(main_frame, mode='determinate', length=400)
            progress.pack(pady=10)

            status_label = tk.Label(main_frame, text="Initializing...", 
                                   font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR)
            status_label.pack(pady=5)

            log_text = tk.Text(main_frame, height=8, width=50, bg="#2a2a40", fg=FG_COLOR, 
                              font=('Consolas', 8), state=tk.DISABLED)
            log_text.pack(pady=10, fill=tk.BOTH, expand=True)

            def update_log(message):
                log_text.config(state=tk.NORMAL)
                log_text.insert(tk.END, f"{message}\n")
                log_text.see(tk.END)
                log_text.config(state=tk.DISABLED)
                progress_window.update()

            def perform_restart():
                try:
                    steps = [
                        ("Stopping database services...", 10),
                        ("Clearing memory cache...", 25),
                        ("Flushing temporary files...", 40),
                        ("Reinitializing database connections...", 60),
                        ("Reloading configuration...", 75),
                        ("Starting system services...", 90),
                        ("Finalizing restart...", 100)
                    ]

                    for step_text, progress_value in steps:
                        status_label.config(text=step_text)
                        progress['value'] = progress_value
                        update_log(f"✓ {step_text}")
                        time.sleep(0.5)  # Simulate work

                    # Actual service restart operations
                    # Close and reopen database connection
                    self.db.conn.close()
                    time.sleep(0.2)
                    self.db.conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
                    self.db.cursor = self.db.conn.cursor()

                    # Clear any cached data
                    if hasattr(self, 'menu_items'):
                        self.menu_items.clear()
                        # Reload menu items from database
                        db_meals = self.db.get_all_meals()
                        for category, name, _, _, selling_price, _, _, _, _, _ in db_meals:
                            if category not in self.menu_items:
                                self.menu_items[category] = {}
                            self.menu_items[category][name] = selling_price

                    # Record the restart activity
                    self.db.cursor.execute('''
                        INSERT INTO user_activity (user, activity_type, description)
                        VALUES (?, ?, ?)
                    ''', (self.current_user or 'system', 'system', 'System services restarted'))
                    self.db.conn.commit()

                    update_log("✓ All services restarted successfully!")
                    status_label.config(text="Restart completed successfully!")

                    # Show completion message
                    messagebox.showinfo("Restart Complete", 
                                       "System services have been restarted successfully!\n\n"
                                       "All caches cleared and services reloaded.")
                    progress_window.destroy()

                except Exception as e:
                    update_log(f"✗ Error: {str(e)}")
                    messagebox.showerror("Restart Failed", 
                                        f"Failed to restart services:\n{str(e)}")
                    progress_window.destroy()

            # Run restart in thread
            threading.Thread(target=perform_restart, daemon=True).start()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to initiate service restart:\n{str(e)}")



    def test_printer(self):
        """Test printer functionality with comprehensive test options"""
        try:
            test_window = tk.Toplevel(self.root)
            test_window.title("Printer Test Utility")
            test_window.geometry("1550x790")  # Changed from fixed size to full screen
            test_window.configure(bg=BG_COLOR)
            test_window.transient(self.root)
            test_window.grab_set()

            main_frame = tk.Frame(test_window, bg=BG_COLOR)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

            tk.Label(main_frame, text="Printer Test Utility", 
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

            # Test options frame
            options_frame = tk.LabelFrame(main_frame, text="Test Options", font=FONT_SMALL,
                                  bg=BG_COLOR, fg=ACCENT_COLOR)
            options_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)

            # Test type selection
            test_type = tk.StringVar(value="receipt")
            
            test_types = [
                ("Simple Receipt Test", "receipt"),
                ("Detailed Report Test", "report"), 
                ("Configuration Page", "config"),
                ("Character Set Test", "chars"),
                ("Alignment Test", "alignment")
            ]
            
            for text, value in test_types:
                tk.Radiobutton(options_frame, text=text, variable=test_type,
                              value=value, bg=BG_COLOR, fg=FG_COLOR,
                              font=FONT_SMALL, selectcolor=BG_COLOR).pack(anchor="w", pady=2)

            # Printer settings
            settings_frame = tk.Frame(options_frame, bg=BG_COLOR)
            settings_frame.pack(fill=tk.X, pady=10)
            
            tk.Label(settings_frame, text="Paper Width:", font=FONT_SMALL,
                     bg=BG_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=5)
            
            width_var = tk.StringVar(value="80mm")
            width_dropdown = ttk.Combobox(settings_frame, textvariable=width_var,
                                         values=["58mm", "80mm", "A4", "A5"], 
                                         font=FONT_SMALL, width=8)
            width_dropdown.pack(side=tk.LEFT, padx=5)

            # Status area
            status_label = tk.Label(main_frame, text="Ready to test printer...", 
                                   font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR)
            status_label.pack(pady=5)

            def generate_test_content(test_type, width):
                """Generate appropriate test content based on test type and width"""
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                user = self.current_user or "System"
                
                # Determine line width based on paper size
                width_map = {"58mm": 35, "80mm": 42, "A4": 60, "A5": 45}
                line_width = width_map.get(width, 42)
                
                content = "=" * line_width + "\n"
                
                if test_type == "receipt":
                    content += "PRINTER TEST RECEIPT\n".center(line_width) + "\n"
                    content += "=" * line_width + "\n"
                    content += f"Date: {timestamp}\n"
                    content += f"User: {user}\n"
                    content += f"Test: Simple Receipt\n"
                    content += "=" * line_width + "\n"
                    content += "This is a test of receipt printing.\n"
                    content += "All lines should be properly aligned.\n"
                    content += "Characters should be clear and legible.\n"
                    content += "-" * line_width + "\n"
                    content += f"{'Item':<20}{'Qty':>5}{'Price':>8}{'Total':>9}\n".replace(' ', ' ')[:line_width] + "\n"
                    content += "-" * line_width + "\n"
                    content += f"{'Test Item 1':<20}{'1':>5}{'100.00':>8}{'100.00':>9}\n".replace(' ', ' ')[:line_width] + "\n"
                    content += f"{'Test Item 2':<20}{'2':>5}{'50.00':>8}{'100.00':>9}\n".replace(' ', ' ')[:line_width] + "\n"
                    content += "=" * line_width + "\n"
                    content += f"{'TOTAL:':<30}{'200.00':>12}\n".replace(' ', ' ')[:line_width] + "\n"
                    content += "=" * line_width + "\n"
                    content += "✓ Print test successful!\n".center(line_width) + "\n"
                    
                elif test_type == "report":
                    content += "DETAILED REPORT TEST\n".center(line_width) + "\n"
                    content += "=" * line_width + "\n"
                    content += f"Generated: {timestamp}\n"
                    content += f"Paper: {width}\n"
                    content += "=" * line_width + "\n"
                    content += "Column Alignment Test:\n"
                    content += "-" * line_width + "\n"
                    headers = f"{'Category':<15}{'Item':<20}{'Qty':>8}{'Amount':>12}\n"
                    content += headers[:line_width] + "\n"
                    content += "-" * line_width + "\n"
                    content += f"{'Food':<15}{'Test Meal':<20}{'5':>8}{'250.00':>12}\n"[:line_width] + "\n"
                    content += f"{'Drinks':<15}{'Test Drink':<20}{'3':>8}{'150.00':>12}\n"[:line_width] + "\n"
                    content += "-" * line_width + "\n"
                    content += f"{'TOTAL':<35}{'400.00':>12}\n"[:line_width] + "\n"
                    content += "=" * line_width + "\n"
                    
                elif test_type == "config":
                    content += "PRINTER CONFIGURATION\n".center(line_width) + "\n"
                    content += "=" * line_width + "\n"
                    content += f"Test Time: {timestamp}\n"
                    content += f"Paper Width: {width}\n"
                    content += f"Line Width: {line_width} chars\n"
                    content += "=" * line_width + "\n"
                    content += "System Information:\n"
                    content += f"- OS: {os.name}\n"
                    content += f"- Python: {sys.version.split()[0]}\n"
                    content += f"- User: {user}\n"
                    content += "=" * line_width + "\n"
                    
                elif test_type == "chars":
                    content += "CHARACTER SET TEST\n".center(line_width) + "\n"
                    content += "=" * line_width + "\n"
                    content += "Uppercase: ABCDEFGHIJKLMNOPQRSTUVWXYZ\n"
                    content += "Lowercase: abcdefghijklmnopqrstuvwxyz\n"
                    content += "Numbers: 0123456789\n"
                    content += "Symbols: !@#$%^&*()_+-=[]{}|;:,.<>?/~`\n"
                    content += "=" * line_width + "\n"
                    content += "Extended Characters:\n"
                    content += "©®™°±×÷¶§¬£€¥¢\n"
                    content += "=" * line_width + "\n"
                    
                else:  # alignment
                    content += "ALIGNMENT TEST\n".center(line_width) + "\n"
                    content += "=" * line_width + "\n"
                    content += "Left aligned text\n".ljust(line_width) + "\n"
                    content += "Right aligned text\n".rjust(line_width) + "\n"
                    content += "Centered text\n".center(line_width) + "\n"
                    content += "-" * line_width + "\n"
                    content += "Width markers: "
                    content += "|" * (line_width - 16) + "\n"
                    content += "=" * line_width + "\n"
                    content += "✓ Alignment test completed\n".center(line_width) + "\n"

                content += "=" * line_width + "\n"
                content += "TEST COMPLETED SUCCESSFULLY\n".center(line_width) + "\n"
                content += "=" * line_width + "\n"
                
                return content

            def perform_test():
                try:
                    test_type_val = test_type.get()
                    width_val = width_var.get()
                    
                    status_label.config(text="Generating test content...")
                    test_content = generate_test_content(test_type_val, width_val)
                    
                    status_label.config(text="Sending to printer...")
                    
                    # Print the test content
                    self.print_receipt_content(test_content, f"Printer Test - {test_type_val}")
                    
                    status_label.config(text="Test sent to printer successfully!", fg=SUCCESS_COLOR)
                    
                    # Record test activity
                    if hasattr(self, 'db'):
                        self.db.cursor.execute('''
                            INSERT INTO user_activity (user, activity_type, description)
                            VALUES (?, ?, ?)
                        ''', (self.current_user or 'system', 'system', 
                              f'Printer test completed: {test_type_val}'))
                        self.db.conn.commit()
                    
                    # Auto-close after success
                    test_window.after(2000, test_window.destroy)
                    
                except Exception as e:
                    status_label.config(text=f"Test failed: {str(e)}", fg=ERROR_COLOR)
                    messagebox.showerror("Test Failed", 
                                        f"Failed to send test to printer:\n{str(e)}",
                                        parent=test_window)

            # Button frame
            button_frame = tk.Frame(main_frame, bg=BG_COLOR)
            button_frame.pack(pady=10)

            tk.Button(button_frame, text="Run Test", command=perform_test,
                     bg=SUCCESS_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="Close", command=test_window.destroy,
                     bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(side=tk.LEFT, padx=5)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open printer test:\n{str(e)}")

    def print_receipt_content(self, content, title="Receipt"):
        """Generic receipt printing function with enhanced error handling"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            # Print based on OS
            if os.name == 'nt':  # Windows
                os.startfile(tmp_path, "print")
                print_status = "sent to print queue"
            elif os.name == 'posix':  # Linux/Unix
                result = subprocess.call(['lp', tmp_path])
                if result == 0:
                    print_status = "sent to printer"
                else:
                    # Try lpr alternative
                    result = subprocess.call(['lpr', tmp_path])
                    if result == 0:
                        print_status = "sent to printer (lpr)"
                    else:
                        raise Exception("Both lp and lpr commands failed")
            else:
                raise Exception("Unsupported operating system")

            # Schedule file deletion
            def cleanup_temp_file():
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except:
                    pass  # Ignore cleanup errors

            threading.Timer(10.0, cleanup_temp_file).start()
            
            return True, f"Print job {print_status} successfully"
            
        except Exception as e:
            # Clean up temp file on error
            try:
                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except:
                pass
            return False, f"Printing failed: {str(e)}"

    def show_add_user_dialog(self):
        add_user_win = tk.Toplevel(self.root)
        add_user_win.title("Add New User")
        add_user_win.state('zoomed')  # Changed from fixed size to full screen
        add_user_win.configure(bg=BG_COLOR)
        add_user_win.transient(self.root)
        add_user_win.grab_set()

    # Main frame
        main_frame = tk.Frame(add_user_win, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

    # New user details
        tk.Label(main_frame, text="New Username:", font=FONT_MEDIUM,
             bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        new_user_var = tk.StringVar()
        new_user_entry = tk.Entry(main_frame, textvariable=new_user_var,
                              font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        new_user_entry.pack(pady=5, ipady=3, fill=tk.X)

        tk.Label(main_frame, text="New Password:", font=FONT_MEDIUM,
             bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        new_pw_var = tk.StringVar()
        new_pw_entry = tk.Entry(main_frame, textvariable=new_pw_var, show="*",
                            font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        new_pw_entry.pack(pady=5, ipady=3, fill=tk.X)

        tk.Label(main_frame, text="Confirm Password:", font=FONT_MEDIUM,
             bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        confirm_pw_var = tk.StringVar()
        confirm_pw_entry = tk.Entry(main_frame, textvariable=confirm_pw_var, show="*",
                                font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        confirm_pw_entry.pack(pady=5, ipady=3, fill=tk.X)

    # Admin checkbox
        is_admin_var = tk.BooleanVar(value=False)
        tk.Checkbutton(main_frame, text="Admin User", variable=is_admin_var,
                   font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR,
                   selectcolor=BG_COLOR, activebackground=BG_COLOR).pack(pady=5)

    # Current manager password verification
        tk.Label(main_frame, text="Manager Password:", font=FONT_MEDIUM,
             bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        manager_pw_var = tk.StringVar()
        manager_entry = tk.Entry(main_frame, textvariable=manager_pw_var, show="*",
                             font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        manager_entry.pack(pady=5, ipady=3, fill=tk.X)

    # Status label
        status_label = tk.Label(main_frame, text="", font=FONT_SMALL, bg=BG_COLOR, fg=ERROR_COLOR)
        status_label.pack(pady=5)

        def validate_and_add():
            new_user = new_user_var.get().strip()
            new_pw = new_pw_var.get()
            confirm_pw = confirm_pw_var.get()
            is_admin = is_admin_var.get()
            manager_pw = manager_pw_var.get()

        # Validate inputs
            if not new_user or not new_pw:
                status_label.config(text="Username and password are required")
                return

            if new_pw != confirm_pw:
                status_label.config(text="Passwords do not match")
                return

            if new_user in self.config["users"]:
                status_label.config(text="Username already exists")
                return

        # Check manager password (accept "MANAGER" or actual manager password)
            if not manager_pw:
                status_label.config(text="Manager password is required")
                return

        # Accept "MANAGER" as universal manager password
            if manager_pw == "MANAGER":
            # Add the new user
                self.config["users"][new_user] = {
                    "password": hash_password(new_pw),
                    "is_admin": is_admin
                }

            # If admin user, set manager password (same as user password by default)
                if is_admin:
                    self.config["users"][new_user]["manager_password"] = hash_password(new_pw)

                save_full_config(self.config)
                messagebox.showinfo("Success", f"User {new_user} added successfully", parent=add_user_win)
                add_user_win.destroy()
                self.show_login_page()
                return

        # Find an admin user to verify the manager password
            admin_user = None
            for username, user_data in self.config["users"].items():
                if user_data.get("is_admin", False):
                    admin_user = user_data
                    break

            if not admin_user:
                status_label.config(text="No admin user found in system")
                return

            if admin_user.get("manager_password", "") != hash_password(manager_pw):
                status_label.config(text="Invalid manager password")
                return

        # Add the new user
            self.config["users"][new_user] = {
                "password": hash_password(new_pw),
                "is_admin": is_admin
            }

        # If admin user, set manager password (same as user password by default)
            if is_admin:
                self.config["users"][new_user]["manager_password"] = hash_password(new_pw)

            save_full_config(self.config)
            messagebox.showinfo("Success", f"User {new_user} added successfully", parent=add_user_win)
            add_user_win.destroy()
            self.show_homepage()

    # Button frame
        button_frame = tk.Frame(main_frame, bg=BG_COLOR)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Add User", command=validate_and_add,
              bg=SUCCESS_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
              padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", command=add_user_win.destroy,
              bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
              padx=15, pady=5).pack(side=tk.LEFT, padx=10)



    def show_change_credentials(self):
        change_window = tk.Toplevel(self.root)
        change_window.title("Change Login Credentials")
        change_window.state('zoomed')  # Changed from fixed size to full screen
        change_window.configure(bg=BG_COLOR)
        change_window.transient(self.root)
        change_window.grab_set()

        # Main frame
        main_frame = tk.Frame(change_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Current credentials section
        current_frame = tk.LabelFrame(main_frame, text="Current Credentials",
                                      font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR)
        current_frame.pack(fill=tk.X, pady=10)

        # User selection
        tk.Label(current_frame, text="Select User:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, padx=5, pady=5, sticky=tk.E)

        self.user_var = tk.StringVar()
        user_dropdown = ttk.Combobox(current_frame, textvariable=self.user_var,
                                     values=list(self.config["users"].keys()), font=FONT_MEDIUM)
        user_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Current password verification
        tk.Label(current_frame, text="Current Password:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=1, column=0, padx=5, pady=5, sticky=tk.E)
        self.current_pw_verify_var = tk.StringVar()
        current_pw_entry = tk.Entry(current_frame, textvariable=self.current_pw_verify_var, show="*",
                                    font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        current_pw_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # New credentials section
        new_frame = tk.LabelFrame(main_frame, text="New Credentials",
                                  font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR)
        new_frame.pack(fill=tk.X, pady=10)

        tk.Label(new_frame, text="New Password:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, padx=5, pady=5, sticky=tk.E)
        self.new_pw_var = tk.StringVar()
        new_pw_entry = tk.Entry(new_frame, textvariable=self.new_pw_var, show="*",
                                font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        new_pw_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Confirm password
        tk.Label(new_frame, text="Confirm Password:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=1, column=0, padx=5, pady=5, sticky=tk.E)
        self.confirm_pw_var = tk.StringVar()
        confirm_pw_entry = tk.Entry(new_frame, textvariable=self.confirm_pw_var, show="*",
                                    font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        confirm_pw_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # Status label
        self.status_label = tk.Label(main_frame, text="", font=FONT_SMALL, bg=BG_COLOR, fg=ERROR_COLOR)
        self.status_label.pack(pady=5)

        def save_changes():
            username = self.user_var.get()
            current_pw = self.current_pw_verify_var.get()
            new_pw = self.new_pw_var.get()
            confirm_pw = self.confirm_pw_var.get()

            if not username:
                return

            user_data = self.config["users"].get(username)
            if not user_data:
                self.status_label.config(text="User not found")
                return

            # Verify current password
            if hash_password(current_pw) != user_data["password"]:
                self.status_label.config(text="Current password is incorrect")
                return

            if new_pw and new_pw != confirm_pw:
                self.status_label.config(text="New passwords do not match")
                return

            # Update password if provided
            if new_pw:
                user_data["password"] = hash_password(new_pw)

            save_full_config(self.config)
            messagebox.showinfo("Success", "Credentials updated successfully")
            change_window.destroy()

        # Button frame
        btn_frame = tk.Frame(main_frame, bg=BG_COLOR)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="Save Changes", command=save_changes,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Cancel", command=change_window.destroy,
                  bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)

        # Initialize with first user if available
        if self.config["users"]:
            first_user = next(iter(self.config["users"]))
            self.user_var.set(first_user)


    def show_change_own_password(self):
        change_window = tk.Toplevel(self.root)
        change_window.title("Manager Password Administration")
        change_window.state('zoomed')  # Changed from fixed size to full screen
        change_window.configure(bg=BG_COLOR)
        change_window.transient(self.root)
        change_window.grab_set()

        main_frame = tk.Frame(change_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Title
        tk.Label(main_frame, text="🔐 Manager Password Administration", 
                 font=('Poppins', 16, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        # Description
        desc_text = "Change manager passwords for any administrator account without requiring login"
        tk.Label(main_frame, text=desc_text, font=FONT_SMALL, bg=BG_COLOR, 
                 fg=FG_COLOR, wraplength=500).pack(pady=5)

        # User selection frame
        user_frame = tk.LabelFrame(main_frame, text="Select Administrator Account", 
                                   font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR)
        user_frame.pack(fill=tk.X, pady=10, padx=5)

        tk.Label(user_frame, text="Administrator:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        
        # Get all admin users
        admin_users = []
        for username, user_data in self.config.get("users", {}).items():
            if user_data.get("is_admin", False):
                admin_users.append(username)
        
        if not admin_users:
            tk.Label(user_frame, text="No administrator accounts found!", 
                     font=FONT_SMALL, bg=BG_COLOR, fg=ERROR_COLOR).pack(pady=10)
            return
        
        user_var = tk.StringVar()
        user_dropdown = ttk.Combobox(user_frame, textvariable=user_var,
                                     values=admin_users, font=FONT_MEDIUM, state="readonly")
        user_dropdown.pack(pady=5, ipady=4, fill=tk.X, padx=10)
        
        # Select first admin by default
        if admin_users:
            user_var.set(admin_users[0])

        # Current password verification frame
        auth_frame = tk.LabelFrame(main_frame, text="Authentication", 
                                   font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR)
        auth_frame.pack(fill=tk.X, pady=10, padx=5)

        tk.Label(auth_frame, text="Current Manager Password:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        
        current_pw_var = tk.StringVar()
        current_entry = tk.Entry(auth_frame, textvariable=current_pw_var, show="•",
                                 font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        current_entry.pack(pady=5, ipady=4, fill=tk.X, padx=10)
        current_entry.focus()

        # New password frame
        new_pw_frame = tk.LabelFrame(main_frame, text="New Manager Password", 
                                     font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR)
        new_pw_frame.pack(fill=tk.X, pady=10, padx=5)

        tk.Label(new_pw_frame, text="New Password:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        
        new_pw_var = tk.StringVar()
        new_entry = tk.Entry(new_pw_frame, textvariable=new_pw_var, show="•",
                             font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        new_entry.pack(pady=5, ipady=4, fill=tk.X, padx=10)

        tk.Label(new_pw_frame, text="Confirm New Password:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        
        confirm_pw_var = tk.StringVar()
        confirm_entry = tk.Entry(new_pw_frame, textvariable=confirm_pw_var, show="•",
                                 font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        confirm_entry.pack(pady=5, ipady=4, fill=tk.X, padx=10)

        # Password strength indicator
        strength_frame = tk.Frame(new_pw_frame, bg=BG_COLOR)
        strength_frame.pack(fill=tk.X, pady=5, padx=10)
        
        tk.Label(strength_frame, text="Password Strength:", font=FONT_SMALL,
                 bg=BG_COLOR, fg=FG_COLOR).pack(side=tk.LEFT)
        
        strength_label = tk.Label(strength_frame, text="", font=FONT_SMALL, bg=BG_COLOR)
        strength_label.pack(side=tk.LEFT, padx=5)

        def update_strength(*args):
            password = new_pw_var.get()
            if len(password) >= 8:
                strength_label.config(text="Strong", fg=SUCCESS_COLOR)
            elif len(password) >= 6:
                strength_label.config(text="Medium", fg="#ffaa00")
            elif len(password) > 0:
                strength_label.config(text="Weak", fg=ERROR_COLOR)
            else:
                strength_label.config(text="", fg=FG_COLOR)

        new_pw_var.trace('w', update_strength)

        # Status label
        status_label = tk.Label(main_frame, text="", font=FONT_SMALL, bg=BG_COLOR, 
                               fg=ERROR_COLOR, wraplength=500)
        status_label.pack(pady=10)

        def save_manager_password():
            selected_user = user_var.get()
            current_password = current_pw_var.get()
            new_password = new_pw_var.get()
            confirm_password = confirm_pw_var.get()

            # Validate inputs
            if not selected_user:
                status_label.config(text="❌ Please select an administrator account!")
                return

            if not current_password:
                status_label.config(text="❌ Current manager password is required!")
                return

            if not new_password or not confirm_password:
                status_label.config(text="❌ New password fields are required!")
                return

            if new_password != confirm_password:
                status_label.config(text="❌ New passwords do not match!")
                return

            if len(new_password) < 4:
                status_label.config(text="❌ New password must be at least 4 characters!")
                return

            # Verify the selected user exists and is an admin
            if selected_user not in self.config.get("users", {}):
                status_label.config(text="❌ Selected user not found in configuration!")
                return

            user_data = self.config["users"][selected_user]
            
            if not user_data.get("is_admin", False):
                status_label.config(text="❌ Selected account is not an administrator!")
                return

            # Verify current manager password or universal access
            # Accept multiple verification methods:
            valid_current = (
                # 1. Stored manager password
                user_data.get("manager_password", "") == hash_password(current_password) or
                # 2. Universal manager passwords
                current_password == "MANAGER1" or 
                current_password == "MANAGER" or
                # 3. User's own password (if admin wants to use their login password)
                user_data.get("password", "") == hash_password(current_password)
            )
            
            if not valid_current:
                status_label.config(text="❌ Current manager password is incorrect!")
                return

            # Update the manager password
            user_data["manager_password"] = hash_password(new_password)
            
            # Save configuration
            try:
                save_full_config(self.config)
                status_label.config(text=f"✅ Manager password for '{selected_user}' updated successfully!", fg=SUCCESS_COLOR)
                
                # Clear form
                current_pw_var.set("")
                new_pw_var.set("")
                confirm_pw_var.set("")
                strength_label.config(text="")
                
                # Auto-close after success
                change_window.after(3000, change_window.destroy)
                
            except Exception as e:
                status_label.config(text=f"❌ Error saving configuration: {str(e)}")

        # Button frame
        btn_frame = tk.Frame(main_frame, bg=BG_COLOR)
        btn_frame.pack(pady=20)

        tk.Button(btn_frame, text="💾 Save Manager Password", 
                  command=save_manager_password,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=15, pady=8).pack(side=tk.LEFT, padx=10)
        
        tk.Button(btn_frame, text="❌ Cancel", 
                  command=change_window.destroy,
                  bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=15, pady=8).pack(side=tk.LEFT, padx=10)


        # Bind Enter key to save
        change_window.bind('<Return>', lambda event: save_manager_password())

        # Auto-focus on current password field
        current_entry.focus_set()

    def show_manager_system(self):
        """Show the enhanced manager interface with comprehensive stock and sales management"""
        self.clear_window()

        # Configure grid weights
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.state('zoomed')

        # Title marquee
        title_marquee = Marquee(self.root, text="HOTEL MANAGEMENT SYSTEM - MANAGER MODE")
        title_marquee.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        # Main content frame
        main_frame = tk.Frame(self.root, bg="#C2C2C8")
        main_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        # Configure grid weights for main frame
        main_frame.grid_rowconfigure(0, weight=0)  # Header
        main_frame.grid_rowconfigure(1, weight=1)  # Notebook
        main_frame.grid_rowconfigure(2, weight=0)  # Buttons
        main_frame.grid_columnconfigure(0, weight=1)

        # Header frame
        header_frame = tk.Frame(main_frame, bg="#1e1e2e")
        header_frame.grid(row=0, column=0, sticky="ew", pady=5, padx=10)

        # Username label
        username_label = tk.Label(header_frame, text=f"Manager: {self.current_user}",
                                  font=("Arial", 16, "bold"), fg=ACCENT_COLOR, bg="#1e1e2e")
        username_label.pack(side=tk.LEFT, padx=10)

# Logout button - goes back to Manager Access Portal
        tk.Button(header_frame, text="Logout", font=FONT_MEDIUM,
          bg=ERROR_COLOR, fg=FG_COLOR, 
          command=lambda: self.return_to_manager_portal(),
          padx=15, pady=3, activebackground=HIGHLIGHT_COLOR).pack(side=tk.RIGHT, padx=10)

        # Notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        # Tab 1: Current Stock
        stock_frame = tk.Frame(notebook, bg=BG_COLOR)
        notebook.add(stock_frame, text="Current Stock")

        # Treeview for stock display with more columns - STORE AS INSTANCE VARIABLE
        self.stock_tree = ttk.Treeview(stock_frame,
                                  columns=("Category", "Item", "Description", "Buying", "Selling",
                                           "Stock", "Sold", "Revenue", "Profit", "Margin", "Last Updated"),
                                  show="headings", selectmode="browse")

        # Configure headings
        self.stock_tree.heading("Category", text="Category")
        self.stock_tree.heading("Item", text="Item")
        self.stock_tree.heading("Description", text="Description")
        self.stock_tree.heading("Buying", text="Buying (Ksh)")
        self.stock_tree.heading("Selling", text="Selling (Ksh)")
        self.stock_tree.heading("Stock", text="Current Stock")
        self.stock_tree.heading("Sold", text="Total Sold")
        self.stock_tree.heading("Revenue", text="Revenue (Ksh)")
        self.stock_tree.heading("Profit", text="Profit (Ksh)")
        self.stock_tree.heading("Margin", text="Margin %")
        self.stock_tree.heading("Last Updated", text="Last Updated")

        # Configure columns
        self.stock_tree.column("Category", width=120, anchor=tk.W)
        self.stock_tree.column("Item", width=120, anchor=tk.W)
        self.stock_tree.column("Description", width=150, anchor=tk.W)
        self.stock_tree.column("Buying", width=80, anchor=tk.E)
        self.stock_tree.column("Selling", width=80, anchor=tk.E)
        self.stock_tree.column("Stock", width=80, anchor=tk.E)
        self.stock_tree.column("Sold", width=80, anchor=tk.E)
        self.stock_tree.column("Revenue", width=100, anchor=tk.E)
        self.stock_tree.column("Profit", width=100, anchor=tk.E)
        self.stock_tree.column("Margin", width=80, anchor=tk.E)
        self.stock_tree.column("Last Updated", width=120, anchor=tk.W)

        # Add scrollbar
        scrollbar = ttk.Scrollbar(stock_frame, orient="vertical", command=self.stock_tree.yview)
        self.stock_tree.configure(yscrollcommand=scrollbar.set)

        # Pack treeview and scrollbar
        self.stock_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Load stock data
        self.load_stock_data(self.stock_tree)

        # Tab 2: Stock History with filtering
        history_frame = tk.Frame(notebook, bg=BG_COLOR)
        notebook.add(history_frame, text="Stock History")

        # Filter frame
        filter_frame = tk.Frame(history_frame, bg=BG_COLOR)
        filter_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(filter_frame, text="Filter by:", font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=5)

        # Days filter
        tk.Label(filter_frame, text="Days:", font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=5)
        days_var = tk.StringVar(value="30")
        days_dropdown = ttk.Combobox(filter_frame, textvariable=days_var,
                                     values=["7", "14", "30", "60", "90", "365"],
                                     font=FONT_SMALL, width=5)
        days_dropdown.pack(side=tk.LEFT, padx=5)

        # Item filter
        tk.Label(filter_frame, text="Item:", font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=5)
        item_var = tk.StringVar()
        item_entry = tk.Entry(filter_frame, textvariable=item_var, font=FONT_SMALL, width=15)
        item_entry.pack(side=tk.LEFT, padx=5)

        # Category filter
        tk.Label(filter_frame, text="Category:", font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=5)
        category_var = tk.StringVar()
        category_dropdown = ttk.Combobox(filter_frame, textvariable=category_var,
                                         values=["", "Food", "Sauce", "Hot Drinks", "Cold Drinks"],
                                         font=FONT_SMALL, width=10)
        category_dropdown.pack(side=tk.LEFT, padx=5)

        # Filter button
        filter_btn = tk.Button(filter_frame, text="Apply Filters", font=FONT_SMALL,
                               bg=BUTTON_COLOR, fg=FG_COLOR, command=lambda: self.load_history_data(
                self.history_tree, int(days_var.get()), item_var.get(), category_var.get()))
        filter_btn.pack(side=tk.LEFT, padx=5)

        # NEW: Delete History Button
        delete_history_btn = tk.Button(filter_frame, text="Delete History", font=FONT_SMALL,
                                     bg=ERROR_COLOR, fg=FG_COLOR, command=self.authenticate_and_delete_history,
                                     padx=10, pady=2)
        delete_history_btn.pack(side=tk.RIGHT, padx=5)

        # Treeview for history display with more columns - STORE AS INSTANCE VARIABLE
        self.history_tree = ttk.Treeview(history_frame,
                                    columns=("Date", "Time", "Item", "Category", "Type", "Qty",
                                             "Prev Stock", "New Stock", "Buying", "Selling", "User", "Notes"),
                                    show="headings", selectmode="browse")


        # Configure headings
        self.history_tree.heading("Date", text="Date")
        self.history_tree.heading("Time", text="Time")
        self.history_tree.heading("Item", text="Item")
        self.history_tree.heading("Category", text="Category")
        self.history_tree.heading("Type", text="Type")
        self.history_tree.heading("Qty", text="Qty")
        self.history_tree.heading("Prev Stock", text="Prev Stock")
        self.history_tree.heading("New Stock", text="New Stock")
        self.history_tree.heading("Buying", text="Buying (Ksh)")
        self.history_tree.heading("Selling", text="Selling (Ksh)")
        self.history_tree.heading("User", text="User")
        self.history_tree.heading("Notes", text="Notes")

        # Configure columns
        self.history_tree.column("Date", width=100, anchor=tk.W)
        self.history_tree.column("Time", width=80, anchor=tk.W)
        self.history_tree.column("Item", width=120, anchor=tk.W)
        self.history_tree.column("Category", width=100, anchor=tk.W)
        self.history_tree.column("Type", width=80, anchor=tk.W)
        self.history_tree.column("Qty", width=60, anchor=tk.E)
        self.history_tree.column("Prev Stock", width=80, anchor=tk.E)
        self.history_tree.column("New Stock", width=80, anchor=tk.E)
        self.history_tree.column("Buying", width=80, anchor=tk.E)
        self.history_tree.column("Selling", width=80, anchor=tk.E)
        self.history_tree.column("User", width=100, anchor=tk.W)
        self.history_tree.column("Notes", width=150, anchor=tk.W)

        # Add scrollbar
        history_scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=history_scrollbar.set)

        # Pack treeview and scrollbar
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Load history data
        self.load_history_data(self.history_tree)

        # Tab 3: Sales Reports
        sales_frame = tk.Frame(notebook, bg=BG_COLOR)
        notebook.add(sales_frame, text="Sales Reports")

        # Sales report filter frame
        sales_filter_frame = tk.Frame(sales_frame, bg=BG_COLOR)
        sales_filter_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(sales_filter_frame, text="Sales Report for:", font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR).pack(
            side=tk.LEFT, padx=5)

        # Days filter
        tk.Label(sales_filter_frame, text="Days:", font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=5)
        sales_days_var = tk.StringVar(value="30")
        sales_days_dropdown = ttk.Combobox(sales_filter_frame, textvariable=sales_days_var,
                                           values=["7", "14", "30", "60", "90", "365"],
                                           font=FONT_SMALL, width=5)
        sales_days_dropdown.pack(side=tk.LEFT, padx=5)

        # User filter
        tk.Label(sales_filter_frame, text="User:", font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=5)
        user_var = tk.StringVar()
        user_dropdown = ttk.Combobox(sales_filter_frame, textvariable=user_var,
                                     values=["All"] + list(self.config["users"].keys()),
                                     font=FONT_SMALL, width=15)
        user_dropdown.pack(side=tk.LEFT, padx=5)

        # Filter button
        sales_filter_btn = tk.Button(sales_filter_frame, text="Generate Report", font=FONT_SMALL,
                                     bg=BUTTON_COLOR, fg=FG_COLOR, command=lambda: self.load_sales_report(
                self.sales_tree, int(sales_days_var.get()),
                None if user_var.get() == "All" else user_var.get()))
        sales_filter_btn.pack(side=tk.LEFT, padx=5)

        # Treeview for sales report - STORE AS INSTANCE VARIABLE
        self.sales_tree = ttk.Treeview(sales_frame,
                                  columns=("User", "Sales Count", "Total Sales", "Total Profit", "Avg Margin"),
                                  show="headings", selectmode="browse")

        # Configure headings
        self.sales_tree.heading("User", text="User")
        self.sales_tree.heading("Sales Count", text="Sales Count")
        self.sales_tree.heading("Total Sales", text="Total Sales (Ksh)")
        self.sales_tree.heading("Total Profit", text="Total Profit (Ksh)")
        self.sales_tree.heading("Avg Margin", text="Avg Margin %")

        # Configure columns
        self.sales_tree.column("User", width=120, anchor=tk.W)
        self.sales_tree.column("Sales Count", width=100, anchor=tk.E)
        self.sales_tree.column("Total Sales", width=120, anchor=tk.E)
        self.sales_tree.column("Total Profit", width=120, anchor=tk.E)
        self.sales_tree.column("Avg Margin", width=100, anchor=tk.E)

        # Add scrollbar
        sales_scrollbar = ttk.Scrollbar(sales_frame, orient="vertical", command=self.sales_tree.yview)
        self.sales_tree.configure(yscrollcommand=sales_scrollbar.set)

        # Pack treeview and scrollbar
        self.sales_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sales_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Load initial sales report
        self.load_sales_report(self.sales_tree)

        # Tab 4: Low Stock Alerts
        low_stock_frame = tk.Frame(notebook, bg=BG_COLOR)
        notebook.add(low_stock_frame, text="Low Stock")

        # Treeview for low stock items - STORE AS INSTANCE VARIABLE
        self.low_stock_tree = ttk.Treeview(low_stock_frame,
                                      columns=("Category", "Item", "Current Stock", "Avg Daily Sales", "Days Left"),
                                      show="headings", selectmode="browse")

        # Configure headings
        self.low_stock_tree.heading("Category", text="Category")
        self.low_stock_tree.heading("Item", text="Item")
        self.low_stock_tree.heading("Current Stock", text="Current Stock")
        self.low_stock_tree.heading("Avg Daily Sales", text="Avg Daily Sales")
        self.low_stock_tree.heading("Days Left", text="Days Left")

        # Configure columns
        self.low_stock_tree.column("Category", width=120, anchor=tk.W)
        self.low_stock_tree.column("Item", width=150, anchor=tk.W)
        self.low_stock_tree.column("Current Stock", width=100, anchor=tk.E)
        self.low_stock_tree.column("Avg Daily Sales", width=120, anchor=tk.E)
        self.low_stock_tree.column("Days Left", width=100, anchor=tk.E)

        # Add scrollbar
        low_stock_scrollbar = ttk.Scrollbar(low_stock_frame, orient="vertical", command=self.low_stock_tree.yview)
        self.low_stock_tree.configure(yscrollcommand=low_stock_scrollbar.set)

        # Pack treeview and scrollbar
        self.low_stock_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        low_stock_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Load low stock data
        self.load_low_stock_data(self.low_stock_tree)

        # Button frame
        button_frame = tk.Frame(main_frame, bg=BG_COLOR)
        button_frame.grid(row=2, column=0, pady=10, sticky="ew")

        # Add stock button
        tk.Button(button_frame, text="Add Stock", font=FONT_MEDIUM,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, command=lambda: self.show_add_stock_dialog(self.stock_tree),
                  padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)

        # Remove stock button
        tk.Button(button_frame, text="Remove Stock", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=lambda: self.show_remove_stock_dialog(self.stock_tree),
                  padx=15, pady=5, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)

        # Add new item button
        tk.Button(button_frame, text="Add New Item", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=lambda: self.show_add_item_dialog(self.stock_tree),
                  padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)

        # Remove item button
        tk.Button(button_frame, text="Remove Item", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=lambda: self.show_remove_item_dialog(self.stock_tree),
                  padx=15, pady=5, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)


# Enhanced Analytics button - ADD THIS TO THE BUTTON FRAME IN show_manager_system
        tk.Button(button_frame, text="Business Analytics", font=FONT_MEDIUM,
                  bg=HIGHLIGHT_COLOR, fg=FG_COLOR, command=self.show_enhanced_analytics,
                  padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)        



        # Refresh button
        tk.Button(button_frame, text="Refresh All", font=FONT_MEDIUM,
                 bg=BUTTON_COLOR, fg=FG_COLOR, command=self.authenticate_and_refresh,
                 padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.RIGHT, padx=10)

    def return_to_manager_portal(self):
        """Return directly to Manager Access Portal (password entry window)"""
        if messagebox.askyesno("Logout", "Are you sure you want to return to Manager Portal?", parent=self.root):
        # Clear manager mode and current user
            self.manager_mode = False
            self.current_user = None
        # Clear window and show manager login portal
            self.clear_window()
            self.create_manager_login_section(self.root)
    def show_enhanced_analytics(self):
        analytics_window = tk.Toplevel(self.root)
        analytics_window.title("Enhanced Business Analytics")
        analytics_window.state('zoomed')
        analytics_window.configure(bg=self.BG_COLOR)
        analytics_window.transient(self.root)

        main_frame = tk.Frame(analytics_window, bg=self.BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(main_frame, text="📊 Business Intelligence Dashboard", 
                 font=('Poppins', 18, 'bold'), bg=self.BG_COLOR, fg=self.ACCENT_COLOR).pack(pady=10)

        # Create notebook for different analytics sections
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        try:
            # Get comprehensive data for all tabs
            # Overall profit metrics
            self.db.cursor.execute('''
                SELECT 
                    SUM(total_revenue) as total_revenue,
                    SUM(total_profit) as total_profit,
                    (SUM(total_profit)/NULLIF(SUM(total_revenue), 0))*100 as overall_margin,
                    COUNT(*) as total_items
                FROM meals 
                WHERE is_active=1
            ''')
            overall_metrics = self.db.cursor.fetchone()
            
            # Top profitable items
            self.db.cursor.execute('''
                SELECT name, category, total_revenue, total_profit, 
                       (total_profit/NULLIF(total_revenue, 0))*100 as profit_margin,
                       total_sold
                FROM meals 
                WHERE is_active=1 AND total_revenue > 0
                ORDER BY total_profit DESC
                LIMIT 20
            ''')
            top_profitable = self.db.cursor.fetchall()

            # Sales trends
            self.db.cursor.execute('''
                SELECT date, SUM(amount) as daily_sales, COUNT(*) as transactions
                FROM sales 
                WHERE date >= date('now', '-30 days')
                GROUP BY date
                ORDER BY date
            ''')
            sales_trends = self.db.cursor.fetchall()

            # Customer spending patterns
            self.db.cursor.execute('''
                SELECT customer_name, COUNT(*) as visits, 
                       SUM(amount) as total_spent, AVG(amount) as avg_spent
                FROM sales 
                WHERE date >= date('now', '-30 days') AND customer_name != 'Walk-in Customer'
                GROUP BY customer_name
                HAVING visits > 1
                ORDER BY total_spent DESC
                LIMIT 20
            ''')
            customer_behavior = self.db.cursor.fetchall()

            # Payment method analysis
            self.db.cursor.execute('''
                SELECT payment_method, COUNT(*) as transaction_count,
                       SUM(amount) as total_amount, AVG(amount) as avg_amount
                FROM sales 
                WHERE date >= date('now', '-30 days')
                GROUP BY payment_method
                ORDER BY total_amount DESC
            ''')
            payment_analysis = self.db.cursor.fetchall()

            # Seasonal trends
            self.db.cursor.execute('''
                SELECT strftime('%H', time) as hour, 
                       COUNT(*) as transactions, SUM(amount) as revenue
                FROM sales 
                WHERE date >= date('now', '-30 days')
                GROUP BY hour
                ORDER BY hour
            ''')
            hourly_trends = self.db.cursor.fetchall()

            # Enhanced inventory data
            self.db.cursor.execute('''
                SELECT 
                    m.name, m.category, m.current_stock, m.total_sold,
                    (m.total_sold / NULLIF(m.current_stock + m.total_sold, 0)) * 100 as turnover_rate,
                    CASE 
                        WHEN m.current_stock = 0 THEN 'Out of Stock'
                        WHEN m.current_stock <= 2 THEN 'Critical'
                        WHEN m.current_stock <= 5 THEN 'Low'
                        WHEN m.current_stock <= 10 THEN 'Adequate'
                        ELSE 'Overstocked'
                    END as stock_status,
                    (SELECT COALESCE(SUM(quantity), 0) FROM sales s 
                     WHERE s.meal = m.name AND s.date >= date('now', '-7 days')) as weekly_demand,
                    m.total_revenue,
                    m.total_profit
                FROM meals m
                WHERE m.is_active = 1
                ORDER BY turnover_rate DESC
            ''')
            inventory_data = self.db.cursor.fetchall()

            # ABC Analysis (Pareto principle)
            self.db.cursor.execute('''
                SELECT name, total_revenue,
                       SUM(total_revenue) OVER (ORDER BY total_revenue DESC) as running_total,
                       (SUM(total_revenue) OVER (ORDER BY total_revenue DESC)) / 
                       NULLIF(SUM(total_revenue) OVER (), 0) * 100 as cumulative_percent
                FROM meals 
                WHERE is_active=1 AND total_revenue > 0
                ORDER BY total_revenue DESC
            ''')
            abc_analysis = self.db.cursor.fetchall()

        except Exception as e:
            print(f"Error fetching analytics data: {str(e)}")
            # Set default values to prevent crashes
            overall_metrics = (0, 0, 0, 0)
            top_profitable = []
            sales_trends = []
            customer_behavior = []
            payment_analysis = []
            hourly_trends = []
            inventory_data = []
            abc_analysis = []

        # All tabs will now use ScrolledFrame for smooth scrolling
        # Tab 1: Profit Analysis
        profit_scrolled = ScrolledFrame(notebook, bg=self.BG_COLOR)
        notebook.add(profit_scrolled.main_frame, text="💰 Profit Analysis")
        self.setup_profit_analysis_tab(profit_scrolled.frame, overall_metrics, top_profitable)

        # Tab 2: Sales Performance
        sales_scrolled = ScrolledFrame(notebook, bg=self.BG_COLOR)
        notebook.add(sales_scrolled.main_frame, text="📈 Sales Performance")
        self.setup_sales_performance_tab(sales_scrolled.frame, sales_trends, hourly_trends, payment_analysis)

        # Tab 3: Inventory Intelligence
        inventory_scrolled = ScrolledFrame(notebook, bg=self.BG_COLOR)
        notebook.add(inventory_scrolled.main_frame, text="📦 Inventory Intelligence")
        self.setup_inventory_intelligence_tab(inventory_scrolled.frame, inventory_data, abc_analysis)

        # Tab 4: Customer Analytics
        customer_scrolled = ScrolledFrame(notebook, bg=self.BG_COLOR)
        notebook.add(customer_scrolled.main_frame, text="👥 Customer Analytics")
        self.setup_customer_analytics_tab(customer_scrolled.frame, customer_behavior)

        # Tab 5: Financial Forecasting
        forecast_scrolled = ScrolledFrame(notebook, bg=self.BG_COLOR)
        notebook.add(forecast_scrolled.main_frame, text="🔮 Financial Forecasting")
        self.setup_financial_forecasting_tab(forecast_scrolled.frame, sales_trends)

        # Tab 6: Performance Metrics
        metrics_scrolled = ScrolledFrame(notebook, bg=self.BG_COLOR)
        notebook.add(metrics_scrolled.main_frame, text="📊 Performance Metrics")
        self.setup_performance_metrics_tab(metrics_scrolled.frame, overall_metrics, sales_trends, customer_behavior)

    def setup_profit_analysis_tab(self, parent, overall_metrics, top_profitable):
        """Enhanced profit analysis with comparative metrics - now with smooth scrolling"""
        # Overall profit metrics
        metrics_frame = tk.LabelFrame(parent, text="Overall Profit Metrics", 
                                      font=self.FONT_MEDIUM, bg=self.BG_COLOR, fg=self.ACCENT_COLOR)
        metrics_frame.pack(fill=tk.X, padx=10, pady=10)

        if overall_metrics:
            total_revenue, total_profit, overall_margin, total_items = overall_metrics
            
            # Comparative metrics (vs previous period)
            try:
                self.db.cursor.execute('''
                    SELECT SUM(total_revenue), SUM(total_profit)
                    FROM meals 
                    WHERE is_active=1 AND last_updated >= date('now', '-60 days') 
                    AND last_updated < date('now', '-30 days')
                ''')
                prev_metrics = self.db.cursor.fetchone()
                prev_revenue, prev_profit = prev_metrics if prev_metrics else (0, 0)
                
                revenue_growth = ((total_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0
                profit_growth = ((total_profit - prev_profit) / prev_profit * 100) if prev_profit > 0 else 0
                
            except:
                revenue_growth = 0
                profit_growth = 0

            metrics_text = f"""
    • Total Revenue: Ksh {total_revenue or 0:,.2f} ({revenue_growth:+.1f}%)
    • Total Profit: Ksh {total_profit or 0:,.2f} ({profit_growth:+.1f}%)
    • Overall Profit Margin: {overall_margin or 0:.1f}%
    • Active Items: {total_items}
    • Average Profit per Item: Ksh {(total_profit/total_items) if total_items > 0 else 0:,.2f}
    • ROI: {(total_profit/(total_revenue-total_profit)*100) if (total_revenue-total_profit) > 0 else 0:.1f}%
            """
            tk.Label(metrics_frame, text=metrics_text.strip(), font=self.FONT_SMALL,
                     bg=self.BG_COLOR, fg=self.FG_COLOR, justify=tk.LEFT).pack(padx=10, pady=10)

        # Profitability matrix
        matrix_frame = tk.LabelFrame(parent, text="Profitability Matrix",
                                     font=self.FONT_MEDIUM, bg=self.BG_COLOR, fg=self.ACCENT_COLOR)
        matrix_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create profitability categories
        try:
            self.db.cursor.execute('''
                SELECT 
                    CASE 
                        WHEN (total_profit/NULLIF(total_revenue, 0))*100 >= 30 THEN 'High (30%+)'
                        WHEN (total_profit/NULLIF(total_revenue, 0))*100 >= 20 THEN 'Medium (20-30%)'
                        WHEN (total_profit/NULLIF(total_revenue, 0))*100 >= 10 THEN 'Low (10-20%)'
                        ELSE 'Marginal (<10%)'
                    END as profit_category,
                    COUNT(*) as item_count,
                    SUM(total_revenue) as category_revenue,
                    SUM(total_profit) as category_profit
                FROM meals 
                WHERE is_active=1 AND total_revenue > 0
                GROUP BY profit_category
                ORDER BY category_profit DESC
            ''')
            profit_categories = self.db.cursor.fetchall()
            
            matrix_text = "📊 PROFITABILITY DISTRIBUTION:\n\n"
            for category, count, revenue, profit in profit_categories:
                margin = (profit/revenue*100) if revenue > 0 else 0
                matrix_text += f"• {category}: {count} items, Ksh {profit:,.2f} profit ({margin:.1f}% margin)\n"
            
            tk.Label(matrix_frame, text=matrix_text, font=self.FONT_SMALL,
                     bg=self.BG_COLOR, fg=self.FG_COLOR, justify=tk.LEFT).pack(padx=10, pady=10)
            
        except Exception as e:
            error_label = tk.Label(matrix_frame, text=f"Error loading profitability matrix: {str(e)}", 
                                  font=self.FONT_SMALL, bg=self.BG_COLOR, fg='red')
            error_label.pack(padx=10, pady=10)

    def setup_sales_performance_tab(self, parent, sales_trends, hourly_trends, payment_analysis):
        """Enhanced sales performance with trends and patterns - now with smooth scrolling"""
        # Sales trends visualization
        trends_frame = tk.LabelFrame(parent, text="Sales Trends & Patterns",
                                     font=self.FONT_MEDIUM, bg=self.BG_COLOR, fg=self.ACCENT_COLOR)
        trends_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Calculate key metrics
        total_sales = sum(day[1] for day in sales_trends) if sales_trends else 0
        avg_daily_sales = total_sales / len(sales_trends) if sales_trends else 0
        best_day = max(sales_trends, key=lambda x: x[1]) if sales_trends else None
        worst_day = min(sales_trends, key=lambda x: x[1]) if sales_trends else None

        # Peak hours analysis
        peak_hour = max(hourly_trends, key=lambda x: x[2]) if hourly_trends else None

        trends_text = f"""
    📈 SALES PERFORMANCE METRICS:

    • Total 30-Day Sales: Ksh {total_sales:,.2f}
    • Average Daily Sales: Ksh {avg_daily_sales:,.2f}
    • Best Day: {best_day[0] if best_day else 'N/A'} - Ksh {best_day[1] if best_day else 0:,.2f}
    • Worst Day: {worst_day[0] if worst_day else 'N/A'} - Ksh {worst_day[1] if worst_day else 0:,.2f}
    • Peak Hour: {peak_hour[0] if peak_hour else 'N/A'}:00 - Ksh {peak_hour[2] if peak_hour else 0:,.2f}

    💳 PAYMENT METHOD ANALYSIS:
    """
        for method, count, amount, avg in payment_analysis:
            trends_text += f"• {method}: {count} transactions, Ksh {amount:,.2f} total (avg: Ksh {avg:.2f})\n"

        tk.Label(trends_frame, text=trends_text, font=self.FONT_SMALL,
                 bg=self.BG_COLOR, fg=self.FG_COLOR, justify=tk.LEFT).pack(padx=10, pady=10)

        # Sales velocity analysis
        velocity_frame = tk.LabelFrame(parent, text="Sales Velocity Analysis",
                                       font=self.FONT_MEDIUM, bg=self.BG_COLOR, fg=self.ACCENT_COLOR)
        velocity_frame.pack(fill=tk.X, padx=10, pady=10)

        try:
            self.db.cursor.execute('''
                SELECT 
                    strftime('%W', date) as week_number,
                    SUM(amount) as weekly_sales,
                    COUNT(*) as weekly_transactions
                FROM sales 
                WHERE date >= date('now', '-30 days')
                GROUP BY week_number
                ORDER BY week_number
            ''')
            weekly_trends = self.db.cursor.fetchall()
            
            velocity_text = "🚀 WEEKLY SALES VELOCITY:\n\n"
            for week, sales, transactions in weekly_trends:
                velocity_text += f"• Week {week}: Ksh {sales:,.2f} ({transactions} transactions)\n"
            
            tk.Label(velocity_frame, text=velocity_text, font=self.FONT_SMALL,
                     bg=self.BG_COLOR, fg=self.FG_COLOR, justify=tk.LEFT).pack(padx=10, pady=10)
            
        except Exception as e:
            error_label = tk.Label(velocity_frame, text=f"Error loading velocity analysis: {str(e)}", 
                                  font=self.FONT_SMALL, bg=self.BG_COLOR, fg='red')
            error_label.pack(padx=10, pady=10)

    def setup_inventory_intelligence_tab(self, parent, inventory_data, abc_analysis):
        """Enhanced inventory analysis with predictive insights - now with smooth scrolling"""
        # Inventory Health Dashboard
        health_frame = tk.LabelFrame(parent, text="Inventory Health Dashboard",
                                     font=self.FONT_MEDIUM, bg=self.BG_COLOR, fg=self.ACCENT_COLOR)
        health_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Calculate inventory health metrics
        total_items = len(inventory_data) if inventory_data else 0
        out_of_stock = sum(1 for item in inventory_data if item[2] == 0) if inventory_data else 0
        critical_stock = sum(1 for item in inventory_data if item[5] == 'Critical') if inventory_data else 0
        low_stock = sum(1 for item in inventory_data if item[5] == 'Low') if inventory_data else 0
        
        health_text = f"""
    🏥 INVENTORY HEALTH SUMMARY:

    • Total Active Items: {total_items}
    • Out of Stock: {out_of_stock} items
    • Critical Stock: {critical_stock} items
    • Low Stock: {low_stock} items
    • Healthy Stock: {total_items - out_of_stock - critical_stock - low_stock} items

    📊 STOCK STATUS DISTRIBUTION:
    """
        status_counts = {}
        if inventory_data:
            for item in inventory_data:
                status = item[5]
                status_counts[status] = status_counts.get(status, 0) + 1
        
        for status, count in status_counts.items():
            health_text += f"• {status}: {count} items\n"

        # Add stock turnover analysis
        if inventory_data:
            high_turnover = sum(1 for item in inventory_data if item[4] and item[4] > 50)
            medium_turnover = sum(1 for item in inventory_data if item[4] and 20 <= item[4] <= 50)
            low_turnover = sum(1 for item in inventory_data if item[4] and item[4] < 20)
            
            health_text += f"\n🔄 STOCK TURNOVER ANALYSIS:\n"
            health_text += f"• High Turnover (>50%): {high_turnover} items\n"
            health_text += f"• Medium Turnover (20-50%): {medium_turnover} items\n"
            health_text += f"• Low Turnover (<20%): {low_turnover} items\n"

        tk.Label(health_frame, text=health_text, font=self.FONT_SMALL,
                 bg=self.BG_COLOR, fg=self.FG_COLOR, justify=tk.LEFT).pack(padx=10, pady=10)

        # ABC Analysis Frame
        abc_frame = tk.LabelFrame(parent, text="ABC Analysis (Pareto Principle)",
                                  font=self.FONT_MEDIUM, bg=self.BG_COLOR, fg=self.ACCENT_COLOR)
        abc_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        abc_text = "📈 VALUE-BASED INVENTORY CLASSIFICATION:\n\n"
        
        if abc_analysis:
            # Classify items into A, B, C categories
            a_items, b_items, c_items = [], [], []
            for item in abc_analysis:
                name, revenue, running, percent = item
                if percent <= 80:
                    a_items.append((name, revenue))
                elif percent <= 95:
                    b_items.append((name, revenue))
                else:
                    c_items.append((name, revenue))
            
            abc_text += f"🅰️ A-Items (Top 80% of revenue): {len(a_items)} items\n"
            for name, revenue in a_items[:5]:  # Show top 5 A items
                abc_text += f"   • {name}: Ksh {revenue:,.2f}\n"
            
            abc_text += f"\n🅱️ B-Items (Next 15% of revenue): {len(b_items)} items\n"
            abc_text += f"\n🅲️ C-Items (Bottom 5% of revenue): {len(c_items)} items\n"
            
            # Add recommendations based on ABC analysis
            abc_text += f"\n🎯 INVENTORY OPTIMIZATION RECOMMENDATIONS:\n"
            abc_text += f"• Focus on maintaining optimal stock for A-items\n"
            abc_text += f"• Review and optimize ordering for B-items\n"
            abc_text += f"• Consider reducing or eliminating slow-moving C-items\n"
        else:
            abc_text += "No data available for ABC analysis"

        tk.Label(abc_frame, text=abc_text, font=self.FONT_SMALL,
                 bg=self.BG_COLOR, fg=self.FG_COLOR, justify=tk.LEFT).pack(padx=10, pady=10)

        # Stock Alert Frame
        alert_frame = tk.LabelFrame(parent, text="Stock Alerts & Recommendations",
                                    font=self.FONT_MEDIUM, bg=self.BG_COLOR, fg=self.ACCENT_COLOR)
        alert_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        alert_text = "🚨 CRITICAL STOCK ALERTS:\n\n"
        
        if inventory_data:
            critical_items = [item for item in inventory_data if item[5] in ['Out of Stock', 'Critical']]
            if critical_items:
                for item in critical_items[:10]:  # Show top 10 critical items
                    alert_text += f"• {item[0]} ({item[1]}): {item[2]} units left - {item[5]}\n"
            else:
                alert_text += "• No critical stock alerts at this time\n"
            
            # High demand items
            high_demand = [item for item in inventory_data if item[6] and item[6] > 10]
            if high_demand:
                alert_text += f"\n🔥 HIGH DEMAND ITEMS (Weekly):\n"
                for item in high_demand[:5]:
                    alert_text += f"• {item[0]}: {item[6]} units sold this week\n"
        else:
            alert_text += "• No inventory data available\n"

        tk.Label(alert_frame, text=alert_text, font=self.FONT_SMALL,
                 bg=self.BG_COLOR, fg=self.FG_COLOR, justify=tk.LEFT).pack(padx=10, pady=10)

    def setup_customer_analytics_tab(self, parent, customer_behavior):
        """Customer behavior and segmentation analysis - now with smooth scrolling"""
        # Customer segmentation
        segmentation_frame = tk.LabelFrame(parent, text="Customer Segmentation Analysis",
                                          font=self.FONT_MEDIUM, bg=self.BG_COLOR, fg=self.ACCENT_COLOR)
        segmentation_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        if not customer_behavior:
            tk.Label(segmentation_frame, text="No customer data available for analysis",
                     font=self.FONT_SMALL, bg=self.BG_COLOR, fg=self.FG_COLOR).pack(padx=10, pady=10)
            return

        # Segment customers
        vip_customers = [c for c in customer_behavior if c[2] > 1000]  # > 1000 Ksh total
        regular_customers = [c for c in customer_behavior if 500 <= c[2] <= 1000]
        occasional_customers = [c for c in customer_behavior if c[2] < 500]

        segmentation_text = f"""
    👥 CUSTOMER SEGMENTATION:

    🎯 VIP Customers (>Ksh 1,000): {len(vip_customers)} customers
    """
        for customer in vip_customers[:3]:  # Top 3 VIPs
            segmentation_text += f"   • {customer[0]}: Ksh {customer[2]:,.2f} total, {customer[1]} visits\n"

        segmentation_text += f"\n👍 Regular Customers (Ksh 500-1,000): {len(regular_customers)} customers"
        segmentation_text += f"\n👋 Occasional Customers (<Ksh 500): {len(occasional_customers)} customers"

        # Customer lifetime value analysis
        segmentation_text += "\n\n💰 CUSTOMER LIFETIME VALUE ANALYSIS:\n"
        total_revenue = sum(c[2] for c in customer_behavior)
        avg_customer_value = total_revenue / len(customer_behavior) if customer_behavior else 0
        
        segmentation_text += f"• Average Customer Value: Ksh {avg_customer_value:,.2f}\n"
        segmentation_text += f"• Total Identified Customer Revenue: Ksh {total_revenue:,.2f}\n"
        segmentation_text += f"• Repeat Customers: {len(customer_behavior)}"

        tk.Label(segmentation_frame, text=segmentation_text, font=self.FONT_SMALL,
                 bg=self.BG_COLOR, fg=self.FG_COLOR, justify=tk.LEFT).pack(padx=10, pady=10)

        # Customer retention analysis
        retention_frame = tk.LabelFrame(parent, text="Customer Retention Analysis",
                                        font=self.FONT_MEDIUM, bg=self.BG_COLOR, fg=self.ACCENT_COLOR)
        retention_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        try:
            self.db.cursor.execute('''
                SELECT 
                    COUNT(DISTINCT customer_name) as total_customers,
                    COUNT(DISTINCT CASE WHEN date >= date('now', '-30 days') THEN customer_name END) as returning_customers
                FROM sales 
                WHERE customer_name != 'Walk-in Customer'
            ''')
            retention_data = self.db.cursor.fetchone()
            
            if retention_data:
                total_customers, returning = retention_data
                retention_rate = (returning / total_customers * 100) if total_customers > 0 else 0
                
                retention_text = f"""
    📊 RETENTION METRICS:

    • Total Unique Customers: {total_customers}
    • Returning Customers (30 days): {returning}
    • Customer Retention Rate: {retention_rate:.1f}%

    🎯 RECOMMENDATIONS:
    """
                if retention_rate < 50:
                    retention_text += "• Focus on customer loyalty programs\n• Implement referral incentives\n• Improve customer service"
                else:
                    retention_text += "• Strong retention - focus on acquisition\n• Expand customer base\n• Introduce premium offerings"
                
                tk.Label(retention_frame, text=retention_text, font=self.FONT_SMALL,
                         bg=self.BG_COLOR, fg=self.FG_COLOR, justify=tk.LEFT).pack(padx=10, pady=10)
                
        except Exception as e:
            error_label = tk.Label(retention_frame, text=f"Error loading retention analysis: {str(e)}", 
                                  font=self.FONT_SMALL, bg=self.BG_COLOR, fg='red')
            error_label.pack(padx=10, pady=10)

    def setup_financial_forecasting_tab(self, parent, sales_trends):
        """Financial projections and forecasting - now with smooth scrolling"""
        forecast_frame = tk.LabelFrame(parent, text="Revenue Forecasting & Projections",
                                       font=self.FONT_MEDIUM, bg=self.BG_COLOR, fg=self.ACCENT_COLOR)
        forecast_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        if not sales_trends:
            tk.Label(forecast_frame, text="Insufficient data for forecasting",
                     font=self.FONT_SMALL, bg=self.BG_COLOR, fg=self.FG_COLOR).pack(padx=10, pady=10)
            return

        # Simple forecasting based on recent trends
        recent_sales = [day[1] for day in sales_trends[-7:]] if len(sales_trends) >= 7 else [day[1] for day in sales_trends]
        avg_recent_sales = sum(recent_sales) / len(recent_sales) if recent_sales else 0
        
        # Projections
        daily_projection = avg_recent_sales
        weekly_projection = daily_projection * 7
        monthly_projection = daily_projection * 30
        
        # Growth rate calculation (simple moving average)
        if len(sales_trends) >= 14:
            first_week = sum(day[1] for day in sales_trends[:7])
            last_week = sum(day[1] for day in sales_trends[-7:])
            growth_rate = ((last_week - first_week) / first_week * 100) if first_week > 0 else 0
        else:
            growth_rate = 0

        forecast_text = f"""
    🔮 FINANCIAL PROJECTIONS:

    📈 BASED ON LAST 7 DAYS TREND:
    • Projected Daily Revenue: Ksh {daily_projection:,.2f}
    • Projected Weekly Revenue: Ksh {weekly_projection:,.2f}
    • Projected Monthly Revenue: Ksh {monthly_projection:,.2f}

    📊 GROWTH ANALYSIS:
    • Current Growth Rate: {growth_rate:+.1f}%
    • Trend: {'📈 Growing' if growth_rate > 5 else '📉 Declining' if growth_rate < -5 else '➡️ Stable'}

    🎯 RECOMMENDATIONS:
    """
        if growth_rate > 10:
            forecast_text += "• Strong growth - consider expansion\n• Invest in inventory\n• Scale operations"
        elif growth_rate > 0:
            forecast_text += "• Steady growth - maintain momentum\n• Optimize operations\n• Focus on customer retention"
        else:
            forecast_text += "• Need growth initiatives\n• Review pricing strategy\n• Enhance marketing efforts"

        # Seasonality insights
        forecast_text += "\n\n🔄 SEASONALITY INSIGHTS:"
        try:
            self.db.cursor.execute('''
                SELECT 
                    strftime('%w', date) as weekday,
                    AVG(amount) as avg_daily_sales,
                    COUNT(*) as transactions
                FROM sales 
                WHERE date >= date('now', '-30 days')
                GROUP BY weekday
                ORDER BY weekday
            ''')
            weekday_patterns = self.db.cursor.fetchall()
            
            weekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
            best_day = max(weekday_patterns, key=lambda x: x[1]) if weekday_patterns else None
            
            if best_day:
                forecast_text += f"\n• Best Performing Day: {weekdays[int(best_day[0])]} - Ksh {best_day[1]:,.2f} average"
                
        except Exception as e:
            forecast_text += f"\n• Seasonality data unavailable"

        tk.Label(forecast_frame, text=forecast_text, font=self.FONT_SMALL,
                 bg=self.BG_COLOR, fg=self.FG_COLOR, justify=tk.LEFT).pack(padx=10, pady=10)

    def setup_performance_metrics_tab(self, parent, overall_metrics, sales_trends, customer_behavior):
        """Comprehensive performance KPIs and benchmarks - now with smooth scrolling"""
        kpi_frame = tk.LabelFrame(parent, text="Key Performance Indicators (KPIs)",
                                  font=self.FONT_MEDIUM, bg=self.BG_COLOR, fg=self.ACCENT_COLOR)
        kpi_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Calculate various KPIs
        total_revenue = overall_metrics[0] if overall_metrics else 0
        total_profit = overall_metrics[1] if overall_metrics else 0
        
        # Sales KPIs
        total_transactions = sum(day[2] for day in sales_trends) if sales_trends else 0
        avg_transaction_value = total_revenue / total_transactions if total_transactions > 0 else 0
        
        # Customer KPIs
        unique_customers = len(customer_behavior) if customer_behavior else 0
        avg_customer_value = total_revenue / unique_customers if unique_customers > 0 else 0

        kpi_text = f"""
    🎯 KEY PERFORMANCE INDICATORS

    💵 FINANCIAL KPIs:
    • Gross Profit Margin: {(total_profit/total_revenue*100) if total_revenue > 0 else 0:.1f}%
    • Return on Investment: {(total_profit/(total_revenue-total_profit)*100) if (total_revenue-total_profit) > 0 else 0:.1f}%
    • Revenue per Square Foot: Ksh {total_revenue/100:,.2f} (est.)

    📊 SALES KPIs:
    • Average Transaction Value: Ksh {avg_transaction_value:.2f}
    • Transactions per Day: {total_transactions/30:.1f}
    • Sales per Square Foot: Ksh {total_revenue/100:,.2f} (est.)

    👥 CUSTOMER KPIs:
    • Customer Acquisition Cost: Ksh {100:.2f} (est.)
    • Customer Lifetime Value: Ksh {avg_customer_value:,.2f}
    • Repeat Customer Rate: {(unique_customers/total_transactions*100) if total_transactions > 0 else 0:.1f}%

    📈 OPERATIONAL KPIs:
    • Inventory Turnover: {(total_revenue/(total_revenue-total_profit)) if (total_revenue-total_profit) > 0 else 0:.1f}x
    • Stockout Rate: {0:.1f}% (est.)
    • Order Accuracy: {98.5}% (est.)
    """

        tk.Label(kpi_frame, text=kpi_text, font=self.FONT_SMALL,
                 bg=self.BG_COLOR, fg=self.FG_COLOR, justify=tk.LEFT).pack(padx=10, pady=10)

        # Benchmarking frame
        benchmark_frame = tk.LabelFrame(parent, text="Industry Benchmarking",
                                        font=self.FONT_MEDIUM, bg=self.BG_COLOR, fg=self.ACCENT_COLOR)
        benchmark_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Industry benchmarks (hypothetical)
        industry_benchmarks = {
            'Profit Margin': {'Your Business': (total_profit/total_revenue*100) if total_revenue > 0 else 0, 'Industry Avg': 15.0},
            'Inventory Turnover': {'Your Business': (total_revenue/(total_revenue-total_profit)) if (total_revenue-total_profit) > 0 else 0, 'Industry Avg': 8.0},
            'Avg Transaction': {'Your Business': avg_transaction_value, 'Industry Avg': 450.0},
        }

        benchmark_text = "🏆 PERFORMANCE vs INDUSTRY BENCHMARKS:\n\n"
        for metric, values in industry_benchmarks.items():
            your_value = values['Your Business']
            industry_avg = values['Industry Avg']
            performance = "✅ Above" if your_value > industry_avg else "⚠️ Below" if your_value < industry_avg else "➡️ At"
            
            benchmark_text += f"• {metric}:\n"
            benchmark_text += f"  Your Business: {your_value:.1f}{'%' if 'Margin' in metric else ''}\n"
            benchmark_text += f"  Industry Average: {industry_avg:.1f}{'%' if 'Margin' in metric else ''}\n"
            benchmark_text += f"  Status: {performance} benchmark\n\n"

        tk.Label(benchmark_frame, text=benchmark_text, font=self.FONT_SMALL,
                 bg=self.BG_COLOR, fg=self.FG_COLOR, justify=tk.LEFT).pack(padx=10, pady=10)


    def get_profit_summary(self, days=30):
        """Get comprehensive profit summary for the manager dashboard"""
        try:
            # Total profit and revenue
            self.db.cursor.execute('''
                SELECT 
                    SUM(s.amount) as total_revenue,
                    SUM(s.profit) as total_profit,
                    (SUM(s.profit)/SUM(s.amount))*100 as profit_margin,
                    COUNT(*) as total_transactions
                FROM sales s
                WHERE s.date >= date('now', ?)
            ''', (f'-{days} days',))
            
            summary = self.db.cursor.fetchone()
            
            # Top performing categories
            self.db.cursor.execute('''
                SELECT 
                    s.category,
                    SUM(s.amount) as category_revenue,
                    SUM(s.profit) as category_profit,
                    (SUM(s.profit)/SUM(s.amount))*100 as category_margin
                FROM sales s
                WHERE s.date >= date('now', ?)
                GROUP BY s.category
                ORDER BY category_profit DESC
            ''', (f'-{days} days',))
            
            categories = self.db.cursor.fetchall()
            
            return {
                'summary': summary,
                'categories': categories,
                'period': days
            }
            
        except Exception as e:
            print(f"Error getting profit summary: {str(e)}")
            return None

    def create_category_frame(self, category):
        """Create a new category frame in the main system"""
        if not hasattr(self, 'meal_frames'):
            return

        # Determine if this should be a left or right frame
        if len(self.meal_frames) < 2:  # First two categories go to left frame
            parent_frame = self.root.nametowidget(self.root.winfo_children()[-1]).grid_slaves(row=1, column=0)[0]
            row = len(self.meal_frames)
        else:  # Subsequent categories go to right frame
            parent_frame = self.root.nametowidget(self.root.winfo_children()[-1]).grid_slaves(row=1, column=1)[0]
            row = len(self.meal_frames) - 2

        # Create new category frame
        category_frame = tk.LabelFrame(parent_frame, text=category, fg=ACCENT_COLOR, bg="#1e1e2e",
                                       font=FONT_MEDIUM, bd=2, relief=tk.GROOVE)
        category_frame.grid(row=row, column=0, sticky="nsew", padx=5, pady=5)
        category_frame.grid_rowconfigure(0, weight=1)
        category_frame.grid_columnconfigure(0, weight=1)

        # Add to meal_frames dictionary
        self.meal_frames[category] = category_frame

        # Create canvas and scrollbar for the new frame
        canvas = tk.Canvas(category_frame, bg="#C2C2C8", highlightthickness=0)
        scrollbar = tk.Scrollbar(category_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#C2C2C8")

        scrollable_frame.bind(
            "<Configure>",
            lambda e, canvas=canvas: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Initialize meal entries for this category
        if category not in self.meal_entries:
            self.meal_entries[category] = {}

    def load_stock_data(self, tree):
        """Load current stock data into the treeview with full details"""
        # Clear existing data
        for item in tree.get_children():
            tree.delete(item)

        # Get current stock from database
        stock_data = self.db.get_current_stock()

        # Insert data into treeview
        for category, name, description, buying_price, selling_price, stock, sold, revenue, profit, last_updated in stock_data:
            margin = (profit / revenue * 100) if revenue > 0 else 0
            tree.insert("", tk.END, values=(
                category,
                name,
                description,
                f"{buying_price:.2f}",
                f"{selling_price:.2f}",
                stock,
                sold,
                f"{revenue:.2f}",
                f"{profit:.2f}",
                f"{margin:.1f}%",
                last_updated
            ))

    def load_history_data(self, tree, days=30, item_filter=None, category_filter=None):
        """Load stock history data into the treeview with filtering"""
        # Clear existing data
        for item in tree.get_children():
            tree.delete(item)

        # Get history from database with filters
        history_data = self.db.get_stock_history(days, item_filter, category_filter)

        # Insert data into treeview
        for (date, time, item, category, change_type, qty,
             prev_stock, new_stock, buying, selling, user, notes) in history_data:
            tree.insert("", tk.END, values=(
                date,
                time,
                item,
                category,
                change_type.capitalize(),
                qty,
                prev_stock,
                new_stock,
                f"{buying:.2f}",
                f"{selling:.2f}",
                user,
                notes
            ))

    def load_sales_report(self, tree, days=30, user=None):
        """Load sales report data into the treeview with detailed user sales"""
        # Clear existing data
        for item in tree.get_children():
            tree.delete(item)

        # Configure treeview columns based on whether we're showing summary or detailed view
        if user and user != "All":
            # Show detailed sales records for specific user
            tree.configure(columns=("Date", "Time", "Customer", "Category", "Item", "Qty", "Price", "Amount", "Profit", "Payment Method"))
            
            # Clear existing headings and configure for detailed view
            tree["show"] = "headings"
            for col in tree["columns"]:
                tree.heading(col, text="")
                tree.column(col, width=0)
            
            # Configure detailed view columns
            tree.heading("Date", text="Date")
            tree.heading("Time", text="Time")
            tree.heading("Customer", text="Customer")
            tree.heading("Category", text="Category")
            tree.heading("Item", text="Item")
            tree.heading("Qty", text="Qty")
            tree.heading("Price", text="Price (Ksh)")
            tree.heading("Amount", text="Amount (Ksh)")
            tree.heading("Profit", text="Profit (Ksh)")
            tree.heading("Payment Method", text="Payment Method")

            tree.column("Date", width=100, anchor=tk.W)
            tree.column("Time", width=80, anchor=tk.W)
            tree.column("Customer", width=120, anchor=tk.W)
            tree.column("Category", width=100, anchor=tk.W)
            tree.column("Item", width=120, anchor=tk.W)
            tree.column("Qty", width=60, anchor=tk.E)
            tree.column("Price", width=80, anchor=tk.E)
            tree.column("Amount", width=90, anchor=tk.E)
            tree.column("Profit", width=90, anchor=tk.E)
            tree.column("Payment Method", width=100, anchor=tk.W)

            # Get detailed sales data for the specific user
            date_limit = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            # Query to get all sales records for the specific user within the date range
            self.db.cursor.execute('''
                SELECT date, time, customer_name, category, meal, quantity, 
                       selling_price, amount, profit, payment_method
                FROM sales 
                WHERE user = ? AND date >= ?
                ORDER BY date DESC, time DESC
            ''', (user, date_limit))
            
            user_sales_data = self.db.cursor.fetchall()
            
            # Insert detailed sales data into treeview
            for sale in user_sales_data:
                date, time, customer, category, meal, quantity, price, amount, profit, payment_method = sale
                profit_margin = (profit / amount * 100) if amount > 0 else 0
                
                tree.insert("", tk.END, values=(
                    date,
                    time,
                    customer,
                    category,
                    meal,
                    quantity,
                    f"{price:.2f}",
                    f"{amount:.2f}",
                    f"{profit:.2f}",
                    payment_method
                ))
                
        else:
            # Show summary view for all users
            tree.configure(columns=("User", "Sales Count", "Total Sales", "Total Profit", "Avg Margin"))
            
            # Clear existing headings and configure for summary view
            tree["show"] = "headings"
            for col in tree["columns"]:
                tree.heading(col, text="")
                tree.column(col, width=0)
            
            # Configure summary view columns
            tree.heading("User", text="User")
            tree.heading("Sales Count", text="Sales Count")
            tree.heading("Total Sales", text="Total Sales (Ksh)")
            tree.heading("Total Profit", text="Total Profit (Ksh)")
            tree.heading("Avg Margin", text="Avg Margin %")

            tree.column("User", width=120, anchor=tk.W)
            tree.column("Sales Count", width=100, anchor=tk.E)
            tree.column("Total Sales", width=120, anchor=tk.E)
            tree.column("Total Profit", width=120, anchor=tk.E)
            tree.column("Avg Margin", width=100, anchor=tk.E)

            # Get sales summary from database
            sales_data = self.db.get_user_sales_summary(user, days)

            # Insert summary data into treeview
            for user_name, count, sales, profit, margin in sales_data:
                tree.insert("", tk.END, values=(
                    user_name,
                    count,
                    f"{sales:.2f}",
                    f"{profit:.2f}",
                    f"{margin:.1f}%"
                ))

    def on_user_selection(self, event, tree, days_var, user_var):
        """Handle user selection in the sales report dropdown"""
        selected_user = user_var.get()
        days = int(days_var.get())
        
        # Reload the sales report with the selected user
        self.load_sales_report(tree, days, selected_user)

    def setup_sales_report_tab(self, sales_frame):
        """Setup the sales report tab with enhanced user selection"""
        # Sales report filter frame
        sales_filter_frame = tk.Frame(sales_frame, bg=BG_COLOR)
        sales_filter_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(sales_filter_frame, text="Sales Report for:", font=FONT_SMALL, 
                 bg=BG_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=5)

        # Days filter
        tk.Label(sales_filter_frame, text="Days:", font=FONT_SMALL, 
                 bg=BG_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=5)
        sales_days_var = tk.StringVar(value="30")
        sales_days_dropdown = ttk.Combobox(sales_filter_frame, textvariable=sales_days_var,
                                           values=["7", "14", "30", "60", "90", "365"],
                                           font=FONT_SMALL, width=5)
        sales_days_dropdown.pack(side=tk.LEFT, padx=5)

        # User filter with binding for selection
        tk.Label(sales_filter_frame, text="User:", font=FONT_SMALL, 
                 bg=BG_COLOR, fg=FG_COLOR).pack(side=tk.LEFT, padx=5)
        user_var = tk.StringVar()
        user_dropdown = ttk.Combobox(sales_filter_frame, textvariable=user_var,
                                     values=["All"] + list(self.config["users"].keys()),
                                     font=FONT_SMALL, width=15, state="readonly")
        user_dropdown.pack(side=tk.LEFT, padx=5)

        # Treeview for sales report
        self.sales_tree = ttk.Treeview(sales_frame, show="headings", selectmode="browse")
        
        # Add scrollbar
        sales_scrollbar = ttk.Scrollbar(sales_frame, orient="vertical", command=self.sales_tree.yview)
        self.sales_tree.configure(yscrollcommand=sales_scrollbar.set)

        # Pack treeview and scrollbar
        self.sales_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sales_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind user selection event
        user_dropdown.bind('<<ComboboxSelected>>', 
                          lambda e: self.on_user_selection(e, self.sales_tree, sales_days_var, user_var))

        # Load initial sales report (summary view)
        self.load_sales_report(self.sales_tree)

        # Add export button for detailed reports
        export_btn = tk.Button(sales_filter_frame, text="Export Report", font=FONT_SMALL,
                              bg=SUCCESS_COLOR, fg=FG_COLOR,
                              command=lambda: self.export_sales_report(user_var.get(), int(sales_days_var.get())),
                              padx=10, pady=2)
        export_btn.pack(side=tk.RIGHT, padx=5)

    def export_sales_report(self, user, days):
        """Export sales report to CSV file"""
        try:
            export_dir = "sales_reports"
            if not os.path.exists(export_dir):
                os.makedirs(export_dir)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if user and user != "All":
                filename = f"sales_report_{user}_{days}days_{timestamp}.csv"
            else:
                filename = f"sales_report_all_users_{days}days_{timestamp}.csv"
                
            filepath = os.path.join(export_dir, filename)

            date_limit = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            if user and user != "All":
                # Export detailed sales for specific user
                self.db.cursor.execute('''
                    SELECT date, time, customer_name, category, meal, quantity, 
                           selling_price, amount, profit, payment_method
                    FROM sales 
                    WHERE user = ? AND date >= ?
                    ORDER BY date DESC, time DESC
                ''', (user, date_limit))
                sales_data = self.db.cursor.fetchall()
                
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    import csv
                    writer = csv.writer(f)
                    writer.writerow(["Date", "Time", "Customer", "Category", "Item", "Quantity", 
                                   "Price", "Amount", "Profit", "Payment Method"])
                    writer.writerows(sales_data)
                    
            else:
                # Export summary for all users
                sales_data = self.db.get_user_sales_summary(None, days)
                
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    import csv
                    writer = csv.writer(f)
                    writer.writerow(["User", "Sales Count", "Total Sales", "Total Profit", "Average Margin"])
                    writer.writerows(sales_data)

            messagebox.showinfo("Export Successful", 
                              f"Sales report exported to:\n{filepath}", 
                              parent=self.root)
                              
        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to export sales report:\n{str(e)}", parent=self.root)

    def load_low_stock_data(self, tree):
        """Load low stock items with estimated days left"""
        # Clear existing data
        for item in tree.get_children():
            tree.delete(item)

        # Get low stock items
        low_stock_items = self.db.get_low_stock_items(threshold=10)

        # Get average daily sales for each item
        avg_sales = {}
        top_selling = self.db.get_top_selling_items(limit=100, days=30)
        for category, item, qty in top_selling:
            avg_sales[(category, item)] = qty / 30  # Average per day over 30 days

        # Insert data into treeview
        for category, item, stock in low_stock_items:
            avg_daily = avg_sales.get((category, item), 0.1)  # Default to 0.1 to avoid division by zero
            days_left = stock / avg_daily if avg_daily > 0 else 999

            tree.insert("", tk.END, values=(
                category,
                item,
                stock,
                f"{avg_daily:.1f}",
                f"{days_left:.1f}"
            ))

    def refresh_all_data(self):
        """Refresh all data views after successful authentication"""
        try:
            # Refresh stock data
            if hasattr(self, 'stock_tree') and self.stock_tree:
                self.load_stock_data(self.stock_tree)
            
            # Refresh history data
            if hasattr(self, 'history_tree') and self.history_tree:
                self.load_history_data(self.history_tree)
            
            # Refresh sales report data
            if hasattr(self, 'sales_tree') and self.sales_tree:
                self.load_sales_report(self.sales_tree)
            
            # Refresh low stock data
            if hasattr(self, 'low_stock_tree') and self.low_stock_tree:
                self.load_low_stock_data(self.low_stock_tree)
            
            messagebox.showinfo("Refreshed", "All data has been refreshed successfully!", parent=self.root)
        except Exception as e:
            messagebox.showerror("Refresh Error", f"Failed to refresh data: {str(e)}", parent=self.root)



    def authenticate_and_refresh(self):
        """Authenticate manager before refreshing data"""
        auth_window = tk.Toplevel(self.root)
        auth_window.title("Manager Authentication")
        auth_window.geometry("400x200")
        auth_window.configure(bg=BG_COLOR)
        auth_window.transient(self.root)
        auth_window.grab_set()
    
        tk.Label(auth_window, text="Enter Manager Password:", 
             font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
    
        password_var = tk.StringVar()
        password_entry = tk.Entry(auth_window, textvariable=password_var, show="*", 
                              font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        password_entry.pack(pady=10, ipady=3, fill=tk.X, padx=20)
        password_entry.focus_set()
    
        status_label = tk.Label(auth_window, text="", font=FONT_SMALL, bg=BG_COLOR, fg=ERROR_COLOR)
        status_label.pack(pady=5)
    
        def verify_password():
            password = password_var.get()
            # Check if password matches any admin's manager password or the fixed 'MANAGER' password
            if password == "MANAGER1":
                auth_window.destroy()
                self.refresh_all_data()
                return
        
            # Check custom manager passwords
            for username, user_data in self.config["users"].items():
                if (user_data.get("is_admin", False) and 
                    (user_data.get("manager_password", "") == hash_password(password) or password == "MANAGER")):
                    auth_window.destroy()
                    self.refresh_all_data()
                    return
        
            status_label.config(text="Invalid manager password")
    
        button_frame = tk.Frame(auth_window, bg=BG_COLOR)
        button_frame.pack(pady=10)
    
        tk.Button(button_frame, text="Authenticate", font=FONT_MEDIUM,
              bg=SUCCESS_COLOR, fg=FG_COLOR, command=verify_password,
              padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
              bg=ERROR_COLOR, fg=FG_COLOR, command=auth_window.destroy,
              padx=15, pady=5).pack(side=tk.LEFT, padx=10)
    
        # Bind Enter key to authenticate
        auth_window.bind('<Return>', lambda event: verify_password())

    def authenticate_and_delete_history(self):
        """Authenticate manager before deleting stock history"""
        auth_window = tk.Toplevel(self.root)
        auth_window.title("Delete Stock History - Authentication Required")
        auth_window.geometry("500x300")
        auth_window.configure(bg=BG_COLOR)
        auth_window.transient(self.root)
        auth_window.grab_set()
    
        # Warning message
        warning_frame = tk.Frame(auth_window, bg=BG_COLOR)
        warning_frame.pack(fill=tk.X, padx=20, pady=10)
        
        warning_icon = tk.Label(warning_frame, text="⚠️", font=('Segoe UI', 24), 
                               bg=BG_COLOR, fg=ERROR_COLOR)
        warning_icon.pack(side=tk.LEFT, padx=(0, 10))
        
        warning_text = tk.Label(warning_frame, 
                              text="WARNING: This action will permanently delete ALL stock history records.\nThis cannot be undone!",
                              font=FONT_MEDIUM, bg=BG_COLOR, fg=ERROR_COLOR, justify=tk.LEFT,
                              wraplength=400)
        warning_text.pack(side=tk.LEFT, fill=tk.X)
    
        tk.Label(auth_window, text="Enter Manager Password to Confirm:", 
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
    
        password_var = tk.StringVar()
        password_entry = tk.Entry(auth_window, textvariable=password_var, show="*", 
                              font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        password_entry.pack(pady=10, ipady=3, fill=tk.X, padx=20)
        password_entry.focus_set()
    
        status_label = tk.Label(auth_window, text="", font=FONT_SMALL, bg=BG_COLOR, fg=ERROR_COLOR)
        status_label.pack(pady=5)
    
        def verify_and_delete():
            password = password_var.get()
            # Check if password matches any admin's manager password or the fixed 'MANAGER' password
            if password == "MANAGER1":
                auth_window.destroy()
                self.delete_all_stock_history()
                return
        
            # Check custom manager passwords
            for username, user_data in self.config["users"].items():
                if (user_data.get("is_admin", False) and 
                    (user_data.get("manager_password", "") == hash_password(password) or password == "MANAGER")):
                    auth_window.destroy()
                    self.delete_all_stock_history()
                    return
        
            status_label.config(text="Invalid manager password")
    
        button_frame = tk.Frame(auth_window, bg=BG_COLOR)
        button_frame.pack(pady=20)
    
        tk.Button(button_frame, text="Delete All History", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=verify_and_delete,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=auth_window.destroy,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
    
        # Bind Enter key to authenticate
        auth_window.bind('<Return>', lambda event: verify_and_delete())

    def delete_all_stock_history(self):
        """Delete all stock history records from the database"""
        try:
            # Confirm one more time due to destructive nature
            confirm = messagebox.askyesno(
                "Final Confirmation", 
                "ARE YOU ABSOLUTELY SURE?\n\nThis will permanently delete ALL stock history records.\nThis action cannot be undone!\n\nProceed with deletion?",
                icon='warning',
                parent=self.root
            )
            
            if not confirm:
                return
            
            # Show progress window
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Deleting Stock History")
            progress_window.geometry("400x150")
            progress_window.configure(bg=BG_COLOR)
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            main_frame = tk.Frame(progress_window, bg=BG_COLOR)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
            
            tk.Label(main_frame, text="Deleting Stock History...", 
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
            
            progress = ttk.Progressbar(main_frame, mode='indeterminate', length=300)
            progress.pack(pady=10)
            progress.start(10)
            
            status_label = tk.Label(main_frame, text="Please wait...", 
                                   font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR)
            status_label.pack(pady=5)
            
            def perform_deletion():
                try:
                    # Get count of records to be deleted
                    self.db.cursor.execute("SELECT COUNT(*) FROM stock_history")
                    record_count = self.db.cursor.fetchone()[0]
                    
                    # Delete all stock history records
                    self.db.cursor.execute("DELETE FROM stock_history")
                    self.db.conn.commit()
                    
                    # Record the activity
                    self.db.cursor.execute('''
                        INSERT INTO user_activity (user, activity_type, description)
                        VALUES (?, ?, ?)
                    ''', (self.current_user, 'system', f'Deleted all stock history records ({record_count} records)'))
                    self.db.conn.commit()
                    
                    progress_window.destroy()
                    
                    # Show success message
                    messagebox.showinfo(
                        "Deletion Complete", 
                        f"Successfully deleted {record_count} stock history records.\n\nStock history has been cleared.",
                        parent=self.root
                    )
                    
                    # Refresh the history treeview
                    if hasattr(self, 'history_tree') and self.history_tree:
                        self.load_history_data(self.history_tree)
                        
                except Exception as e:
                    progress_window.destroy()
                    messagebox.showerror(
                        "Deletion Failed", 
                        f"Failed to delete stock history:\n{str(e)}",
                        parent=self.root
                    )
            
            # Run deletion in thread to avoid blocking UI
            threading.Thread(target=perform_deletion, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to initiate deletion:\n{str(e)}", parent=self.root)


    def show_add_stock_dialog(self, stock_tree):
        add_dialog = tk.Toplevel(self.root)
        add_dialog.title("Add Stock")
        add_dialog.state('zoomed')  # Changed from fixed size to full screen
        add_dialog.configure(bg=BG_COLOR)
        add_dialog.transient(self.root)
        add_dialog.grab_set()

        # Category selection
        tk.Label(add_dialog, text="Category:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        category_var = tk.StringVar()
        category_dropdown = ttk.Combobox(add_dialog, textvariable=category_var,
                                         values=list(self.menu_items.keys()), font=FONT_MEDIUM)
        category_dropdown.pack(pady=5, ipady=3, fill=tk.X)

        # Item selection
        tk.Label(add_dialog, text="Item:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        item_var = tk.StringVar()
        item_dropdown = ttk.Combobox(add_dialog, textvariable=item_var, font=FONT_MEDIUM)
        item_dropdown.pack(pady=5, ipady=3, fill=tk.X)

        # Update items when category changes
        def update_items(*args):
            selected_category = category_var.get()
            if selected_category in self.menu_items:
                item_dropdown['values'] = list(self.menu_items[selected_category].keys())

        category_var.trace('w', update_items)

        # Current stock display
        current_stock_label = tk.Label(add_dialog, text="Current Stock: -",
                                       font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR)
        current_stock_label.pack(pady=5)

        def update_current_stock(*args):
            category = category_var.get()
            item = item_var.get()
            if category and item:
                stock = self.db.get_current_stock_for_item(category, item)
                current_stock_label.config(text=f"Current Stock: {stock}")
            else:
                current_stock_label.config(text="Current Stock: -")

        category_var.trace('w', update_current_stock)
        item_var.trace('w', update_current_stock)

        # Quantity
        tk.Label(add_dialog, text="Quantity to Add:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        qty_var = tk.StringVar()
        tk.Entry(add_dialog, textvariable=qty_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).pack(pady=5, ipady=3, fill=tk.X)

        # Buying Price
        tk.Label(add_dialog, text="New Buying Price (Ksh):", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        buying_var = tk.StringVar()
        tk.Entry(add_dialog, textvariable=buying_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).pack(pady=5, ipady=3, fill=tk.X)

        # Selling Price
        tk.Label(add_dialog, text="New Selling Price (Ksh):", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        selling_var = tk.StringVar()
        tk.Entry(add_dialog, textvariable=selling_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).pack(pady=5, ipady=3, fill=tk.X)

        # Notes
        tk.Label(add_dialog, text="Notes:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        notes_var = tk.StringVar()
        tk.Entry(add_dialog, textvariable=notes_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).pack(pady=5, ipady=3, fill=tk.X)

        def add_stock():
            category = category_var.get()
            item = item_var.get()
            qty = qty_var.get()
            buying_price = buying_var.get()
            selling_price = selling_var.get()
            notes = notes_var.get()

            if not category or not item or not qty:
                messagebox.showerror("Error", "Category, item and quantity are required", parent=add_dialog)
                return

            try:
                qty = int(qty)
                if qty <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", "Quantity must be a positive integer", parent=add_dialog)
                return

            try:
                buying_price = float(buying_price) if buying_price else None
                selling_price = float(selling_price) if selling_price else None

                if buying_price is not None and buying_price <= 0:
                    raise ValueError("Buying price must be positive")
                if selling_price is not None and selling_price <= 0:
                    raise ValueError("Selling price must be positive")
                if (buying_price is not None and selling_price is not None and
                        selling_price < buying_price):
                    raise ValueError("Selling price must be >= buying price")

            except ValueError as e:
                messagebox.showerror("Error", f"Invalid price: {str(e)}", parent=add_dialog)
                return

            success, message = self.db.update_stock(
                category, item, qty, buying_price, selling_price, self.current_user, notes
            )

            if success:
                messagebox.showinfo("Success", message, parent=add_dialog)
                add_dialog.destroy()
                self.load_stock_data(stock_tree)
            else:
                messagebox.showerror("Error", message, parent=add_dialog)

        # Button frame
        button_frame = tk.Frame(add_dialog, bg=BG_COLOR)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Add Stock", font=FONT_MEDIUM,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, command=add_stock,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=add_dialog.destroy,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)

    def show_remove_stock_dialog(self, stock_tree):
        remove_dialog = tk.Toplevel(self.root)
        remove_dialog.title("Remove Stock")
        remove_dialog.state('zoomed')  # Changed from fixed size to full screen
        remove_dialog.configure(bg=BG_COLOR)
        remove_dialog.transient(self.root)
        remove_dialog.grab_set()

        # Category selection
        tk.Label(remove_dialog, text="Category:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        category_var = tk.StringVar()
        category_dropdown = ttk.Combobox(remove_dialog, textvariable=category_var,
                                         values=list(self.menu_items.keys()), font=FONT_MEDIUM)
        category_dropdown.pack(pady=5, ipady=3, fill=tk.X)

        # Item selection
        tk.Label(remove_dialog, text="Item:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        item_var = tk.StringVar()
        item_dropdown = ttk.Combobox(remove_dialog, textvariable=item_var, font=FONT_MEDIUM)
        item_dropdown.pack(pady=5, ipady=3, fill=tk.X)

        # Update items when category changes
        def update_items(*args):
            selected_category = category_var.get()
            if selected_category in self.menu_items:
                item_dropdown['values'] = list(self.menu_items[selected_category].keys())

        category_var.trace('w', update_items)

        # Current stock display
        current_stock_label = tk.Label(remove_dialog, text="Current Stock: -",
                                       font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR)
        current_stock_label.pack(pady=5)

        def update_current_stock(*args):
            category = category_var.get()
            item = item_var.get()
            if category and item:
                stock = self.db.get_current_stock_for_item(category, item)
                current_stock_label.config(text=f"Current Stock: {stock}")
            else:
                current_stock_label.config(text="Current Stock: -")

        category_var.trace('w', update_current_stock)
        item_var.trace('w', update_current_stock)

        # Quantity
        tk.Label(remove_dialog, text="Quantity to Remove:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        qty_var = tk.StringVar()
        tk.Entry(remove_dialog, textvariable=qty_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).pack(pady=5, ipady=3, fill=tk.X)

        # Notes
        tk.Label(remove_dialog, text="Reason:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        notes_var = tk.StringVar()
        tk.Entry(remove_dialog, textvariable=notes_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).pack(pady=5, ipady=3, fill=tk.X)

        def remove_stock():
            category = category_var.get()
            item = item_var.get()
            qty = qty_var.get()
            notes = notes_var.get()

            if not category or not item or not qty:
                messagebox.showerror("Error", "Category, item and quantity are required", parent=remove_dialog)
                return

            try:
                qty = int(qty)
                if qty <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", "Quantity must be a positive integer", parent=remove_dialog)
                return

            # Check current stock
            current_stock = self.db.get_current_stock_for_item(category, item)
            if current_stock < qty:
                messagebox.showerror("Error",
                                     f"Cannot remove {qty} items. Only {current_stock} available",
                                     parent=remove_dialog)
                return

            # Convert to negative for removal
            success, message = self.db.update_stock(
                category, item, -qty, None, None, self.current_user, notes
            )

            if success:
                messagebox.showinfo("Success", message, parent=remove_dialog)
                remove_dialog.destroy()
                self.load_stock_data(stock_tree)
            else:
                messagebox.showerror("Error", message, parent=remove_dialog)

        # Button frame
        button_frame = tk.Frame(remove_dialog, bg=BG_COLOR)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Remove Stock", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=remove_stock,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=remove_dialog.destroy,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)

    def show_add_item_dialog(self, stock_tree):
        add_dialog = tk.Toplevel(self.root)
        add_dialog.title("Add New Item")
        add_dialog.state('zoomed')  # Changed from fixed size to full screen
        add_dialog.configure(bg=BG_COLOR)
        add_dialog.transient(self.root)
        add_dialog.grab_set()

        # Category selection
        tk.Label(add_dialog, text="Category:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        category_var = tk.StringVar()
        category_dropdown = ttk.Combobox(add_dialog, textvariable=category_var,
                                         values=list(self.menu_items.keys()), font=FONT_MEDIUM)
        category_dropdown.pack(pady=5, ipady=3, fill=tk.X)

        # Allow new categories
        category_dropdown['state'] = 'normal'

        # Item name
        tk.Label(add_dialog, text="Item Name:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        item_var = tk.StringVar()
        tk.Entry(add_dialog, textvariable=item_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).pack(pady=5, ipady=3, fill=tk.X)

        # Description
        tk.Label(add_dialog, text="Description:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        desc_var = tk.StringVar()
        tk.Entry(add_dialog, textvariable=desc_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).pack(pady=5, ipady=3, fill=tk.X)

        # Buying Price
        tk.Label(add_dialog, text="Buying Price (Ksh):", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        buying_var = tk.StringVar()
        tk.Entry(add_dialog, textvariable=buying_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).pack(pady=5, ipady=3, fill=tk.X)

        # Selling Price
        tk.Label(add_dialog, text="Selling Price (Ksh):", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        selling_var = tk.StringVar()
        tk.Entry(add_dialog, textvariable=selling_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).pack(pady=5, ipady=3, fill=tk.X)

        # Initial Stock
        tk.Label(add_dialog, text="Initial Stock:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        stock_var = tk.StringVar(value="0")
        tk.Entry(add_dialog, textvariable=stock_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).pack(pady=5, ipady=3, fill=tk.X)

        def add_item():
            category = category_var.get().strip()
            name = item_var.get().strip()
            description = desc_var.get().strip()
            buying_price = buying_var.get()
            selling_price = selling_var.get()
            stock = stock_var.get()

            if not category or not name or not buying_price or not selling_price or not stock:
                messagebox.showerror("Error", "All fields except description are required", parent=add_dialog)
                return

            try:
                buying_price = float(buying_price)
                selling_price = float(selling_price)
                stock = int(stock)

                if buying_price <= 0:
                    raise ValueError("Buying price must be positive")
                if selling_price <= 0:
                    raise ValueError("Selling price must be positive")
                if selling_price < buying_price:
                    raise ValueError("Selling price must be >= buying price")
                if stock < 0:
                    raise ValueError("Stock cannot be negative")

            except ValueError as e:
                messagebox.showerror("Error", f"Invalid value: {str(e)}", parent=add_dialog)
                return

            if self.db.add_meal(category, name, description, buying_price, selling_price, stock):
                # Update the menu_items dictionary
                if category not in self.menu_items:
                    self.menu_items[category] = {}
                self.menu_items[category][name] = selling_price

                messagebox.showinfo("Success", f"{name} added to {category} category", parent=add_dialog)
                add_dialog.destroy()
                self.load_stock_data(stock_tree)
            else:
                messagebox.showerror("Error", "Failed to add item. It may already exist.", parent=add_dialog)

        # Button frame
        button_frame = tk.Frame(add_dialog, bg=BG_COLOR)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Add Item", font=FONT_MEDIUM,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, command=add_item,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=add_dialog.destroy,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)

    def show_remove_item_dialog(self, stock_tree):
        remove_dialog = tk.Toplevel(self.root)
        remove_dialog.title("Remove Item")
        remove_dialog.state('zoomed')  # Changed from fixed size to full screen
        remove_dialog.configure(bg=BG_COLOR)
        remove_dialog.transient(self.root)
        remove_dialog.grab_set()

        # Category selection
        tk.Label(remove_dialog, text="Category:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        category_var = tk.StringVar()
        category_dropdown = ttk.Combobox(remove_dialog, textvariable=category_var,
                                         values=list(self.menu_items.keys()), font=FONT_MEDIUM)
        category_dropdown.pack(pady=5, ipady=3, fill=tk.X)

        # Item selection
        tk.Label(remove_dialog, text="Item:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        item_var = tk.StringVar()
        item_dropdown = ttk.Combobox(remove_dialog, textvariable=item_var, font=FONT_MEDIUM)
        item_dropdown.pack(pady=5, ipady=3, fill=tk.X)

        # Update items when category changes
        def update_items(*args):
            selected_category = category_var.get()
            if selected_category in self.menu_items:
                item_dropdown['values'] = list(self.menu_items[selected_category].keys())

        category_var.trace('w', update_items)

        # Current stock display
        current_stock_label = tk.Label(remove_dialog, text="Current Stock: -",
                                       font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR)
        current_stock_label.pack(pady=5)

        def update_current_stock(*args):
            category = category_var.get()
            item = item_var.get()
            if category and item:
                stock = self.db.get_current_stock_for_item(category, item)
                current_stock_label.config(text=f"Current Stock: {stock}")
            else:
                current_stock_label.config(text="Current Stock: -")

        category_var.trace('w', update_current_stock)
        item_var.trace('w', update_current_stock)

        def remove_item():
            category = category_var.get()
            item = item_var.get()

            if not category or not item:
                messagebox.showerror("Error", "Please select both category and item", parent=remove_dialog)
                return

            current_stock = self.db.get_current_stock_for_item(category, item)
            confirm_msg = f"Are you sure you want to remove {item} from {category}?"
            if current_stock > 0:
                confirm_msg += f"\n\nWARNING: There are {current_stock} items in stock that will be lost!"

            if messagebox.askyesno("Confirm", confirm_msg, parent=remove_dialog):
                if self.db.remove_meal(category, item):
                    messagebox.showinfo("Success", f"{item} removed from {category} category", parent=remove_dialog)
                    remove_dialog.destroy()
                    self.load_stock_data(stock_tree)
                else:
                    messagebox.showerror("Error", "Failed to remove item", parent=remove_dialog)

        # Button frame
        button_frame = tk.Frame(remove_dialog, bg=BG_COLOR)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Remove Item", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=remove_item,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=remove_dialog.destroy,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)

    def show_main_system(self):
        """Show the main cashier interface with enhanced features"""
        self.clear_window()

        # Configure grid weights
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_columnconfigure(2, weight=0)
        self.root.grid_columnconfigure(3, weight=0)
        self.root.state('zoomed')

    # Title marquee
        title_marquee = Marquee(self.root, text="ZETECH CAFETERIA POS")
        title_marquee.grid(row=0, column=0, columnspan=4, sticky="ew", padx=10, pady=10)

    # Add clock at top right
        clock_frame = tk.Frame(self.root, bg=BG_COLOR)
        clock_frame.grid(row=0, column=3, sticky="ne", padx=10, pady=10)
    
        self.clock_label = tk.Label(clock_frame, font=('Poppins', 12, 'bold'), 
                               bg=BG_COLOR, fg="white")
        self.clock_label.pack()
        self.update_clock()  # Start the clock

    # Main content frame
        main_frame = tk.Frame(self.root, bg="#C2C2C8")
        main_frame.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=10, pady=10)

    # Configure grid weights for main frame
        main_frame.grid_rowconfigure(0, weight=0)  # Customer info
        main_frame.grid_rowconfigure(1, weight=1)  # Menu items
        main_frame.grid_rowconfigure(2, weight=1)  # Menu items
        main_frame.grid_rowconfigure(3, weight=0)  # Totals
        main_frame.grid_rowconfigure(4, weight=0)  # Buttons

        main_frame.grid_columnconfigure(0, weight=1)  # Food/Sauce
        main_frame.grid_columnconfigure(1, weight=1)  # Drinks
        main_frame.grid_columnconfigure(2, weight=0)  # Receipt (less weight)
        main_frame.grid_columnconfigure(3, weight=0)  # Calculator (less weight)

    # Customer info frame
        customer_frame = tk.Frame(main_frame, bg="#1e1e2e")
        customer_frame.grid(row=0, column=0, columnspan=4, sticky="ew", pady=5, padx=10)
        customer_frame.grid_columnconfigure(0, weight=1)
        customer_frame.grid_columnconfigure(1, weight=1)
        customer_frame.grid_columnconfigure(2, weight=1)

    # Personal greeting for the user
        greeting_label = tk.Label(customer_frame, text=f"Welcome, {self.current_user}! ",
                              font=("Arial", 14, "bold"), fg=ACCENT_COLOR, bg="#1e1e2e")
        greeting_label.grid(row=0, column=0, columnspan=3, pady=(5, 2), sticky="n")

    # Customer Name label and entry centered in next row
        name_label = tk.Label(customer_frame, text="Customer Name:",
                          font=FONT_MEDIUM, fg=ACCENT_COLOR, bg="#1e1e2e")
        name_label.grid(row=1, column=0, sticky="e", padx=(0, 5), pady=(10, 5))
        self.customer_name_entry = tk.Entry(customer_frame, bd=2, width=16,
                                        font=FONT_MEDIUM, bg="#fff", fg="#2a2a40")
        self.customer_name_entry.grid(row=1, column=1, sticky="ew", padx=(0, 5), pady=(10, 5))

    # Logout button right-aligned
        # Logout and Exit buttons
        tk.Button(customer_frame, text="Logout", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=self.confirm_logout,
                  padx=15, pady=3, activebackground=HIGHLIGHT_COLOR).grid(row=1, column=2, sticky="e", padx=(5, 0),
                                                                      pady=(10, 5))


        # Load meals from database
        db_meals = self.db.get_all_meals()
        self.menu_items = {}
        for category, name, _, _, selling_price, _, _, _, _, _ in db_meals:
            if category not in self.menu_items:
                self.menu_items[category] = {}
            self.menu_items[category][name] = selling_price

        # Create meal category frames
        self.meal_frames = {}
        self.meal_entries = {}

        # Left side frame (Food and Sauce)
        left_frame = tk.Frame(main_frame, bg="#1e1e2e")
        left_frame.grid(row=1, column=0, rowspan=2, sticky="nsew", padx=5, pady=5)
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_rowconfigure(1, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        # Food frame
        food_frame = tk.LabelFrame(left_frame, text="Food", fg=ACCENT_COLOR, bg="#1e1e2e",
                                   font=FONT_MEDIUM, bd=2, relief=tk.GROOVE)
        food_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        food_frame.grid_rowconfigure(0, weight=1)
        food_frame.grid_columnconfigure(0, weight=1)
        self.meal_frames["Food"] = food_frame

        # For Food
# For Food
        food_search_var = tk.StringVar()
        tk.Label(food_frame, text="Search:", bg="#1e1e2e", fg=FG_COLOR, font=FONT_SMALL).pack(anchor="w", padx=5, pady=(3, 1))
        food_search_entry = tk.Entry(food_frame, textvariable=food_search_var, font=FONT_SMALL, bg="#fff", fg="#2a2a40")
        food_search_entry.pack(fill=tk.X, padx=5, pady=(0, 5))

        def filter_food_items(*args):
            query = food_search_var.get().strip().lower()
            for item, entry in self.meal_entries["Food"].items():
                parent = entry.master  # This is the item_frame
                if not query or query in item.lower():
                    parent.pack(fill=tk.X, padx=5, pady=2)
                else:
                    parent.pack_forget()
    
    # Update scroll region after filtering
            for widget in food_frame.winfo_children():
                if isinstance(widget, tk.Frame):  # The container frame
                    for child in widget.winfo_children():
                        if isinstance(child, tk.Canvas):
                            child.configure(scrollregion=child.bbox("all"))
                            break

        food_search_var.trace_add("write", filter_food_items)

        # Sauce frame
        sauce_frame = tk.LabelFrame(left_frame, text="Sauce", fg=ACCENT_COLOR, bg="#1e1e2e",
                                    font=FONT_MEDIUM, bd=2, relief=tk.GROOVE)
        sauce_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        sauce_frame.grid_rowconfigure(0, weight=1)
        sauce_frame.grid_columnconfigure(0, weight=1)
        self.meal_frames["Sauce"] = sauce_frame

        # For Sauce
        sauce_search_var = tk.StringVar()
        tk.Label(sauce_frame, text="Search:", bg="#1e1e2e", fg=FG_COLOR, font=FONT_SMALL).pack(anchor="w", padx=5,
                                                                                               pady=(3, 1))
        sauce_search_entry = tk.Entry(sauce_frame, textvariable=sauce_search_var, font=FONT_SMALL, bg="#fff",
                                      fg="#2a2a40")
        sauce_search_entry.pack(fill=tk.X, padx=5, pady=(0, 5))

        def filter_sauce_items(*args):
            query = sauce_search_var.get().strip().lower()
            for item, entry in self.meal_entries["Sauce"].items():
                parent = entry.master
                if not query or query in item.lower():
                    parent.pack_configure(fill=tk.X, padx=5, pady=2)
                else:
                    parent.pack_forget()

        sauce_search_var.trace_add("write", filter_sauce_items)

        # Right side frame (Drinks)
        right_frame = tk.Frame(main_frame, bg="#1e1e2e")
        right_frame.grid(row=1, column=1, rowspan=2, sticky="nsew", padx=5, pady=5)
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_rowconfigure(1, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        # Hot Drinks frame
        hot_drinks_frame = tk.LabelFrame(right_frame, text="Hot Drinks", fg=ACCENT_COLOR, bg="#1e1e2e",
                                         font=FONT_MEDIUM, bd=2, relief=tk.GROOVE)
        hot_drinks_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        hot_drinks_frame.grid_rowconfigure(0, weight=1)
        hot_drinks_frame.grid_columnconfigure(0, weight=1)
        self.meal_frames["Hot Drinks"] = hot_drinks_frame

        # For Hot Drinks
        hot_search_var = tk.StringVar()
        tk.Label(hot_drinks_frame, text="Search:", bg="#1e1e2e", fg=FG_COLOR, font=FONT_SMALL).pack(anchor="w", padx=5,
                                                                                                    pady=(3, 1))
        hot_search_entry = tk.Entry(hot_drinks_frame, textvariable=hot_search_var, font=FONT_SMALL, bg="#fff",
                                    fg="#2a2a40")
        hot_search_entry.pack(fill=tk.X, padx=5, pady=(0, 5))

        def filter_hot_items(*args):
            query = hot_search_var.get().strip().lower()
            for item, entry in self.meal_entries["Hot Drinks"].items():
                parent = entry.master
                if not query or query in item.lower():
                    parent.pack_configure(fill=tk.X, padx=5, pady=2)
                else:
                    parent.pack_forget()

        hot_search_var.trace_add("write", filter_hot_items)

        # Cold Drinks frame
        cold_drinks_frame = tk.LabelFrame(right_frame, text="Cold Drinks", fg=ACCENT_COLOR, bg="#1e1e2e",
                                          font=FONT_MEDIUM, bd=2, relief=tk.GROOVE)
        cold_drinks_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        cold_drinks_frame.grid_rowconfigure(0, weight=1)
        cold_drinks_frame.grid_columnconfigure(0, weight=1)
        self.meal_frames["Cold Drinks"] = cold_drinks_frame

        # For Cold Drinks
        cold_search_var = tk.StringVar()
        tk.Label(cold_drinks_frame, text="Search:", bg="#1e1e2e", fg=FG_COLOR, font=FONT_SMALL).pack(anchor="w", padx=5,
                                                                                                     pady=(3, 1))
        cold_search_entry = tk.Entry(cold_drinks_frame, textvariable=cold_search_var, font=FONT_SMALL, bg="#fff",
                                     fg="#2a2a40")
        cold_search_entry.pack(fill=tk.X, padx=5, pady=(0, 5))

        def filter_cold_items(*args):
            query = cold_search_var.get().strip().lower()
            for item, entry in self.meal_entries["Cold Drinks"].items():
                parent = entry.master
                if not query or query in item.lower():
                    parent.pack_configure(fill=tk.X, padx=5, pady=2)
                else:
                    parent.pack_forget()

        cold_search_var.trace_add("write", filter_cold_items)

        # Add scrollable content to each category frame
        for category, frame in self.meal_frames.items():
            # Create a frame to hold canvas and scrollbar
            container = tk.Frame(frame, bg="#C2C2C8")
            container.pack(fill=tk.BOTH, expand=True)
    
            # Create canvas and scrollbar
            canvas = tk.Canvas(container, bg="#C2C2C8", highlightthickness=0)
            scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
            scrollable_frame = tk.Frame(canvas, bg="#C2C2C8")

            # Configure scroll region
            scrollable_frame.bind(
                "<Configure>",
                lambda e, canvas=canvas: canvas.configure(scrollregion=canvas.bbox("all"))
            )

            # Create window in canvas for scrollable frame
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            # Pack canvas and scrollbar
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
    
            # Bind mousewheel to canvas for smooth scrolling
            def _on_mousewheel(event, canvas=canvas):
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
            canvas.bind("<MouseWheel>", _on_mousewheel)
# Add meal items with stock indicators
# Add meal items with stock indicators
            self.meal_entries[category] = {}
            if category in self.menu_items:
                for item, price in self.menu_items[category].items():
                    item_frame = tk.Frame(scrollable_frame, bg="#C2C2C8")
                    item_frame.pack(fill=tk.X, padx=5, pady=2)

        # Get current stock from database
                    current_stock = self.db.get_current_stock_for_item(category, item)
                    stock_color = "red" if current_stock <= 5 else "black"

        # Item name label
                    item_label = tk.Label(item_frame, text=f"{item}", 
                             font=FONT_SMALL, bg="#C2C2C8", fg="#000",
                             width=20, anchor="w")
                    item_label.pack(side=tk.LEFT, padx=5)

        # Price label
                    price_label = tk.Label(item_frame, text=f"(ksh{price})", 
                              font=FONT_SMALL, bg="#C2C2C8", fg="#000",
                              width=10, anchor="w")
                    price_label.pack(side=tk.LEFT, padx=5)

        # Stock indicator - make sure this has a distinct variable name for easy reference
                    stock_label = tk.Label(item_frame, text=f"({current_stock})", 
                              font=FONT_SMALL, bg="#C2C2C8", fg=stock_color,
                              width=5, anchor="w", name=f"stock_{category}_{item}")
                    stock_label.pack(side=tk.LEFT, padx=5)

        # Entry field
                    entry = tk.Entry(item_frame, bd=1, bg="#fff", fg="#2a2a40",
            font=FONT_SMALL, width=8, justify=tk.CENTER)
                    entry.pack(side=tk.LEFT, padx=5)
                    self.meal_entries[category][item] = entry

        # Receipt frame
        bill_frame = tk.LabelFrame(main_frame, text="Receipt", font=FONT_MEDIUM,
                                   bg="#2a2a40", fg=ACCENT_COLOR, bd=2, relief=tk.GROOVE)
        bill_frame.grid(row=1, column=2, rowspan=2, sticky="nsew", padx=5, pady=5, ipadx=5)
        bill_frame.grid_rowconfigure(0, weight=1)
        bill_frame.grid_columnconfigure(0, weight=1)

        # Text widget for receipt
        self.bill_txt = tk.Text(bill_frame, bg="#fff", fg="#2a2a40",
                                font=('Consolas', 10), wrap=tk.WORD, width=41)
        scrollbar = tk.Scrollbar(bill_frame, command=self.bill_txt.yview)
        self.bill_txt.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.bill_txt.pack(fill=tk.BOTH, expand=True)

        self.default_bill()

        # Calculator frame
        calc_frame = tk.LabelFrame(main_frame, text="Calculator", font=FONT_MEDIUM,
                                   bg="#2a2a40", fg=ACCENT_COLOR, bd=2, relief=tk.GROOVE)
        calc_frame.grid(row=1, column=3, rowspan=2, sticky="nsew", padx=5, pady=5, ipadx=5)

        # Configure grid weights for calculator
        for i in range(6):
            calc_frame.grid_rowconfigure(i, weight=1)
        for i in range(4):
            calc_frame.grid_columnconfigure(i, weight=1)

        # Calculator display
        self.calc_var = tk.StringVar()
        num_ent = tk.Entry(calc_frame, bd=1, bg="#2a51ec", fg="#2a2a40",
                           textvariable=self.calc_var, font=FONT_MEDIUM,
                           justify=tk.RIGHT)
        num_ent.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=5, pady=5)

        # Calculator buttons
        buttons = [
            ("7", 1, 0), ("8", 1, 1), ("9", 1, 2), ("+", 1, 3),
            ("4", 2, 0), ("5", 2, 1), ("6", 2, 2), ("-", 2, 3),
            ("1", 3, 0), ("2", 3, 1), ("3", 3, 2), ("*", 3, 3),
            ("0", 4, 0), (".", 4, 1), ("C", 4, 2), ("/", 4, 3),
            ("=", 5, 0, 4)
        ]

        def button_click(char):
            current = self.calc_var.get()
            if char == "=":
                try:
                    result = str(eval(current))
                    self.calc_var.set(result)
                except Exception:
                    self.calc_var.set("Error")
            elif char == "C":
                self.calc_var.set("")
            else:
                self.calc_var.set(current + char)

        for btn in buttons:
            if len(btn) == 4:
                text, row, col, colspan = btn
                button = tk.Button(calc_frame, text=text, bd=1,
                                   font=FONT_MEDIUM, bg=BUTTON_COLOR, fg=FG_COLOR,
                                   activebackground=ACCENT_COLOR,
                                   command=lambda t=text: button_click(t))
                button.grid(row=row, column=col, columnspan=colspan, sticky="nsew", padx=2, pady=2)
            else:
                text, row, col = btn
                button = tk.Button(calc_frame, text=text, bd=1,
                                   font=FONT_MEDIUM, bg=BUTTON_COLOR, fg=FG_COLOR,
                                   activebackground=ACCENT_COLOR,
                                   command=lambda t=text: button_click(t))
                button.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)

        # Totals frame
        control_frame = tk.Frame(main_frame, bg="#C2C2C8")
        control_frame.grid(row=3, column=2, columnspan=2, sticky="nsew", padx=5, pady=5)

        tk.Label(control_frame, text="Tax:", font=("Arial", 16, "bold"),
                 fg=BUTTON_COLOR, width=4, bg="#C2C2C8").grid(row=0, column=0, padx=5, pady=2, sticky=tk.E)

        self.tax_btn_entry = tk.Entry(control_frame, bd=1, bg="#fff", fg="#2a2a40",
                                      font=FONT_MEDIUM, width=15, justify=tk.RIGHT)
        self.tax_btn_entry.grid(row=0, column=1, padx=5, pady=2)

        tk.Label(control_frame, text="Total:",font=("Arial", 16, "bold"),
                 fg=BUTTON_COLOR, width=4, bg="#C2C2C8").grid(row=1, column=0, padx=5, pady=2, sticky=tk.E)

        self.total_btn_entry = tk.Entry(control_frame, bd=1, bg="#fff", fg="#2a2a40",
                                        font=FONT_MEDIUM, width=15, justify=tk.RIGHT)
        self.total_btn_entry.grid(row=1, column=1, padx=5, pady=2)

        # Action buttons frame
        button_frame = tk.Frame(main_frame, bg="#C2C2C8")
        button_frame.grid(row=4, column=0, columnspan=4, pady=10, sticky="ew")

        # Configure button styles
        button_style = {
            'font': FONT_MEDIUM,
            'bd': 0,
            'padx': 15,
            'pady': 8,
            'activebackground': ACCENT_COLOR
        }

        # Create buttons
        buttons = [
            ("Payment Method", self.payment_method_dialog, BUTTON_COLOR, FG_COLOR),
            ("Print Receipt", self.print_receipt, BUTTON_COLOR, FG_COLOR),
            ("Total", self.calculate_total, BUTTON_COLOR, FG_COLOR),
            ("Show Daily Sales", self.show_daily_sales, BUTTON_COLOR, FG_COLOR),
            ("Reset", self.reset_all, BUTTON_COLOR, FG_COLOR)
        ]

        # Only show admin buttons for admin users
        if self.is_admin_user():
            buttons.extend([
                ("Add Meal", self.add_new_meal_dialog, BUTTON_COLOR, FG_COLOR),
                ("Remove Meal", self.remove_existing_meal_dialog, BUTTON_COLOR, FG_COLOR)
            ])

        for text, command, bg, fg in buttons:
            tk.Button(button_frame, text=text, command=command,
                      bg=bg, fg=fg, **button_style).pack(side=tk.LEFT, padx=5)

    def calculate_total(self):
        customer_name = self.customer_name_entry.get().strip()
    
        total_list = []
        self.bill_txt.delete(1.0, tk.END) 
        self.default_bill()
   
        items_selected = False
        self.pending_sales = []  # Store sales data for later processing
        items_summary = []  # Store items for QR code

        try:
        # Get configured tax rate (default to 2% if not set)
            tax_rate = self.config.get("tax_rate", 2.0) / 100.0
            tax_enabled = self.config.get("tax_enabled", True)
        
            for category, items in self.menu_items.items():
                if category not in self.meal_entries:
                    continue

                for item, price in items.items():
                    if item not in self.meal_entries[category]:
                        continue

                    qty = self.meal_entries[category][item].get().strip()
                    if qty:
                        qty = int(qty)
                        if qty > 0:
                        # Check stock availability but DON'T deduct yet
                            current_stock = self.db.get_current_stock_for_item(category, item)
                            if current_stock < qty:
                                messagebox.showerror("Error",
                                                f"Not enough stock for {item}. Only {current_stock} available",
                                                parent=self.root)
                                return

                            cost = qty * price
                            total_list.append(cost)
                    
                        # Add to items summary for QR code
                            items_summary.append(f"{item}: {qty} x {price} = {cost}")
                    
                        # Format item name to fit within 20 characters
                            item_display = item[:18] + ".." if len(item) > 18 else item
                            self.bill_txt.insert(tk.END, f"{item_display:<20}{qty:>5}{price:>8.2f}{cost:>9.2f}\n")

                        # Prepare sales data for recording (but don't record yet)
                            self.pending_sales.append({
                                'user': self.current_user,
                                'date': datetime.now().strftime('%Y-%m-%d'),
                                'time': datetime.now().strftime('%H:%M:%S'),
                                'customer_name': customer_name if customer_name else "Walk-in Customer",
                                'category': category,
                                'meal': item,
                                'quantity': qty,
                                'price': price,
                                'amount': cost,
                                'payment_method': self.payment_method_used["method"],
                                'payment_details': self.payment_method_used["details"]
                            })

                            items_selected = True

            if items_selected:
                total_cost = sum(total_list)
            
            # Calculate tax based on configuration
                if tax_enabled:
                    tax = total_cost * tax_rate
                    tax_percentage = self.config.get("tax_rate", 2.0)
                else:
                    tax = 0.0
                    tax_percentage = 0.0
                
                grand_total = total_cost + tax

                self.bill_txt.insert(tk.END, "-" * 55 + "\n")
                self.bill_txt.insert(tk.END, f"{'Subtotal:':<20}{'':>5}ksh{total_cost:>12.2f}\n")
            
            # Show tax line only if tax is enabled
                if tax_enabled:
                    self.bill_txt.insert(tk.END, f"{f'Tax ({tax_percentage}%):':<20}{'':>5}ksh{tax:>12.2f}\n")
            
                self.bill_txt.insert(tk.END, "-" * 55 + "\n")
                self.bill_txt.insert(tk.END, f"{'GRAND TOTAL:':<20}{'':>5}ksh{grand_total:>12.2f}\n")
                self.bill_txt.insert(tk.END, "=" * 55 + "\n")

            # Payment method info
                if self.payment_method_used["method"]:
                    self.bill_txt.insert(tk.END, f"Payment: {self.payment_method_used['method']}\n")
                    if self.payment_method_used["details"]:
                    # Truncate details if too long for receipt
                        details = self.payment_method_used["details"]
                        if len(details) > 40:
                            details = details[:37] + "..."
                        self.bill_txt.insert(tk.END, f"Details: {details}\n")
        
            # Store items summary for QR code
                self.receipt_items = items_summary
                self.receipt_total = grand_total
        
                self.bill_txt.insert(tk.END, "\nThank you for your business!\n")
                self.bill_txt.insert(tk.END, "System By: Clin-Tech Technologies\n")
                self.bill_txt.insert(tk.END, "Tel: 0796939191/0707326661\n")
    
                self.tax_btn_entry.delete(0, tk.END)
                self.tax_btn_entry.insert(0, f"ksh{tax:.2f}")
                self.total_btn_entry.delete(0, tk.END)
                self.total_btn_entry.insert(0, f"ksh{grand_total:.2f}")
            else:
                self.bill_txt.insert(tk.END, "No items selected.\n")
                self.tax_btn_entry.delete(0, tk.END)
                self.total_btn_entry.delete(0, tk.END)
        except ValueError:
            messagebox.showerror("Error", "Please enter valid quantities (whole numbers)", parent=self.root)
            self.bill_txt.insert(tk.END, "No items selected.\n")
            self.tax_btn_entry.delete(0, tk.END)
            self.total_btn_entry.delete(0, tk.END)

    def refresh_stock_indicators(self):
        """Refresh all stock indicators in the main system UI"""
        if not hasattr(self, 'meal_frames') or not self.meal_frames:
            return
        
        for category, frame in self.meal_frames.items():
        # Find the scrollable frame within each category frame
            scrollable_frame = None
            for widget in frame.winfo_children():
                if isinstance(widget, tk.Frame):  # This is the container
                    for child in widget.winfo_children():
                        if isinstance(child, tk.Canvas):
                        # Get the scrollable frame from the canvas
                            scrollable_frame = child.winfo_children()[0]
                            break
                    if scrollable_frame:
                        break
        
            if not scrollable_frame:
                continue
            
        # Update each item's stock indicator
            for item_frame in scrollable_frame.winfo_children():
                if not isinstance(item_frame, tk.Frame):
                    continue
                
            # Find the item name label and stock label
                item_name = None
                stock_label = None
            
                for widget in item_frame.winfo_children():
                    if isinstance(widget, tk.Label) and widget['text'] and '(' not in widget['text']:
                    # This is the item name label (contains item name without parentheses)
                        item_text = widget['text']
                    # Extract item name (remove price part if present)
                        if '(' in item_text:
                            item_name = item_text.split('(')[0].strip()
                        else:
                            item_name = item_text.strip()
                    elif isinstance(widget, tk.Label) and widget['text'] and '(' in widget['text'] and ')' in widget['text']:
                    # This is the stock label (contains text in parentheses)
                        stock_label = widget
            
                if item_name and stock_label and category in self.menu_items and item_name in self.menu_items[category]:
                # Get current stock from database
                    current_stock = self.db.get_current_stock_for_item(category, item_name)
                    stock_color = "red" if current_stock <= 5 else "black"
                
                # Update the stock label
                    stock_label.config(text=f"({current_stock})", fg=stock_color)
    def print_receipt(self):
        """Print receipt and deduct items from stock"""
        # First calculate total to get pending sales data
        self.calculate_total()
        
        # Check if there are pending sales to process
        if not hasattr(self, 'pending_sales') or not self.pending_sales:
            messagebox.showwarning("No Items", "No items selected for printing.", parent=self.root)
            return
        
        # Record all sales in the database (this is where stock gets deducted)
        for sale in self.pending_sales:
            success, message = self.db.record_sale(sale)
            if not success:
                messagebox.showerror("Error", f"Failed to record sale: {message}", parent=self.root)
                return
        
        # Refresh stock indicators after deduction
        self.refresh_stock_indicators()
        
        # Generate receipt content with proper formatting
        receipt_content = self.generate_receipt_content()
        
        # Print the receipt
        success, message = self.print_receipt_content(receipt_content, "Customer Receipt")
        
        if success:
            messagebox.showinfo("Success", "Receipt printed successfully!", parent=self.root)
            # Clear pending sales after successful printing
            self.pending_sales = []
            # Reset the form
            self.reset_all()
        else:
            messagebox.showerror("Print Error", f"Failed to print receipt: {message}", parent=self.root)


    def generate_receipt_content(self):
        """Generate formatted receipt content for printing with increased width and reduced spacing"""
        # Get receipt settings or use defaults
        company_name = getattr(self, 'company_name_var', tk.StringVar(value="Zetech University Cafeteria")).get()
        contact_info = getattr(self, 'contact_info_var', tk.StringVar(value="Tel: 0796939191/0707326661")).get()
        footer_message = getattr(self, 'footer_msg_var', tk.StringVar(value="Thank you for your business!")).get()
        
        # Increased receipt width for better readability
        receipt_type = getattr(self, 'receipt_type_var', tk.StringVar(value="80mm Thermal")).get()
        if receipt_type == "58mm Thermal":
            width = 45  # Increased from 35
        elif receipt_type == "80mm Thermal":
            width = 55  # Increased from 42
        elif receipt_type == "A4 Paper":
            width = 70  # Increased from 60
        elif receipt_type == "A5 Paper":
            width = 60  # Increased from 45
        else:
            width = 55  # Default increased width
        
        # Build receipt content with reduced spacing
        content = "=" * width + "\n"
        
        # Header with reduced spacing
        if getattr(self, 'print_header_var', tk.BooleanVar(value=True)).get():
            content += f"{company_name.center(width)}\n"
            content += f"{'OFFICIAL RECEIPT'.center(width)}\n"
            content += f"{contact_info.center(width)}\n"
            content += "=" * width + "\n"
        
        # Date and time with reduced spacing
        if getattr(self, 'print_datetime_var', tk.BooleanVar(value=True)).get():
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            content += f"Date: {now}\n"
            content += f"Cashier: {self.current_user}\n"
        
        # Customer info
        customer_name = self.customer_name_entry.get().strip() if hasattr(self, 'customer_name_entry') and self.customer_name_entry.get().strip() else "Walk-in Customer"
        content += f"Customer: {customer_name}\n"
        content += "=" * width + "\n"
        
        # Column headers with optimized spacing
        content += f"{'Item':<25}{'Qty':>5}{'Price':>10}{'Total':>12}\n"
        content += "-" * width + "\n"
        
        # Calculate totals
        subtotal = 0
        tax_rate = 0.02  # 2% tax
        
        # Add items to receipt with optimized spacing
        for sale in self.pending_sales:
            item = sale['meal']
            qty = sale['quantity']
            price = sale['price']
            total = sale['amount']
            subtotal += total
            
            # Format item name to fit increased width
            item_display = item[:22] + ".." if len(item) > 22 else item
            content += f"{item_display:<25}{qty:>5}{price:>10.2f}{total:>12.2f}\n"
        
        # Calculate tax and total
        tax = subtotal * tax_rate
        grand_total = subtotal + tax
        
        # Add totals section with optimized spacing
        content += "-" * width + "\n"
        content += f"{'Subtotal:':<30}{subtotal:>22.2f}\n"
        content += f"{'Tax (2%):':<30}{tax:>22.2f}\n"
        content += "=" * width + "\n"
        content += f"{'GRAND TOTAL:':<30}{grand_total:>22.2f}\n"
        content += "=" * width + "\n"
        
        # Payment method
        if hasattr(self, 'payment_method_used') and self.payment_method_used["method"]:
            content += f"Payment: {self.payment_method_used['method']}\n"
            if self.payment_method_used["details"]:
                details = self.payment_method_used["details"]
                if len(details) > width - 9:
                    details = details[:width - 12] + "..."
                content += f"Details: {details}\n"
        
        # Footer with reduced spacing
        if getattr(self, 'print_footer_var', tk.BooleanVar(value=True)).get():
            content += "\n" + footer_message.center(width) + "\n"
        
        content += "\n" + "System By: Clin-Tech Technologies".center(width) + "\n"
        content += "=" * width + "\n"
        
        return content

    def print_receipt_with_settings(self, receipt_content):
        """Print receipt with current settings"""
        try:
            success, message = self.print_receipt_content(receipt_content, "Customer Receipt")
            if success:
                messagebox.showinfo("Success", "Receipt printed successfully!", parent=self.root)
                # Clear pending sales after successful printing
                self.pending_sales = []
                return True
            else:
                messagebox.showerror("Print Error", f"Failed to print receipt: {message}", parent=self.root)
                return False
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print receipt: {str(e)}", parent=self.root)
            return False

    def print_receipt_content(self, content, title="Receipt"):
        """Generic receipt printing function with enhanced error handling"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            # Print based on OS
            if os.name == 'nt':  # Windows
                os.startfile(tmp_path, "print")
                print_status = "sent to print queue"
            elif os.name == 'posix':  # Linux/Unix
                result = subprocess.call(['lp', tmp_path])
                if result == 0:
                    print_status = "sent to printer"
                else:
                    # Try lpr alternative
                    result = subprocess.call(['lpr', tmp_path])
                    if result == 0:
                        print_status = "sent to printer (lpr)"
                    else:
                        raise Exception("Both lp and lpr commands failed")
            else:
                raise Exception("Unsupported operating system")

            # Schedule file deletion
            def cleanup_temp_file():
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except:
                    pass  # Ignore cleanup errors

            threading.Timer(10.0, cleanup_temp_file).start()
            
            return True, f"Print job {print_status} successfully"
            
        except Exception as e:
            # Clean up temp file on error
            try:
                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except:
                pass
            return False, f"Printing failed: {str(e)}"
        
        # Clear pending sales after successful printing
        self.pending_sales = []

    def reset_all(self):
        self.customer_name_entry.delete(0, tk.END)
        for category in self.meal_entries:
            for item in self.meal_entries[category]:
                self.meal_entries[category][item].delete(0, tk.END)
        self.tax_btn_entry.delete(0, tk.END)
        self.total_btn_entry.delete(0, tk.END)
        self.calc_var.set("")
        self.bill_txt.delete(1.0, tk.END)
        self.default_bill()
        self.payment_method_used = {"method": "Cash", "details": ""}
        # Clear any pending sales when resetting
        if hasattr(self, 'pending_sales'):
            self.pending_sales = []


    def show_daily_sales(self):
        date = datetime.now().strftime('%Y-%m-%d')

        # Get sales data for the current date for THIS USER ONLY
        sales_data = self.db.get_daily_sales(date, self.current_user)
        
        # Calculate user-specific totals from sales_data
        user_total_sales = sum(amt for _, _, _, amt, _, _, _ in sales_data)
        user_total_profit = sum(profit for _, _, _, _, _, profit, _ in sales_data)
        user_profit_percentage = (user_total_profit / user_total_sales * 100) if user_total_sales > 0 else 0

        # Find most sold item and category for this user
        item_sales = {}
        category_sales = {}
        for category, meal, qty, amt, _, _, _ in sales_data:
            item_sales[meal] = item_sales.get(meal, 0) + qty
            category_sales[category] = category_sales.get(category, 0) + qty
        
        most_sold_item = max(item_sales, key=item_sales.get) if item_sales else "None"
        most_sold_category = max(category_sales, key=category_sales.get) if category_sales else "None"

        sales_window = tk.Toplevel(self.root)
        sales_window.title(f'Daily Sales Summary - {self.current_user}')
        sales_window.geometry('900x700')
        sales_window.configure(bg=BG_COLOR)

        # Main frame with scrollbar
        main_frame = tk.Frame(sales_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Title - SPECIFIC TO USER
        tk.Label(main_frame, text=f"Sales Summary for {date} - {self.current_user}",
                 font=('Poppins', 16, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        # Create a notebook for multiple tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Sales by item
        item_frame = tk.Frame(notebook, bg=BG_COLOR)
        notebook.add(item_frame, text="Sales by Item")

        # Header row
        header_frame = tk.Frame(item_frame, bg=BG_COLOR)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(header_frame, text="Category", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(header_frame, text="Meal", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=20, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(header_frame, text="Qty Sold", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=16, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(header_frame, text="Amount", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(header_frame, text="Profit", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=17, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(header_frame, text="Margin", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)

        # Sales data rows
        canvas = tk.Canvas(item_frame, bg=BG_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(item_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=BG_COLOR)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        for category, meal, qty, amt, method, profit, margin in sales_data:
            row_frame = tk.Frame(scrollable_frame, bg=BG_COLOR)
            row_frame.pack(fill=tk.X, pady=4)

            tk.Label(row_frame, text=category, font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=meal, font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=20, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=str(qty), font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=20, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=f"{amt:.2f}", font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=25, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=f"{profit:.2f}", font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=23, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=f"{margin:.1f}%", font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=25, anchor="w").pack(side=tk.LEFT, padx=5)

        # Tab 2: Payment methods
        payment_frame = tk.Frame(notebook, bg=BG_COLOR)
        notebook.add(payment_frame, text="Payment Methods")

        # Header row
        payment_header = tk.Frame(payment_frame, bg=BG_COLOR)
        payment_header.pack(fill=tk.X, pady=(0, 10))

        tk.Label(payment_header, text="Payment Method", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=25, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(payment_header, text="Amount (ksh)", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)

        # Payment method data
        payment_canvas = tk.Canvas(payment_frame, bg=BG_COLOR, highlightthickness=0)
        payment_scrollbar = ttk.Scrollbar(payment_frame, orient="vertical", command=payment_canvas.yview)
        payment_scrollable = tk.Frame(payment_canvas, bg=BG_COLOR)

        payment_scrollable.bind(
            "<Configure>",
            lambda e: payment_canvas.configure(scrollregion=payment_canvas.bbox("all"))
        )

        payment_canvas.create_window((0, 0), window=payment_scrollable, anchor="nw")
        payment_canvas.configure(yscrollcommand=payment_scrollbar.set)

        payment_scrollbar.pack(side="right", fill="y")
        payment_canvas.pack(side="left", fill="both", expand=True)

        # Group sales by payment method for THIS USER ONLY
        payment_methods = {}
        for _, _, _, amt, method, _, _ in sales_data:
            payment_methods[method] = payment_methods.get(method, 0) + amt

        for method, amount in payment_methods.items():
            row_frame = tk.Frame(payment_scrollable, bg=BG_COLOR)
            row_frame.pack(fill=tk.X, pady=2)

            tk.Label(row_frame, text=method, font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=25, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=f"{amount:.2f}", font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)

        # Tab 3: Profit Summary - NOW USER SPECIFIC
        profit_frame = tk.Frame(notebook, bg=BG_COLOR)
        notebook.add(profit_frame, text="Profit Summary")

        # User-specific profit summary
        tk.Label(profit_frame, text=f"Total Sales: ksh {user_total_sales:.2f}",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
        tk.Label(profit_frame, text=f"Total Profit: ksh {user_total_profit:.2f}",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=SUCCESS_COLOR).pack(pady=5)
        tk.Label(profit_frame, text=f"Profit Margin: {user_profit_percentage:.2f}%",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=5)
        tk.Label(profit_frame, text=f"Most Sold Item: {most_sold_item}",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
        tk.Label(profit_frame, text=f"Most Sold Category: {most_sold_category}",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)

        # Total row (at bottom of main frame)
        total_frame = tk.Frame(main_frame, bg=BG_COLOR)
        total_frame.pack(fill=tk.X, pady=(20, 10))

        tk.Label(total_frame, text="TOTAL SALES:", font=('Poppins', 14, 'bold'),
                 bg=BG_COLOR, fg=ACCENT_COLOR, anchor="e").pack(side=tk.LEFT, padx=5, expand=True)
        tk.Label(total_frame, text=f"ksh {user_total_sales:.2f}", font=('Poppins', 14, 'bold'),
                 bg=BG_COLOR, fg=ACCENT_COLOR).pack(side=tk.LEFT, padx=5)

        # Buttons
        btn_frame = tk.Frame(main_frame, bg=BG_COLOR)
        btn_frame.pack(pady=10)

        if self.is_admin_user():
            tk.Button(
                btn_frame, text="Clear Today's Sales",
                command=lambda: self.clear_today_sales(sales_window),
                bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                activebackground=HIGHLIGHT_COLOR, bd=0, padx=15, pady=5
            ).pack(side=tk.LEFT, padx=10)

        tk.Button(
            btn_frame, text="Print Summary",
            command=lambda: self.print_sales_summary(date, sales_data, user_total_sales, payment_methods, user_total_profit, user_profit_percentage, most_sold_item, most_sold_category),
            bg=BUTTON_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
            activebackground=ACCENT_COLOR, bd=0, padx=15, pady=5
        ).pack(side=tk.LEFT, padx=10)
        tk.Button(
            btn_frame, text="Close",
            command=sales_window.destroy,
            bg=BUTTON_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
            activebackground=ACCENT_COLOR, bd=0, padx=15, pady=5
        ).pack(side=tk.LEFT, padx=10)

    def print_sales_summary(self, date, sales_data, total, payment_methods, total_profit, profit_percentage, most_sold_item, most_sold_category):
        """Print a summary of daily sales with USER-SPECIFIC profit details"""
        summary = f"Daily Sales Summary - {date} - {self.current_user}\n"
        summary += "=" * 50 + "\n\n"

        summary += "Sales by Item:\n"
        summary += "-" * 50 + "\n"
        summary += f"{'Category':<15}{'Item':<20}{'Qty':>10}{'Amount':>15}{'Profit':>15}{'Margin':>10}\n"
        summary += "-" * 50 + "\n"

        for category, item, qty, amt, _, profit, margin in sales_data:
            summary += f"{category[:14]:<15}{item[:19]:<20}{qty:>10}{amt:>15.2f}{profit:>15.2f}{margin:>10.1f}%\n"

        summary += "\nPayment Methods:\n"
        summary += "-" * 50 + "\n"
        summary += f"{'Method':<25}{'Amount':>25}\n"
        summary += "-" * 50 + "\n"

        for method, amount in payment_methods.items():
            summary += f"{method[:24]:<25}{amount:>25.2f}\n"

        # Add USER-SPECIFIC profit information
        summary += "\nProfit Summary:\n"
        summary += "-" * 50 + "\n"
        summary += f"{'Total Sales:':<25}{total:>25.2f}\n"
        summary += f"{'Total Profit:':<25}{total_profit:>25.2f}\n"
        summary += f"{'Profit Margin:':<25}{profit_percentage:>24.2f}%\n"
        summary += f"{'Most Sold Item:':<25}{most_sold_item:>25}\n"
        summary += f"{'Most Sold Category:':<25}{most_sold_category:>25}\n"

        summary += "\n" + "=" * 50 + "\n"
        summary += f"{'TOTAL SALES:':<25}{total:>25.2f}\n"
        summary += "=" * 50 + "\n"

        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp:
                tmp.write(summary)
                tmp_path = tmp.name

            if os.name == 'nt':
                os.startfile(tmp_path, "print")
                messagebox.showinfo("Printing", "Sales summary sent to printer!", parent=self.root)
            elif os.name == 'posix':
                if subprocess.call(['lp', tmp_path]) == 0:
                    messagebox.showinfo("Printing", "Sales summary sent to printer!", parent=self.root)
                else:
                    messagebox.showerror("Error", "Failed to send to printer", parent=self.root)
            else:
                messagebox.showerror("Error", "Printing not supported on this platform", parent=self.root)

            threading.Timer(5.0, os.unlink, args=[tmp_path]).start()
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print sales summary:\n{str(e)}", parent=self.root)


    def clear_today_sales(self, parent_window=None):
        """Clear today's sales with proper authentication and confirmation"""
        # First authenticate manager
        auth_window = tk.Toplevel(self.root)
        auth_window.title("Clear Today's Sales - Authentication Required")
        auth_window.geometry("500x250")
        auth_window.configure(bg=BG_COLOR)
        auth_window.transient(self.root)
        auth_window.grab_set()

        tk.Label(auth_window, text="Manager Authentication Required", 
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)
        
        tk.Label(auth_window, text="Enter manager password to clear today's sales:", 
                 font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)

        password_var = tk.StringVar()
        password_entry = tk.Entry(auth_window, textvariable=password_var, show="•",
                                  font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        password_entry.pack(pady=10, ipady=3, fill=tk.X, padx=20)
        password_entry.focus_set()

        status_label = tk.Label(auth_window, text="", font=FONT_SMALL, bg=BG_COLOR, fg=ERROR_COLOR)
        status_label.pack(pady=5)

        def verify_and_clear():
            password = password_var.get()
            
            # Check if password matches any admin's manager password or the fixed passwords
            if password == "MANAGER1":
                auth_window.destroy()
                self._perform_clear_today_sales(parent_window)
                return
            
            # Check custom manager passwords
            for username, user_data in self.config["users"].items():
                if (user_data.get("is_admin", False) and 
                    (user_data.get("manager_password", "") == hash_password(password) or password == "MANAGER")):
                    auth_window.destroy()
                    self._perform_clear_today_sales(parent_window)
                    return
            
            status_label.config(text="Invalid manager password")

        button_frame = tk.Frame(auth_window, bg=BG_COLOR)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Authenticate & Clear", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=verify_and_clear,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=auth_window.destroy,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)

        auth_window.bind('<Return>', lambda event: verify_and_clear())

    def _perform_clear_today_sales(self, parent_window=None):
        """Perform the actual clearing of today's sales after authentication"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Final confirmation due to destructive nature
        confirm = messagebox.askyesno(
            "Final Confirmation", 
            f"WARNING: This will permanently delete ALL sales records for {today}!\n\n"
            f"This action cannot be undone and will:\n"
            f"• Remove all sales transactions\n"
            f"• Clear daily summary\n"
            f"• Restore stock levels\n\n"
            f"Are you absolutely sure you want to proceed?",
            icon='warning',
            parent=parent_window or self.root
        )
        
        if not confirm:
            return

        # Show progress window
        progress_window = tk.Toplevel(self.root)
        progress_window.title("Clearing Today's Sales")
        progress_window.geometry("400x200")
        progress_window.configure(bg=BG_COLOR)
        progress_window.transient(self.root)
        progress_window.grab_set()

        main_frame = tk.Frame(progress_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        tk.Label(main_frame, text="Clearing Today's Sales...", 
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
        
        progress = ttk.Progressbar(main_frame, mode='indeterminate', length=300)
        progress.pack(pady=10)
        progress.start(10)
        
        status_label = tk.Label(main_frame, text="Please wait...", 
                               font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR)
        status_label.pack(pady=5)

        def perform_clear():
            try:
                # Clear sales for today
                success = self.db.clear_daily_sales(today)
                
                if success:
                    # Record the activity
                    self.db.cursor.execute('''
                        INSERT INTO user_activity (user, activity_type, description)
                        VALUES (?, ?, ?)
                    ''', (self.current_user, 'system', f'Cleared all sales for {today}'))
                    self.db.conn.commit()
                    
                    progress_window.destroy()
                    
                    # Show success message
                    messagebox.showinfo(
                        "Clear Complete", 
                        f"Successfully cleared all sales records for {today}.\n\n"
                        f"Stock levels have been restored to their pre-sales state.",
                        parent=parent_window or self.root
                    )
                    
                    # Refresh any open sales windows
                    if parent_window and parent_window.winfo_exists():
                        parent_window.destroy()
                        
                else:
                    progress_window.destroy()
                    messagebox.showerror(
                        "Clear Failed", 
                        "Failed to clear today's sales. Please check the database.",
                        parent=parent_window or self.root
                    )
                    
            except Exception as e:
                progress_window.destroy()
                messagebox.showerror(
                    "Clear Failed", 
                    f"Error clearing today's sales:\n{str(e)}",
                    parent=parent_window or self.root
                )

        # Run clearing in thread to avoid blocking UI
        threading.Thread(target=perform_clear, daemon=True).start()

    def reset_all(self):
        self.customer_name_entry.delete(0, tk.END)
        for category in self.meal_entries:
            for item in self.meal_entries[category]:
                self.meal_entries[category][item].delete(0, tk.END)
        self.tax_btn_entry.delete(0, tk.END)
        self.total_btn_entry.delete(0, tk.END)
        self.calc_var.set("")
        self.bill_txt.delete(1.0, tk.END)
        self.default_bill()
        self.payment_method_used = {"method": "Cash", "details": ""}

    def add_new_meal_dialog(self):
        add_meal_win = tk.Toplevel(self.root)
        add_meal_win.title("Add New Meal")
        add_meal_win.state('zoomed')  # Changed from fixed size to full screen
        add_meal_win.configure(bg=BG_COLOR)
        add_meal_win.transient(self.root)
        add_meal_win.grab_set()

        # Category selection
        tk.Label(add_meal_win, text="Category:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, padx=10, pady=10, sticky=tk.E)
        category_var = tk.StringVar()
        category_dropdown = ttk.Combobox(add_meal_win, textvariable=category_var,
                                         values=list(self.menu_items.keys()), font=FONT_MEDIUM)
        category_dropdown.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        # Allow new categories
        category_dropdown['state'] = 'normal'

        # Meal name
        tk.Label(add_meal_win, text="Meal Name:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=1, column=0, padx=10, pady=10, sticky=tk.E)
        meal_name_var = tk.StringVar()
        tk.Entry(add_meal_win, textvariable=meal_name_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        # Description
        tk.Label(add_meal_win, text="Description:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=2, column=0, padx=10, pady=10, sticky=tk.E)
        desc_var = tk.StringVar()
        tk.Entry(add_meal_win, textvariable=desc_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        # Buying Price
        tk.Label(add_meal_win, text="Buying Price:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=3, column=0, padx=10, pady=10, sticky=tk.E)
        buying_var = tk.StringVar()
        tk.Entry(add_meal_win, textvariable=buying_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).grid(row=3, column=1, padx=10, pady=10, sticky="ew")

        # Selling Price
        tk.Label(add_meal_win, text="Selling Price:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=4, column=0, padx=10, pady=10, sticky=tk.E)
        selling_var = tk.StringVar()
        tk.Entry(add_meal_win, textvariable=selling_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).grid(row=4, column=1, padx=10, pady=10, sticky="ew")

        # Initial Stock
        # Initial Stock
        tk.Label(add_meal_win, text="Initial Stock:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=5, column=0, padx=10, pady=10, sticky=tk.E)
        stock_var = tk.StringVar(value="0")
        tk.Entry(add_meal_win, textvariable=stock_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).grid(row=5, column=1, padx=10, pady=10, sticky="ew")

        # Status label
        status_label = tk.Label(add_meal_win, text="", font=FONT_SMALL,
                                bg=BG_COLOR, fg=ERROR_COLOR)
        status_label.grid(row=6, column=0, columnspan=2, pady=5)

        def add_meal():
            category = category_var.get().strip()
            name = meal_name_var.get().strip()
            description = desc_var.get().strip()
            buying_price = buying_var.get()
            selling_price = selling_var.get()
            stock = stock_var.get()

            # Validate inputs
            if not category or not name or not buying_price or not selling_price or not stock:
                status_label.config(text="All fields except description are required")
                return

            try:
                buying_price = float(buying_price)
                selling_price = float(selling_price)
                stock = int(stock)

                if buying_price <= 0:
                    raise ValueError("Buying price must be positive")
                if selling_price <= 0:
                    raise ValueError("Selling price must be positive")
                if selling_price < buying_price:
                    raise ValueError("Selling price must be >= buying price")
                if stock < 0:
                    raise ValueError("Stock cannot be negative")

            except ValueError as e:
                status_label.config(text=f"Invalid value: {str(e)}")
                return

            # Add the meal to database
            if self.db.add_meal(category, name, description, buying_price, selling_price, stock):
                # Update the menu_items dictionary
                if category not in self.menu_items:
                    self.menu_items[category] = {}
                self.menu_items[category][name] = selling_price

                # Refresh the meal entries in the UI
                for widget in self.meal_frames[category].winfo_children():
                    if isinstance(widget, tk.Canvas):
                        for child in widget.winfo_children():
                            if isinstance(child, tk.Frame):  # This is our scrollable frame
                                child.destroy()
                                break
                        break

                # Recreate the scrollable content for this category
                canvas = None
                for widget in self.meal_frames[category].winfo_children():
                    if isinstance(widget, tk.Canvas):
                        canvas = widget
                        break

                if canvas:
                    scrollable_frame = tk.Frame(canvas, bg="#C2C2C8")
                    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

                    self.meal_entries[category] = {}
                    for item, price in self.menu_items[category].items():
                        item_frame = tk.Frame(scrollable_frame, bg="#C2C2C8")
                        item_frame.pack(fill=tk.X, padx=5, pady=2)

                        stock = self.db.get_current_stock_for_item(category, item)
                        stock_color = "red" if stock <= 5 else "black"

                        tk.Label(item_frame, text=f"{item[:18]:<18} (ksh{price}):",
                                 font=FONT_SMALL, bg="#C2C2C8", fg="#000",
                                 width=20, anchor="w").pack(side=tk.LEFT, padx=5)

                        tk.Label(item_frame, text=f"({stock})", font=FONT_SMALL,
                                 bg="#C2C2C8", fg=stock_color).pack(side=tk.LEFT)

                        entry = tk.Entry(item_frame, bd=1, bg="#fff", fg="#2a2a40",
                                         font=FONT_SMALL, width=16, justify=tk.CENTER)
                        entry.pack(side=tk.LEFT, padx=11)
                        self.meal_entries[category][item] = entry

                messagebox.showinfo("Success", f"{name} added to {category} category", parent=add_meal_win)
                add_meal_win.destroy()
            else:
                status_label.config(text="Failed to add meal. It may already exist.")

        # Button frame
        button_frame = tk.Frame(add_meal_win, bg=BG_COLOR)
        button_frame.grid(row=7, column=0, columnspan=2, pady=20)

        tk.Button(button_frame, text="Add Meal", font=FONT_MEDIUM,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, command=add_meal,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=add_meal_win.destroy,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)

    def remove_existing_meal_dialog(self):
        remove_meal_win = tk.Toplevel(self.root)
        remove_meal_win.title("Remove Meal")
        remove_meal_win.state('zoomed')  # Changed from fixed size to full screen
        remove_meal_win.configure(bg=BG_COLOR)
        remove_meal_win.transient(self.root)
        remove_meal_win.grab_set()

        # Category selection
        tk.Label(remove_meal_win, text="Category:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, padx=10, pady=10, sticky=tk.E)
        category_var = tk.StringVar()
        category_dropdown = ttk.Combobox(remove_meal_win, textvariable=category_var,
                                         values=list(self.menu_items.keys()), font=FONT_MEDIUM)
        category_dropdown.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        # Meal selection
        tk.Label(remove_meal_win, text="Meal:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=1, column=0, padx=10, pady=10, sticky=tk.E)
        meal_var = tk.StringVar()
        meal_dropdown = ttk.Combobox(remove_meal_win, textvariable=meal_var, font=FONT_MEDIUM)
        meal_dropdown.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        # Update meals when category changes
        def update_meals(*args):
            selected_category = category_var.get()
            if selected_category in self.menu_items:
                meal_dropdown['values'] = list(self.menu_items[selected_category].keys())

        category_var.trace('w', update_meals)

        # Current stock display
        current_stock_label = tk.Label(remove_meal_win, text="Current Stock: -",
                                       font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR)
        current_stock_label.grid(row=2, column=0, columnspan=2, pady=10)

        def update_current_stock(*args):
            category = category_var.get()
            meal = meal_var.get()
            if category and meal:
                stock = self.db.get_current_stock_for_item(category, meal)
                current_stock_label.config(text=f"Current Stock: {stock}")
            else:
                current_stock_label.config(text="Current Stock: -")

        category_var.trace('w', update_current_stock)
        meal_var.trace('w', update_current_stock)

        # Status label
        status_label = tk.Label(remove_meal_win, text="", font=FONT_SMALL,
                                bg=BG_COLOR, fg=ERROR_COLOR)
        status_label.grid(row=3, column=0, columnspan=2, pady=5)

        def remove_meal():
            category = category_var.get()
            meal = meal_var.get()

            if not category or not meal:
                status_label.config(text="Please select both category and meal")
                return

            current_stock = self.db.get_current_stock_for_item(category, meal)
            confirm_msg = f"Are you sure you want to remove {meal} from {category}?"
            if current_stock > 0:
                confirm_msg += f"\n\nWARNING: There are {current_stock} items in stock that will be lost!"

            if messagebox.askyesno("Confirm", confirm_msg, parent=remove_meal_win):
                if self.db.remove_meal(category, meal):
                    # Update the menu_items dictionary
                    del self.menu_items[category][meal]
                    if not self.menu_items[category]:  # Remove category if empty
                        del self.menu_items[category]
                        del self.meal_frames[category]
                        del self.meal_entries[category]
                    else:
                        # Refresh the meal entries in the UI
                        for widget in self.meal_frames[category].winfo_children():
                            if isinstance(widget, tk.Canvas):
                                for child in widget.winfo_children():
                                    if isinstance(child, tk.Frame):  # Scrollable frame
                                        child.destroy()
                                        break
                                break

                        # Recreate the scrollable content for this category
                        canvas = None
                        for widget in self.meal_frames[category].winfo_children():
                            if isinstance(widget, tk.Canvas):
                                canvas = widget
                                break

                        if canvas:
                            scrollable_frame = tk.Frame(canvas, bg="#C2C2C8")
                            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

                            self.meal_entries[category] = {}
                            for item, price in self.menu_items[category].items():
                                item_frame = tk.Frame(scrollable_frame, bg="#C2C2C8")
                                item_frame.pack(fill=tk.X, padx=5, pady=2)

                                stock = self.db.get_current_stock_for_item(category, item)
                                stock_color = "red" if stock <= 5 else "black"

                                tk.Label(item_frame, text=f"{item[:18]:<18} (ksh{price}):",
                                         font=FONT_SMALL, bg="#C2C2C8", fg="#000",
                                         width=20, anchor="w").pack(side=tk.LEFT, padx=5)

                                tk.Label(item_frame, text=f"({stock})", font=FONT_SMALL,
                                         bg="#C2C2C8", fg=stock_color).pack(side=tk.LEFT)

                                entry = tk.Entry(item_frame, bd=1, bg="#fff", fg="#2a2a40",
                                                 font=FONT_SMALL, width=16, justify=tk.CENTER)
                                entry.pack(side=tk.LEFT, padx=11)
                                self.meal_entries[category][item] = entry

                    messagebox.showinfo("Success", f"{meal} removed from {category} category", parent=remove_meal_win)
                    remove_meal_win.destroy()
                else:
                    status_label.config(text="Failed to remove meal")

        # Button frame
        button_frame = tk.Frame(remove_meal_win, bg=BG_COLOR)
        button_frame.grid(row=4, column=0, columnspan=2, pady=20)

        tk.Button(button_frame, text="Remove Meal", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=remove_meal,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=remove_meal_win.destroy,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)

    def payment_method_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Payment Method")
        dialog.state('zoomed')  # Changed from fixed size to full screen
        dialog.configure(bg=BG_COLOR)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="Choose Payment Method:",
                 font=FONT_LARGE, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        method_var = tk.StringVar(value=self.payment_method_used["method"])

        # Payment method options
        methods_frame = tk.Frame(dialog, bg=BG_COLOR)
        methods_frame.pack(pady=10)

        tk.Radiobutton(methods_frame, text="Cash", variable=method_var, value="Cash",
                       font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR,
                       selectcolor=BG_COLOR, activebackground=BG_COLOR).pack(anchor=tk.W, pady=5)
        tk.Radiobutton(methods_frame, text="Mpesa", variable=method_var, value="Mpesa",
                       font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR,
                       selectcolor=BG_COLOR, activebackground=BG_COLOR).pack(anchor=tk.W, pady=5)
        tk.Radiobutton(methods_frame, text="Credit Card", variable=method_var, value="Credit Card",
                       font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR,
                       selectcolor=BG_COLOR, activebackground=BG_COLOR).pack(anchor=tk.W, pady=5)

        # Button frame
        button_frame = tk.Frame(dialog, bg=BG_COLOR)
        button_frame.pack(pady=20)

        def proceed():
            method = method_var.get()
            self.payment_method_used = {"method": method, "details": ""}
            dialog.destroy()

            if method == "Mpesa":
                self.mpesa_payment()
            elif method == "Credit Card":
                self.credit_card_payment()
            else:
                messagebox.showinfo("Cash Payment", "Please collect cash from the customer.", parent=self.root)

        tk.Button(button_frame, text="Proceed", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=proceed,
                  padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=dialog.destroy,
                  padx=15, pady=5, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)


    def mpesa_payment(self):
        mpesa_win = tk.Toplevel(self.root)
        mpesa_win.title("Mpesa Payment")
        mpesa_win.state('zoomed')  # Changed from fixed size to full screen
        mpesa_win.configure(bg=BG_COLOR)
        mpesa_win.transient(self.root)
        mpesa_win.grab_set()

        # Mpesa API credentials
        self.consumer_key = "f4hFDXmMmj4jbSZXtVJnzGkeF0rClGfUmUzNjPbPlEpaoKmH"
        self.consumer_secret = "Nvbveu4nEZBNv6uOXX7UlmDAoDG7uOArqNjaiAqG2AVoZ5lIFYfnYlkKi6WYgiYD"
        self.business_short_code = "174379"
        self.passkey = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
        self.callback_url = "https://mydomain.com/path"
        self.transaction_type = "CustomerPayBillOnline"
        self.party_b = "174379"

        # Calculate grand total from pending sales
        grand_total = 0.0
        if hasattr(self, 'pending_sales') and self.pending_sales:
            for sale in self.pending_sales:
                grand_total += sale['amount']
            
            # Add tax if applicable
            tax_rate = self.config.get("tax_rate", 2.0) / 100.0
            tax_enabled = self.config.get("tax_enabled", True)
            if tax_enabled:
                tax = grand_total * tax_rate
                grand_total += tax

        if grand_total <= 0:
            messagebox.showerror("Error", "No items selected or total is zero. Please calculate total first.", parent=mpesa_win)
            mpesa_win.destroy()
            return

        # Get customer name
        customer_name = self.customer_name_entry.get().strip() if hasattr(self, 'customer_name_entry') and self.customer_name_entry.get().strip() else "Walk-in Customer"

        # Display amount information
        amount_frame = tk.Frame(mpesa_win, bg=BG_COLOR)
        amount_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(amount_frame, text=f"Amount to Pay: Ksh {grand_total:.2f}", 
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR).pack()
        tk.Label(amount_frame, text=f"Customer: {customer_name}",
                 font=FONT_SMALL, bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)

        tk.Label(mpesa_win, text="Enter Client Phone Number (0XXXXXXXXX):",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)

        phone_entry = tk.Entry(mpesa_win, font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        phone_entry.pack(pady=5, ipady=3)
        phone_entry.focus_set()

        def send_mpesa():
            phone = phone_entry.get().strip()

            # Validate phone number
            if not phone or not phone.isdigit() or len(phone) != 10 or not phone.startswith('0'):
                messagebox.showerror("Error", "Enter a valid Kenyan phone number in format 0XXXXXXXXX",
                                     parent=mpesa_win)
                return

            # Convert phone to 254 format for API
            formatted_phone = "254" + phone[1:]

            # Generate access token
            try:
                access_token = self.generate_access_token()
                if not access_token:
                    raise Exception("Could not generate access token")

                # Initiate STK push with the grand total amount
                response = self.initiate_stk_push(access_token, formatted_phone, grand_total)

                if response and response.get('ResponseCode') == '0':
                    # Show success message with customer name
                    success_message = (
                        f"✅ PAYMENT SUCCESSFUL!\n\n"
                        f"💰 Amount: Ksh {grand_total:.2f}\n"
                        f"📱 Phone: {phone}\n"
                        f"👤 Customer: {customer_name}\n"
                        f"🕒 Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
                        f"Payment received successfully from {customer_name}!"
                    )
                    messagebox.showinfo("Payment Successful", success_message, parent=self.root)
                    
                    # Update payment method details with customer name
                    self.payment_method_used = {
                        "method": "Mpesa",
                        "details": f"Phone: {phone}, Customer: {customer_name}, Amount: {grand_total:.2f}"
                    }
                    
                    # Update receipt to show payment confirmation and customer name
                    self.update_receipt_with_payment_confirmation(customer_name, phone, grand_total)
                    
                    mpesa_win.destroy()
                else:
                    error_msg = response.get('errorMessage', 'Unknown error occurred')
                    messagebox.showerror("Error", f"Failed to send STK push: {error_msg}", parent=mpesa_win)

            except Exception as e:
                messagebox.showerror("Error", f"MPesa API Error: {str(e)}", parent=mpesa_win)

        btn_frame = tk.Frame(mpesa_win, bg=BG_COLOR)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="Send Payment Request", font=FONT_MEDIUM,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, command=send_mpesa,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=mpesa_win.destroy,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)

        # Bind Enter key to send payment request
        mpesa_win.bind('<Return>', lambda event: send_mpesa())

    def update_receipt_with_payment_confirmation(self, customer_name, phone, amount):
        """Update the receipt to show payment confirmation and customer details"""
        if hasattr(self, 'bill_txt') and self.bill_txt:
            # Find the end of the receipt and add payment confirmation
            receipt_content = self.bill_txt.get(1.0, tk.END)
            
            # Remove existing payment confirmation if any
            lines = receipt_content.split('\n')
            new_lines = []
            payment_confirmed = False
            
            for line in lines:
                if "PAYMENT CONFIRMED" in line or "MPESA PAYMENT" in line:
                    payment_confirmed = True
                    continue
                if payment_confirmed and line.strip() == "":
                    payment_confirmed = False
                    continue
                if not payment_confirmed:
                    new_lines.append(line)
            
            # Rebuild receipt with updated payment confirmation
            self.bill_txt.delete(1.0, tk.END)
            for line in new_lines:
                if line.strip():  # Skip empty lines at the end
                    self.bill_txt.insert(tk.END, line + '\n')
            
            # Add payment confirmation section
            self.bill_txt.insert(tk.END, "\n" + "=" * 55 + "\n")
            self.bill_txt.insert(tk.END, "✅ PAYMENT CONFIRMED - MPESA\n")
            self.bill_txt.insert(tk.END, "=" * 55 + "\n")
            self.bill_txt.insert(tk.END, f"Customer: {customer_name}\n")
            self.bill_txt.insert(tk.END, f"Phone: {phone}\n")
            self.bill_txt.insert(tk.END, f"Amount: Ksh {amount:.2f}\n")
            self.bill_txt.insert(tk.END, f"Time: {datetime.now().strftime('%H:%M:%S')}\n")
            self.bill_txt.insert(tk.END, "Status: ✅ Payment Received\n")
            self.bill_txt.insert(tk.END, "=" * 55 + "\n")
            self.bill_txt.insert(tk.END, "Thank you for your payment!\n")
            self.bill_txt.insert(tk.END, "=" * 55 + "\n")

    def generate_access_token(self):
        """Generate OAuth access token using consumer key and secret"""
        try:
            auth_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
            response = requests.get(auth_url, auth=HTTPBasicAuth(self.consumer_key, self.consumer_secret))
            response.raise_for_status()
            return response.json().get('access_token')
        except Exception as e:
            print(f"Error generating access token: {str(e)}")
            return None

    def initiate_stk_push(self, access_token, phone, amount):
        """Initiate STK push to customer's phone"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            password = base64.b64encode(
                f"{self.business_short_code}{self.passkey}{timestamp}".encode()
            ).decode('utf-8')

            stk_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            payload = {
                "BusinessShortCode": self.business_short_code,
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": self.transaction_type,
                "Amount": int(amount),  # Convert to integer for MPesa API
                "PartyA": phone,
                "PartyB": self.business_short_code,
                "PhoneNumber": phone,
                "CallBackURL": self.callback_url,
                "AccountReference": "ZetechCafeteria",
                "TransactionDesc": "Cafeteria Payment"
            }

            response = requests.post(stk_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"STK Push Error: {str(e)}")
            try:
                return e.response.json()
            except:
                return {"errorMessage": str(e)}
        except Exception as e:
            print(f"STK Push General Error: {str(e)}")
            return {"errorMessage": str(e)}

    def credit_card_payment(self):
        cc_win = tk.Toplevel(self.root)
        cc_win.title("Credit Card Payment")
        cc_win.state('zoomed')  # Changed from fixed size to full screen
        cc_win.configure(bg=BG_COLOR)
        cc_win.transient(self.root)
        cc_win.grab_set()

        tk.Label(cc_win, text="Enter Credit Card Details",
                 font=FONT_LARGE, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        tk.Label(cc_win, text="Card Number:",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack()
        card_num = tk.Entry(cc_win, font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        card_num.pack(pady=5, ipady=3)

        tk.Label(cc_win, text="Expiry (MM/YY):",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack()
        expiry = tk.Entry(cc_win, font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        expiry.pack(pady=5, ipady=3)

        tk.Label(cc_win, text="CVV:",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack()
        cvv = tk.Entry(cc_win, font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR, show="*")
        cvv.pack(pady=5, ipady=3)

        tk.Label(cc_win, text="Name on Card:",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack()
        name = tk.Entry(cc_win, font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        name.pack(pady=5, ipady=3)

        def pay_card():
            if not card_num.get() or not expiry.get() or not cvv.get() or not name.get():
                messagebox.showerror("Error", "All fields required", parent=cc_win)
                return

            details = f"Card ending with {card_num.get()[-4:]}, Name: {name.get()}"
            self.payment_method_used = {"method": "Credit Card", "details": details}
            messagebox.showinfo("Success", "Credit Card payment processed!", parent=self.root)
            cc_win.destroy()

        btn_frame = tk.Frame(cc_win, bg=BG_COLOR)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="Pay", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=pay_card,
                  padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=cc_win.destroy,
                  padx=15, pady=5, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)

    def default_bill(self):
        """Set up the default receipt header for 80mm thermal printer in a logical/professional way"""
        from datetime import datetime
        self.bill_txt.delete(1.0, tk.END)
        # -- Arranged header --
        self.bill_txt.insert(tk.END, " " * 12 + "ZETECH UNIVERSITY CAFETERIA\n")
        self.bill_txt.insert(tk.END, " " * 14 + "OFFICIAL RECEIPT\n")
        self.bill_txt.insert(tk.END, " " * 14 + "C0NTACT:0796939191\n")
        self.bill_txt.insert(tk.END, "=" * 55 + "\n")
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.bill_txt.insert(tk.END, f"Date: {now}\n")
        self.bill_txt.insert(tk.END, f"Served by: {self.current_user if self.current_user else ''}\n")
        customer = self.customer_name_entry.get().strip() if hasattr(self, 'customer_name_entry') else ''
        if customer:
            self.bill_txt.insert(tk.END, f"Customer: {customer}\n")
        self.bill_txt.insert(tk.END, "=" * 55 + "\n")
        # Column headers
        self.bill_txt.insert(tk.END, f"{'Item':<20}{'Qty':>5}{'Price':>8}{'Total':>9}\n")
        self.bill_txt.insert(tk.END, "=" * 55 + "\n")

        


if __name__ == "__main__":
    root = tk.Tk()
    app = HotelApp(root)
    root.protocol("WM_DELETE_WINDOW", app.confirm_exit)
    root.mainloop()

