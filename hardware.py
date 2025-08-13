# Enhanced Hotel Management System

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
DATABASE_FILE = "hotel1_database.db"
DEFAULT_CREDENTIALS = {
    "users": {
        "admin": {
            "password": "5f4dcc3b5aa765d61d8327deb882cf99",  # MD5 hash of "password"
            "is_admin": True,
            "manager_password": "1a1dc91c907325c69271ddf0c944bc72"  # MD5 hash of "manager123"
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

                # Update meal stock and sales metrics
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
                            avg_profit_margin = (total_profit + ?) / (total_sales + ?) * 100
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
                        date
                    ))
                else:
                    # Create new summary
                    self.cursor.execute(f'''
                        INSERT INTO daily_summaries 
                        (date, total_sales, items_sold, total_profit, {payment_method}_sales,
                         most_sold_item, most_sold_category, avg_profit_margin)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        date,
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
                           SUM(profit) as total_profit, AVG(profit/amount)*100 as avg_margin
                    FROM sales
                    WHERE date >= ? AND user = ?
                    GROUP BY user
                ''', (date_limit, user))
            else:
                self.cursor.execute('''
                    SELECT user, COUNT(*) as sales_count, SUM(amount) as total_sales, 
                           SUM(profit) as total_profit, AVG(profit/amount)*100 as avg_margin
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


class HotelApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Hotel Management System")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        self.root.configure(bg=BG_COLOR)

        # Initialize components
        self.config = load_config()
        self.db = DatabaseManager()
        self.current_user = None
        self.payment_method_used = {"method": "Cash", "details": ""}
        self.manager_mode = False

        # Initialize menu_items from database
        self.menu_items = {}
        db_meals = self.db.get_all_meals()
        for category, name, _, _, selling_price, _, _, _, _, _ in db_meals:
            if category not in self.menu_items:
                self.menu_items[category] = {}
            self.menu_items[category][name] = selling_price

        # Show login page
        self.show_login_page()

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
            self.current_user = None
            self.manager_mode = False
            self.show_login_page()

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def show_login_page(self):
        self.clear_window()

        # Main container
        main_container = tk.Frame(self.root, bg=BG_COLOR)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Title marquee
        title_marquee = Marquee(main_container, text="Welcome to Hotel Management System")
        title_marquee.pack(fill=tk.X, pady=(0, 20))

        # Login frame
        login_frame = tk.Frame(main_container, bg=BG_COLOR, bd=0)
        login_frame.pack(expand=True)

        # Login box
        login_box = tk.LabelFrame(login_frame, text="Login", font=('Poppins', 20, 'bold'),
                                  bg=BG_COLOR, fg=ACCENT_COLOR, bd=0)
        login_box.pack(padx=50, pady=20, ipadx=30, ipady=20)

        # Username (dropdown)
        tk.Label(login_box, text="Username:", bg=BG_COLOR, fg=FG_COLOR,
                 font=FONT_LARGE).grid(row=0, column=0, padx=10, pady=10, sticky=tk.E)
        username_var = tk.StringVar()
        user_dropdown = ttk.Combobox(login_box, font=FONT_LARGE, textvariable=username_var,
                                     values=list(self.config["users"].keys()), state="readonly")
        user_dropdown.grid(row=0, column=1, padx=10, pady=10, ipady=5, sticky="ew")

        # Password
        tk.Label(login_box, text="Password:", bg=BG_COLOR, fg=FG_COLOR,
                 font=FONT_LARGE).grid(row=1, column=0, padx=10, pady=10, sticky=tk.E)
        password_var = tk.StringVar()
        password_entry = tk.Entry(login_box, font=FONT_LARGE, bd=2,
                                  bg='#2a2a40', fg=FG_COLOR, insertbackground=FG_COLOR,
                                  textvariable=password_var, show="*")
        password_entry.grid(row=1, column=1, padx=10, pady=10, ipady=5, sticky="ew")

        # Buttons
        button_frame = tk.Frame(login_box, bg=BG_COLOR)
        button_frame.grid(row=2, column=0, columnspan=2, pady=20)

        tk.Button(button_frame, text="Login", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR,
                  command=lambda: self.check_login(username_var.get(), password_var.get()),
                  padx=20, pady=5).pack(side=tk.LEFT, padx=10)

        tk.Button(button_frame, text="Reset", font=FONT_MEDIUM,
                  bd=0, bg=ACCENT_COLOR, fg=BG_COLOR,
                  activebackground=FG_COLOR, activeforeground=BG_COLOR,
                  command=lambda: self.reset_login(username_var, password_var),
                  padx=20, pady=5).pack(side=tk.LEFT, padx=10)

        tk.Button(button_frame, text="Exit", font=FONT_MEDIUM,
                  bd=0, bg=ERROR_COLOR, fg=FG_COLOR,
                  activebackground=FG_COLOR, activeforeground=ERROR_COLOR,
                  command=self.confirm_exit,
                  padx=20, pady=5).pack(side=tk.LEFT, padx=10)

        # Manager login section
        manager_frame = tk.LabelFrame(login_box, text="Manager Login", font=('Poppins', 12, 'bold'),
                                      bg=BG_COLOR, fg=ACCENT_COLOR, bd=0)
        manager_frame.grid(row=3, column=0, columnspan=2, pady=10, padx=10, sticky="ew")

        tk.Label(manager_frame, text="Manager Password:", bg=BG_COLOR, fg=FG_COLOR,
                 font=FONT_SMALL).pack(side=tk.LEFT, padx=5)
        manager_pw_var = tk.StringVar()
        manager_entry = tk.Entry(manager_frame, textvariable=manager_pw_var, show="*",
                                 font=FONT_SMALL, bg="#2a2a40", fg=FG_COLOR, width=15)
        manager_entry.pack(side=tk.LEFT, padx=5)

        tk.Button(manager_frame, text="Manager Login", font=FONT_SMALL,
                  bg=HIGHLIGHT_COLOR, fg=FG_COLOR,
                  command=lambda: self.check_manager_login(manager_pw_var.get()),
                  padx=10, pady=2).pack(side=tk.LEFT, padx=5)

        # Change credentials button
        if self.config["users"]:
            tk.Button(login_box, text="Change Login", font=FONT_MEDIUM,
                      bg=BUTTON_COLOR, fg=FG_COLOR, bd=0,
                      activebackground=ACCENT_COLOR, activeforeground=FG_COLOR,
                      command=self.show_change_credentials
                      ).grid(row=4, column=0, columnspan=2, pady=10, padx=10, sticky="ew")

        # Add user button (only visible to admin users)
        if any(user.get("is_admin", False) for user in self.config["users"].values()):
            tk.Button(login_box, text="Add New User", font=FONT_MEDIUM,
                      bg=BUTTON_COLOR, fg=FG_COLOR, bd=0,
                      activebackground=ACCENT_COLOR, activeforeground=FG_COLOR,
                      command=self.show_add_user_dialog
                      ).grid(row=5, column=0, columnspan=2, pady=10, padx=10, sticky="ew")
            tk.Button(login_box, text="Remove User", font=FONT_MEDIUM,
                      bg=ERROR_COLOR, fg=FG_COLOR, bd=0,
                      activebackground=HIGHLIGHT_COLOR, activeforeground=FG_COLOR,
                      command=self.show_remove_user_dialog
                      ).grid(row=6, column=0, columnspan=2, pady=10, padx=10, sticky="ew")

    def check_manager_login(self, password):
        """Check if the entered password matches any admin's manager password"""
        for username, user_data in self.config["users"].items():
            if user_data.get("is_admin", False) and user_data.get("manager_password", "") == hash_password(password):
                self.current_user = username
                self.manager_mode = True
                progress_window = tk.Toplevel(self.root)
                progress_window.title("Logging In...")
                progress_window.geometry("400x100")
                progress_window.configure(bg=BG_COLOR)
                progress_window.transient(self.root)
                progress_window.grab_set()

                tk.Label(progress_window, text=f"Logging in as Manager, please wait...",
                         font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)

                progress_bar = ttk.Progressbar(progress_window, orient="horizontal",
                                               length=300, mode="determinate")
                progress_bar.pack(pady=10)

                # Use a queue to communicate between threads
                self.login_queue = queue.Queue()

                def simulate_login_progress():
                    for i in range(101):
                        progress_bar['value'] = i
                        progress_window.update_idletasks()
                        time.sleep(0.02)

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
        remove_user_win.geometry("400x300")
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

            # Check manager password
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
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Logging In...")
            progress_window.geometry("400x100")
            progress_window.configure(bg=BG_COLOR)
            progress_window.transient(self.root)
            progress_window.grab_set()

            tk.Label(progress_window, text=f"Logging in as {username}, please wait...",
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)

            progress_bar = ttk.Progressbar(progress_window, orient="horizontal",
                                           length=300, mode="determinate")
            progress_bar.pack(pady=10)

            # Use a queue to communicate between threads
            self.login_queue = queue.Queue()

            def simulate_login_progress():
                for i in range(101):
                    progress_bar['value'] = i
                    progress_window.update_idletasks()
                    time.sleep(0.02)

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

    def show_add_user_dialog(self):
        add_user_win = tk.Toplevel(self.root)
        add_user_win.title("Add New User")
        add_user_win.geometry("500x450")
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

            # For admin users, require manager password
            if is_admin and not manager_pw:
                status_label.config(text="Manager password required for admin users")
                return

            # Add the new user
            self.config["users"][new_user] = {
                "password": hash_password(new_pw),
                "is_admin": is_admin
            }

            if is_admin:
                self.config["users"][new_user]["manager_password"] = hash_password(manager_pw)

            save_full_config(self.config)
            messagebox.showinfo("Success", f"User {new_user} added successfully", parent=add_user_win)
            add_user_win.destroy()
            self.show_login_page()

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
        change_window.geometry("500x600")
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

        # Current password display
        self.current_pw_label = tk.Label(current_frame, text="Current Password: ******",
                                         font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR)
        self.current_pw_label.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="w")

        # New credentials section
        new_frame = tk.LabelFrame(main_frame, text="New Credentials",
                                  font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR)
        new_frame.pack(fill=tk.X, pady=10)

        # New password
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

        # Manager password (only for admin users)
        self.manager_pw_frame = tk.Frame(new_frame, bg=BG_COLOR)
        self.manager_pw_frame.grid(row=2, column=0, columnspan=2, pady=5, sticky="ew")

        tk.Label(self.manager_pw_frame, text="Manager Password:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(side=tk.LEFT)
        self.manager_pw_var = tk.StringVar()
        tk.Entry(self.manager_pw_frame, textvariable=self.manager_pw_var, show="*",
                 font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR, width=15).pack(side=tk.LEFT, padx=5)

        # Status label
        self.status_label = tk.Label(main_frame, text="", font=FONT_SMALL, bg=BG_COLOR, fg=ERROR_COLOR)
        self.status_label.pack(pady=5)

        def update_current_credentials(*args):
            username = self.user_var.get()
            if username in self.config["users"]:
                self.current_pw_label.config(text="Current Password: ******")

                # Show/hide manager password field based on admin status
                if self.config["users"][username].get("is_admin", False):
                    self.manager_pw_frame.grid()
                else:
                    self.manager_pw_frame.grid_remove()

        self.user_var.trace('w', update_current_credentials)

        def save_changes():
            username = self.user_var.get()
            new_pw = self.new_pw_var.get()
            confirm_pw = self.confirm_pw_var.get()
            manager_pw = self.manager_pw_var.get()

            if not username:
                self.status_label.config(text="Please select a user")
                return

            user_data = self.config["users"].get(username)
            if not user_data:
                self.status_label.config(text="User not found")
                return

            if new_pw and new_pw != confirm_pw:
                self.status_label.config(text="New passwords do not match")
                return

            # Update password if provided
            if new_pw:
                user_data["password"] = hash_password(new_pw)

            # Update manager password if provided and user is admin
            if manager_pw and user_data.get("is_admin", False):
                user_data["manager_password"] = hash_password(manager_pw)

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
            update_current_credentials()

    def show_manager_system(self):
        """Show the enhanced manager interface with comprehensive stock and sales management"""
        self.clear_window()

        # Configure grid weights
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

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

        # Logout button
        tk.Button(header_frame, text="Logout", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=self.confirm_logout,
                  padx=15, pady=3, activebackground=HIGHLIGHT_COLOR).pack(side=tk.RIGHT, padx=10)

        # Notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        # Tab 1: Current Stock
        stock_frame = tk.Frame(notebook, bg=BG_COLOR)
        notebook.add(stock_frame, text="Current Stock")

        # Treeview for stock display with more columns
        stock_tree = ttk.Treeview(stock_frame,
                                  columns=("Category", "Item", "Description", "Buying", "Selling",
                                           "Stock", "Sold", "Revenue", "Profit", "Margin", "Last Updated"),
                                  show="headings", selectmode="browse")

        # Configure headings
        stock_tree.heading("Category", text="Category")
        stock_tree.heading("Item", text="Item")
        stock_tree.heading("Description", text="Description")
        stock_tree.heading("Buying", text="Buying (Ksh)")
        stock_tree.heading("Selling", text="Selling (Ksh)")
        stock_tree.heading("Stock", text="Current Stock")
        stock_tree.heading("Sold", text="Total Sold")
        stock_tree.heading("Revenue", text="Revenue (Ksh)")
        stock_tree.heading("Profit", text="Profit (Ksh)")
        stock_tree.heading("Margin", text="Margin %")
        stock_tree.heading("Last Updated", text="Last Updated")

        # Configure columns
        stock_tree.column("Category", width=120, anchor=tk.W)
        stock_tree.column("Item", width=120, anchor=tk.W)
        stock_tree.column("Description", width=150, anchor=tk.W)
        stock_tree.column("Buying", width=80, anchor=tk.E)
        stock_tree.column("Selling", width=80, anchor=tk.E)
        stock_tree.column("Stock", width=80, anchor=tk.E)
        stock_tree.column("Sold", width=80, anchor=tk.E)
        stock_tree.column("Revenue", width=100, anchor=tk.E)
        stock_tree.column("Profit", width=100, anchor=tk.E)
        stock_tree.column("Margin", width=80, anchor=tk.E)
        stock_tree.column("Last Updated", width=120, anchor=tk.W)

        # Add scrollbar
        scrollbar = ttk.Scrollbar(stock_frame, orient="vertical", command=stock_tree.yview)
        stock_tree.configure(yscrollcommand=scrollbar.set)

        # Pack treeview and scrollbar
        stock_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Load stock data
        self.load_stock_data(stock_tree)

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
                history_tree, int(days_var.get()), item_var.get(), category_var.get()))
        filter_btn.pack(side=tk.LEFT, padx=5)

        # Treeview for history display with more columns
        history_tree = ttk.Treeview(history_frame,
                                    columns=("Date", "Time", "Item", "Category", "Type", "Qty",
                                             "Prev Stock", "New Stock", "Buying", "Selling", "User", "Notes"),
                                    show="headings", selectmode="browse")

        # Configure headings
        history_tree.heading("Date", text="Date")
        history_tree.heading("Time", text="Time")
        history_tree.heading("Item", text="Item")
        history_tree.heading("Category", text="Category")
        history_tree.heading("Type", text="Type")
        history_tree.heading("Qty", text="Qty")
        history_tree.heading("Prev Stock", text="Prev Stock")
        history_tree.heading("New Stock", text="New Stock")
        history_tree.heading("Buying", text="Buying (Ksh)")
        history_tree.heading("Selling", text="Selling (Ksh)")
        history_tree.heading("User", text="User")
        history_tree.heading("Notes", text="Notes")

        # Configure columns
        history_tree.column("Date", width=100, anchor=tk.W)
        history_tree.column("Time", width=80, anchor=tk.W)
        history_tree.column("Item", width=120, anchor=tk.W)
        history_tree.column("Category", width=100, anchor=tk.W)
        history_tree.column("Type", width=80, anchor=tk.W)
        history_tree.column("Qty", width=60, anchor=tk.E)
        history_tree.column("Prev Stock", width=80, anchor=tk.E)
        history_tree.column("New Stock", width=80, anchor=tk.E)
        history_tree.column("Buying", width=80, anchor=tk.E)
        history_tree.column("Selling", width=80, anchor=tk.E)
        history_tree.column("User", width=100, anchor=tk.W)
        history_tree.column("Notes", width=150, anchor=tk.W)

        # Add scrollbar
        history_scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=history_tree.yview)
        history_tree.configure(yscrollcommand=history_scrollbar.set)

        # Pack treeview and scrollbar
        history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Load history data
        self.load_history_data(history_tree)

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
                sales_tree, int(sales_days_var.get()),
                None if user_var.get() == "All" else user_var.get()))
        sales_filter_btn.pack(side=tk.LEFT, padx=5)

        # Treeview for sales report
        sales_tree = ttk.Treeview(sales_frame,
                                  columns=("User", "Sales Count", "Total Sales", "Total Profit", "Avg Margin"),
                                  show="headings", selectmode="browse")

        # Configure headings
        sales_tree.heading("User", text="User")
        sales_tree.heading("Sales Count", text="Sales Count")
        sales_tree.heading("Total Sales", text="Total Sales (Ksh)")
        sales_tree.heading("Total Profit", text="Total Profit (Ksh)")
        sales_tree.heading("Avg Margin", text="Avg Margin %")

        # Configure columns
        sales_tree.column("User", width=120, anchor=tk.W)
        sales_tree.column("Sales Count", width=100, anchor=tk.E)
        sales_tree.column("Total Sales", width=120, anchor=tk.E)
        sales_tree.column("Total Profit", width=120, anchor=tk.E)
        sales_tree.column("Avg Margin", width=100, anchor=tk.E)

        # Add scrollbar
        sales_scrollbar = ttk.Scrollbar(sales_frame, orient="vertical", command=sales_tree.yview)
        sales_tree.configure(yscrollcommand=sales_scrollbar.set)

        # Pack treeview and scrollbar
        sales_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sales_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Load initial sales report
        self.load_sales_report(sales_tree)

        # Tab 4: Low Stock Alerts
        low_stock_frame = tk.Frame(notebook, bg=BG_COLOR)
        notebook.add(low_stock_frame, text="Low Stock")

        # Treeview for low stock items
        low_stock_tree = ttk.Treeview(low_stock_frame,
                                      columns=("Category", "Item", "Current Stock", "Avg Daily Sales", "Days Left"),
                                      show="headings", selectmode="browse")

        # Configure headings
        low_stock_tree.heading("Category", text="Category")
        low_stock_tree.heading("Item", text="Item")
        low_stock_tree.heading("Current Stock", text="Current Stock")
        low_stock_tree.heading("Avg Daily Sales", text="Avg Daily Sales")
        low_stock_tree.heading("Days Left", text="Days Left")

        # Configure columns
        low_stock_tree.column("Category", width=120, anchor=tk.W)
        low_stock_tree.column("Item", width=150, anchor=tk.W)
        low_stock_tree.column("Current Stock", width=100, anchor=tk.E)
        low_stock_tree.column("Avg Daily Sales", width=120, anchor=tk.E)
        low_stock_tree.column("Days Left", width=100, anchor=tk.E)

        # Add scrollbar
        low_stock_scrollbar = ttk.Scrollbar(low_stock_frame, orient="vertical", command=low_stock_tree.yview)
        low_stock_tree.configure(yscrollcommand=low_stock_scrollbar.set)

        # Pack treeview and scrollbar
        low_stock_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        low_stock_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Load low stock data
        self.load_low_stock_data(low_stock_tree)

        # Button frame
        button_frame = tk.Frame(main_frame, bg=BG_COLOR)
        button_frame.grid(row=2, column=0, pady=10, sticky="ew")

        # Add stock button
        tk.Button(button_frame, text="Add Stock", font=FONT_MEDIUM,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, command=lambda: self.show_add_stock_dialog(stock_tree),
                  padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)

        # Remove stock button
        tk.Button(button_frame, text="Remove Stock", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=lambda: self.show_remove_stock_dialog(stock_tree),
                  padx=15, pady=5, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)

        # Add new item button
        tk.Button(button_frame, text="Add New Item", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=lambda: self.show_add_item_dialog(stock_tree),
                  padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)

        # Remove item button
        tk.Button(button_frame, text="Remove Item", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=lambda: self.show_remove_item_dialog(stock_tree),
                  padx=15, pady=5, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)

        # Refresh button
        tk.Button(button_frame, text="Refresh All", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=lambda: self.refresh_manager_data(
                stock_tree, history_tree, sales_tree, low_stock_tree),
                  padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.RIGHT, padx=10)

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
        """Load sales report data into the treeview"""
        # Clear existing data
        for item in tree.get_children():
            tree.delete(item)

        # Get sales report from database
        sales_data = self.db.get_user_sales_summary(user, days)

        # Insert data into treeview
        for user, count, sales, profit, margin in sales_data:
            tree.insert("", tk.END, values=(
                user,
                count,
                f"{sales:.2f}",
                f"{profit:.2f}",
                f"{margin:.1f}%"
            ))

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

    def refresh_manager_data(self, stock_tree, history_tree, sales_tree, low_stock_tree):
        """Refresh all manager data views"""
        self.load_stock_data(stock_tree)
        self.load_history_data(history_tree)
        self.load_sales_report(sales_tree)
        self.load_low_stock_data(low_stock_tree)
        messagebox.showinfo("Refreshed", "All data has been refreshed", parent=self.root)

    def show_add_stock_dialog(self, stock_tree):
        """Show dialog to add stock to existing item with comprehensive options"""
        add_dialog = tk.Toplevel(self.root)
        add_dialog.title("Add Stock")
        add_dialog.geometry("500x500")
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
        """Show dialog to remove stock from existing item with comprehensive options"""
        remove_dialog = tk.Toplevel(self.root)
        remove_dialog.title("Remove Stock")
        remove_dialog.geometry("500x400")
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
        """Show dialog to add a new item to the menu with comprehensive details"""
        add_dialog = tk.Toplevel(self.root)
        add_dialog.title("Add New Item")
        add_dialog.geometry("500x500")
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
        """Show dialog to remove an item from the menu with confirmation"""
        remove_dialog = tk.Toplevel(self.root)
        remove_dialog.title("Remove Item")
        remove_dialog.geometry("500x300")
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
        self.root.grid_columnconfigure(2, weight=0)  # Less weight for receipt frame
        self.root.grid_columnconfigure(3, weight=0)  # Less weight for calculator frame

        # Title marquee
        title_marquee = Marquee(self.root, text="HOTEL MANAGEMENT SYSTEM")
        title_marquee.grid(row=0, column=0, columnspan=4, sticky="ew", padx=10, pady=10)

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

        # Username label centered
        username_label = tk.Label(customer_frame, text=f"Username: {self.current_user}",
                                  font=("Arial", 16, "bold"), fg=ACCENT_COLOR, bg="#1e1e2e")
        username_label.grid(row=0, column=0, columnspan=3, pady=(5, 2), sticky="n")

        # Customer Name label and entry centered in next row
        name_label = tk.Label(customer_frame, text="Customer Name:",
                              font=FONT_MEDIUM, fg=ACCENT_COLOR, bg="#1e1e2e")
        name_label.grid(row=1, column=0, sticky="e", padx=(0, 5), pady=(10, 5))
        self.customer_name_entry = tk.Entry(customer_frame, bd=2, width=16,
                                            font=FONT_MEDIUM, bg="#fff", fg="#2a2a40")
        self.customer_name_entry.grid(row=1, column=1, sticky="ew", padx=(0, 5), pady=(10, 5))

        # Logout button right-aligned
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

        # Sauce frame
        sauce_frame = tk.LabelFrame(left_frame, text="Sauce", fg=ACCENT_COLOR, bg="#1e1e2e",
                                    font=FONT_MEDIUM, bd=2, relief=tk.GROOVE)
        sauce_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        sauce_frame.grid_rowconfigure(0, weight=1)
        sauce_frame.grid_columnconfigure(0, weight=1)
        self.meal_frames["Sauce"] = sauce_frame

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

        # Cold Drinks frame
        cold_drinks_frame = tk.LabelFrame(right_frame, text="Cold Drinks", fg=ACCENT_COLOR, bg="#1e1e2e",
                                          font=FONT_MEDIUM, bd=2, relief=tk.GROOVE)
        cold_drinks_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        cold_drinks_frame.grid_rowconfigure(0, weight=1)
        cold_drinks_frame.grid_columnconfigure(0, weight=1)
        self.meal_frames["Cold Drinks"] = cold_drinks_frame

        # Add scrollable content to each category frame
        for category, frame in self.meal_frames.items():
            # Create canvas and scrollbar
            canvas = tk.Canvas(frame, bg="#C2C2C8", highlightthickness=0)
            scrollbar = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
            scrollable_frame = tk.Frame(canvas, bg="#C2C2C8")

            scrollable_frame.bind(
                "<Configure>",
                lambda e, canvas=canvas: canvas.configure(
                    scrollregion=canvas.bbox("all")
                )
            )

            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            # Pack canvas and scrollbar
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            # Add meal items with stock indicators
            self.meal_entries[category] = {}
            if category in self.menu_items:
                for item, price in self.menu_items[category].items():
                    item_frame = tk.Frame(scrollable_frame, bg="#C2C2C8")
                    item_frame.pack(fill=tk.X, padx=5, pady=2)

                    # Get current stock for this item
                    stock = self.db.get_current_stock_for_item(category, item)
                    stock_color = "red" if stock <= 5 else "black"

                    tk.Label(item_frame, text=f"{item[:18]:<18} (ksh{price}):",
                             font=FONT_SMALL, bg="#C2C2C8", fg="#000",
                             width=20, anchor="w").pack(side=tk.LEFT, padx=5)

                    # Stock indicator
                    tk.Label(item_frame, text=f"({stock})", font=FONT_SMALL,
                             bg="#C2C2C8", fg=stock_color).pack(side=tk.LEFT)

                    entry = tk.Entry(item_frame, bd=1, bg="#fff", fg="#2a2a40",
                                     font=FONT_SMALL, width=16, justify=tk.CENTER)
                    entry.pack(side=tk.LEFT, padx=11)
                    self.meal_entries[category][item] = entry

        # Receipt frame
        bill_frame = tk.LabelFrame(main_frame, text="Receipt", font=FONT_MEDIUM,
                                   bg="#2a2a40", fg=ACCENT_COLOR, bd=2, relief=tk.GROOVE)
        bill_frame.grid(row=1, column=2, rowspan=2, sticky="nsew", padx=5, pady=5, ipadx=5)
        bill_frame.grid_rowconfigure(0, weight=1)
        bill_frame.grid_columnconfigure(0, weight=1)

        # Text widget for receipt
        self.bill_txt = tk.Text(bill_frame, bg="#fff", fg="#2a2a40",
                                font=('Consolas', 10), wrap=tk.WORD, width=30)
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
        num_ent = tk.Entry(calc_frame, bd=1, bg="#c2ec2a", fg="#2a2a40",
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

        tk.Label(control_frame, text="Tax:", font=FONT_MEDIUM,
                 fg=ACCENT_COLOR, width=4, bg="#1e1e2e").grid(row=0, column=0, padx=5, pady=2, sticky=tk.E)

        self.tax_btn_entry = tk.Entry(control_frame, bd=1, bg="#fff", fg="#2a2a40",
                                      font=FONT_MEDIUM, width=15, justify=tk.RIGHT)
        self.tax_btn_entry.grid(row=0, column=1, padx=5, pady=2)

        tk.Label(control_frame, text="Total:", font=FONT_MEDIUM,
                 fg=ACCENT_COLOR, width=4, bg="#1e1e2e").grid(row=1, column=0, padx=5, pady=2, sticky=tk.E)

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
            ("Total", self.calculate_total, HIGHLIGHT_COLOR, FG_COLOR),
            ("Show Daily Sales", self.show_daily_sales, ACCENT_COLOR, BG_COLOR),
            ("Reset", self.reset_all, ERROR_COLOR, FG_COLOR)
        ]

        # Only show admin buttons for admin users
        if self.is_admin_user():
            buttons.extend([
                ("Add Meal", self.add_new_meal_dialog, SUCCESS_COLOR, FG_COLOR),
                ("Remove Meal", self.remove_existing_meal_dialog, ERROR_COLOR, FG_COLOR)
            ])

        for text, command, bg, fg in buttons:
            tk.Button(button_frame, text=text, command=command,
                      bg=bg, fg=fg, **button_style).pack(side=tk.LEFT, padx=5)

    def calculate_total(self):
        customer_name = self.customer_name_entry.get().strip()
        if not customer_name:
            messagebox.showerror("Error", "Please enter customer name", parent=self.root)
            return

        total_list = []
        self.bill_txt.delete(1.0, tk.END)
        self.default_bill()
        self.bill_txt.insert(tk.END, f"Username: {self.current_user}\n")
        self.bill_txt.insert(tk.END, f"Customer: {customer_name}\n")
        self.bill_txt.insert(tk.END, "=" * 40 + "\n")

        items_selected = False
        sales_to_record = []

        try:
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
                            # Check stock availability
                            current_stock = self.db.get_current_stock_for_item(category, item)
                            if current_stock < qty:
                                messagebox.showerror("Error",
                                                     f"Not enough stock for {item}. Only {current_stock} available",
                                                     parent=self.root)
                                return

                            cost = qty * price
                            total_list.append(cost)
                            self.bill_txt.insert(tk.END, f"{item[:18]:<20}{qty:>5}{price:>8.2f}{cost:>9.2f}\n")

                            # Prepare sales data for recording
                            sales_to_record.append({
                                'user': self.current_user,
                                'date': datetime.now().strftime('%Y-%m-%d'),
                                'time': datetime.now().strftime('%H:%M:%S'),
                                'customer_name': customer_name,
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
                # Record all sales in the database
                for sale in sales_to_record:
                    success, message = self.db.record_sale(sale)
                    if not success:
                        messagebox.showerror("Error", f"Failed to record sale: {message}", parent=self.root)
                        return

                total_cost = sum(total_list)
                tax = total_cost * 0.02
                grand_total = total_cost + tax

                self.bill_txt.insert(tk.END, "-" * 40 + "\n")
                self.bill_txt.insert(tk.END, f"{'Subtotal:':<20}{'':>13}ksh{total_cost:>9.2f}\n")
                self.bill_txt.insert(tk.END, f"{'Tax (2%):':<20}{'':>13}ksh{tax:>9.2f}\n")
                self.bill_txt.insert(tk.END, "-" * 40 + "\n")
                self.bill_txt.insert(tk.END, f"{'GRAND TOTAL:':<20}{'':>13}ksh{grand_total:>9.2f}\n")
                self.bill_txt.insert(tk.END, "=" * 40 + "\n")

                # Payment method info
                if self.payment_method_used["method"]:
                    self.bill_txt.insert(tk.END, f"Payment Method: {self.payment_method_used['method']}\n")
                    if self.payment_method_used["details"]:
                        self.bill_txt.insert(tk.END, f"Details: {self.payment_method_used['details']}\n")
                self.bill_txt.insert(tk.END, "\nThank you for your business!\n")

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

    def show_daily_sales(self):
        date = datetime.now().strftime('%Y-%m-%d')

        # Get sales data for the current date
        sales_data = self.db.get_daily_sales(date, self.current_user)
        daily_summary = self.db.get_daily_summary(date)

        sales_window = tk.Toplevel(self.root)
        sales_window.title('Daily Sales Summary')
        sales_window.geometry('900x700')
        sales_window.configure(bg=BG_COLOR)

        # Main frame with scrollbar
        main_frame = tk.Frame(sales_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Title
        tk.Label(main_frame, text=f"Sales Summary for {date}",
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
                 fg=ACCENT_COLOR, width=10, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(header_frame, text="Amount", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(header_frame, text="Profit", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(header_frame, text="Margin", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=10, anchor="w").pack(side=tk.LEFT, padx=5)

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
            row_frame.pack(fill=tk.X, pady=2)

            tk.Label(row_frame, text=category, font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=meal, font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=20, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=str(qty), font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=10, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=f"{amt:.2f}", font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=f"{profit:.2f}", font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=f"{margin:.1f}%", font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=10, anchor="w").pack(side=tk.LEFT, padx=5)

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

        # Group sales by payment method
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

        # Tab 3: Profit Summary
        profit_frame = tk.Frame(notebook, bg=BG_COLOR)
        notebook.add(profit_frame, text="Profit Summary")

        # Profit summary
        if daily_summary:
            total_sales = daily_summary[1]
            total_profit = daily_summary[7]  # Index 7 is total_profit
            profit_percentage = (total_profit / total_sales * 100) if total_sales > 0 else 0

            tk.Label(profit_frame, text=f"Total Sales: ksh {total_sales:.2f}",
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
            tk.Label(profit_frame, text=f"Total Profit: ksh {total_profit:.2f}",
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=SUCCESS_COLOR).pack(pady=5)
            tk.Label(profit_frame, text=f"Profit Margin: {profit_percentage:.2f}%",
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=5)

            # Most sold item and category
            tk.Label(profit_frame, text=f"Most Sold Item: {daily_summary[8]}",
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
            tk.Label(profit_frame, text=f"Most Sold Category: {daily_summary[9]}",
                     font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)

        # Total row (at bottom of main frame)
        total_frame = tk.Frame(main_frame, bg=BG_COLOR)
        total_frame.pack(fill=tk.X, pady=(20, 10))

        total_sales = daily_summary[1] if daily_summary else sum(amt for _, _, _, amt, _, _, _ in sales_data)

        tk.Label(total_frame, text="TOTAL SALES:", font=('Poppins', 14, 'bold'),
                 bg=BG_COLOR, fg=ACCENT_COLOR, anchor="e").pack(side=tk.LEFT, padx=5, expand=True)
        tk.Label(total_frame, text=f"ksh {total_sales:.2f}", font=('Poppins', 14, 'bold'),
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
            command=lambda: self.print_sales_summary(date, sales_data, total_sales, payment_methods),
            bg=BUTTON_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
            activebackground=ACCENT_COLOR, bd=0, padx=15, pady=5
        ).pack(side=tk.LEFT, padx=10)
        tk.Button(
            btn_frame, text="Close",
            command=sales_window.destroy,
            bg=BUTTON_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
            activebackground=ACCENT_COLOR, bd=0, padx=15, pady=5
        ).pack(side=tk.LEFT, padx=10)

    def clear_today_sales(self, sales_window=None):
        def do_clear():
            date = datetime.now().strftime('%Y-%m-%d')
            if self.db.clear_daily_sales(date):
                messagebox.showinfo("Cleared", "Today's sales have been cleared.")
                if sales_window:
                    sales_window.destroy()
                    self.show_daily_sales()
            else:
                messagebox.showerror("Error", "Failed to clear today's sales")

        # Prompt for universal clear password
        pw_window = tk.Toplevel(self.root)
        pw_window.title("Clear Daily Records Password Required")
        pw_window.geometry("400x200")
        pw_window.configure(bg=BG_COLOR)
        pw_window.transient(self.root)
        pw_window.grab_set()

        tk.Label(pw_window, text="Enter password to clear today's sales:",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)

        pw_var = tk.StringVar()
        pw_entry = tk.Entry(pw_window, textvariable=pw_var, show="*", font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        pw_entry.pack(pady=10, ipady=5)
        pw_entry.focus_set()

        btn_frame = tk.Frame(pw_window, bg=BG_COLOR)
        btn_frame.pack(pady=10)

        def check_pw():
            if hash_password(pw_var.get()) == hash_password("clinton"):
                pw_window.destroy()
                do_clear()
            else:
                messagebox.showerror("Error", "Incorrect password. Cannot clear today's sales.")
                pw_window.lift()
                pw_entry.delete(0, tk.END)

        tk.Button(btn_frame, text="OK", command=check_pw,
                  bg=BUTTON_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=20, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Cancel", command=pw_window.destroy,
                  bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=20, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)

    def print_sales_summary(self, date, sales_data, total, payment_methods):
        """Print a summary of daily sales with enhanced details"""
        summary = f"Daily Sales Summary - {date}\n"
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

        # Add profit information
        daily_summary = self.db.get_daily_summary(date)
        if daily_summary:
            total_profit = daily_summary[7]
            profit_percentage = (total_profit / total * 100) if total > 0 else 0
            summary += "\nProfit Summary:\n"
            summary += "-" * 50 + "\n"
            summary += f"{'Total Sales:':<25}{total:>25.2f}\n"
            summary += f"{'Total Profit:':<25}{total_profit:>25.2f}\n"
            summary += f"{'Profit Margin:':<25}{profit_percentage:>24.2f}%\n"
            summary += f"{'Most Sold Item:':<25}{daily_summary[8]:>25}\n"
            summary += f"{'Most Sold Category:':<25}{daily_summary[9]:>25}\n"

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

    def print_receipt(self):
        if not self.customer_name_entry.get().strip():
            messagebox.showerror("Error", "Please enter customer name first", parent=self.root)
            return

        self.calculate_total()
        bill_content = self.bill_txt.get("1.0", tk.END)

        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp:
                tmp.write(bill_content)
                tmp_path = tmp.name

            if os.name == 'nt':
                os.startfile(tmp_path, "print")
                messagebox.showinfo("Printing", "Receipt sent to printer!", parent=self.root)
            elif os.name == 'posix':
                if subprocess.call(['lp', tmp_path]) == 0:
                    messagebox.showinfo("Printing", "Receipt sent to printer!", parent=self.root)
                else:
                    messagebox.showerror("Error", "Failed to send to printer", parent=self.root)
            else:
                messagebox.showerror("Error", "Printing not supported on this platform", parent=self.root)

            threading.Timer(5.0, os.unlink, args=[tmp_path]).start()
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print receipt:\n{str(e)}", parent=self.root)

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
        add_meal_win.geometry("500x500")
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
        """Show dialog to remove an existing meal from the menu"""
        remove_meal_win = tk.Toplevel(self.root)
        remove_meal_win.title("Remove Meal")
        remove_meal_win.geometry("500x400")
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
        """Show dialog to select payment method with details"""
        payment_win = tk.Toplevel(self.root)
        payment_win.title("Payment Method")
        payment_win.geometry("400x300")
        payment_win.configure(bg=BG_COLOR)
        payment_win.transient(self.root)
        payment_win.grab_set()

        # Payment method selection
        tk.Label(payment_win, text="Payment Method:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)

        method_var = tk.StringVar(value=self.payment_method_used["method"])
        methods = ["Cash", "M-Pesa", "Credit Card", "Other"]
        for method in methods:
            tk.Radiobutton(payment_win, text=method, variable=method_var, value=method,
                           font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR,
                           selectcolor=BG_COLOR, activebackground=BG_COLOR).pack(anchor=tk.W, padx=20)

        # Payment details
        tk.Label(payment_win, text="Details (if applicable):", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
        details_var = tk.StringVar(value=self.payment_method_used["details"])
        tk.Entry(payment_win, textvariable=details_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).pack(pady=5, ipady=3, fill=tk.X, padx=20)

        def save_payment():
            self.payment_method_used = {
                "method": method_var.get(),
                "details": details_var.get()
            }
            payment_win.destroy()

        # Button frame
        button_frame = tk.Frame(payment_win, bg=BG_COLOR)
        button_frame.pack(pady=20)

        tk.Button(button_frame, text="OK", font=FONT_MEDIUM,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, command=save_payment,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=payment_win.destroy,
                  padx=15, pady=5).pack(side=tk.LEFT, padx=10)

    def default_bill(self):
        """Set up the default receipt header"""
        self.bill_txt.insert(tk.END, " " * 10 + "HOTEL MANAGEMENT SYSTEM\n")
        self.bill_txt.insert(tk.END, " " * 15 + "RECEIPT\n")
        self.bill_txt.insert(tk.END, "=" * 40 + "\n")
        self.bill_txt.insert(tk.END, f"{'Item':<20}{'Qty':>5}{'Price':>8}{'Total':>9}\n")
        self.bill_txt.insert(tk.END, "=" * 40 + "\n")


if __name__ == "__main__":
    root = tk.Tk()
    app = HotelApp(root)
    root.protocol("WM_DELETE_WINDOW", app.confirm_exit)
    root.mainloop()
