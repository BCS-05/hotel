import tkinter as tk
from tkinter import ttk, messagebox
import time
import json
import os
import threading
from datetime import datetime
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
DATABASE_FILE = "hotel_database.db"
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

    def initialize_database(self):
        """Initialize all database tables"""
        # Sales table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                meal TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                payment_method TEXT NOT NULL,
                payment_details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Meals table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                UNIQUE(category, name)
            )
        ''')

        # Daily summaries table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_summaries (
                date TEXT PRIMARY KEY,
                total_sales REAL NOT NULL,
                cash_sales REAL DEFAULT 0,
                mpesa_sales REAL DEFAULT 0,
                card_sales REAL DEFAULT 0,
                other_sales REAL DEFAULT 0,
                items_sold INTEGER DEFAULT 0
            )
        ''')

        self.conn.commit()
        self.initialize_default_meals()

    def initialize_default_meals(self):
        """Initialize with default meals if table is empty"""
        self.cursor.execute("SELECT COUNT(*) FROM meals")
        if self.cursor.fetchone()[0] == 0:
            default_meals = [
                ("Cold Drinks", "Soda", 60),
                ("Cold Drinks", "Water", 50),
                ("Cold Drinks", "Juice", 40),
                ("Hot Drinks", "Coffee", 30),
                ("Hot Drinks", "Milk", 25),
                ("Food", "Matooke", 80),
                ("Food", "Rice", 70),
                ("Sauce", "Meat", 200),
                ("Sauce", "Beans", 35)
            ]
            self.cursor.executemany(
                "INSERT INTO meals (category, name, price) VALUES (?, ?, ?)",
                default_meals
            )
            self.conn.commit()

    def record_sale(self, sale_data):
        """Record a sale in the database and update daily summary"""
        try:
            # Record the individual sale
            self.cursor.execute('''
                INSERT INTO sales 
                (user, date, time, customer_name, meal, quantity, price, amount, payment_method, payment_details) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                sale_data['user'],
                sale_data['date'],
                sale_data['time'],
                sale_data['customer_name'],
                sale_data['meal'],
                sale_data['quantity'],
                sale_data['price'],
                sale_data['amount'],
                sale_data['payment_method'],
                sale_data['payment_details']
            ))

            # Update or create daily summary
            self.update_daily_summary(sale_data)

            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error recording sale: {str(e)}")
            return False

    def update_daily_summary(self, sale_data):
        """Update the daily summary with new sale data"""
        date = sale_data['date']
        amount = sale_data['amount']
        payment_method = sale_data['payment_method']

        # Check if summary exists for this date
        self.cursor.execute("SELECT 1 FROM daily_summaries WHERE date=?", (date,))
        exists = self.cursor.fetchone()

        if exists:
            # Update existing summary
            update_query = '''
                UPDATE daily_summaries 
                SET total_sales = total_sales + ?,
                    items_sold = items_sold + ?,
                    {} = {} + ?
                WHERE date = ?
            '''.format(
                f"{payment_method.lower()}_sales",
                f"{payment_method.lower()}_sales"
            )

            self.cursor.execute(update_query, (
                amount,
                sale_data['quantity'],
                amount,
                date
            ))
        else:
            # Create new summary
            insert_query = '''
                INSERT INTO daily_summaries 
                (date, total_sales, items_sold, {}_sales)
                VALUES (?, ?, ?, ?)
            '''.format(payment_method.lower())

            self.cursor.execute(insert_query, (
                date,
                amount,
                sale_data['quantity'],
                amount
            ))

    def get_daily_sales(self, date, user=None):
        """Get sales summary for a specific date and optionally user"""
        try:
            if user:
                # Get sales for specific user
                self.cursor.execute('''
                    SELECT meal, SUM(quantity), SUM(amount), payment_method
                    FROM sales 
                    WHERE date=? AND user=?
                    GROUP BY meal, payment_method
                    ORDER BY SUM(amount) DESC
                ''', (date, user))
            else:
                # Get all sales for the date
                self.cursor.execute('''
                    SELECT meal, SUM(quantity), SUM(amount), payment_method
                    FROM sales 
                    WHERE date=?
                    GROUP BY meal, payment_method
                    ORDER BY SUM(amount) DESC
                ''', (date,))

            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error getting daily sales: {str(e)}")
            return []

    def get_daily_summary(self, date):
        """Get the daily summary record"""
        try:
            self.cursor.execute('''
                SELECT * FROM daily_summaries WHERE date=?
            ''', (date,))
            return self.cursor.fetchone()
        except Exception as e:
            print(f"Error getting daily summary: {str(e)}")
            return None

    def clear_daily_sales(self, date):
        """Clear all sales for a specific date"""
        try:
            with self.conn:
                self.cursor.execute('DELETE FROM sales WHERE date=?', (date,))
                self.cursor.execute('DELETE FROM daily_summaries WHERE date=?', (date,))
                self.conn.commit()
                return True
        except Exception as e:
            print(f"Error clearing daily sales: {str(e)}")
            return False

    def get_all_meals(self):
        """Get all active meals from database"""
        try:
            self.cursor.execute('''
                SELECT category, name, price 
                FROM meals 
                WHERE is_active = 1
                ORDER BY category, name
            ''')
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error getting meals: {str(e)}")
            return []

    def add_meal(self, category, name, price):
        """Add a new meal to the database"""
        try:
            self.cursor.execute('''
                INSERT INTO meals (category, name, price) 
                VALUES (?, ?, ?)
            ''', (category, name, price))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            print(f"Meal '{name}' already exists in category '{category}'")
            return False
        except Exception as e:
            print(f"Error adding meal: {str(e)}")
            return False

    def remove_meal(self, category, name):
        """Mark a meal as inactive (soft delete)"""
        try:
            self.cursor.execute('''
                UPDATE meals 
                SET is_active = 0 
                WHERE category=? AND name=?
            ''', (category, name))

            if self.cursor.rowcount == 0:
                print(f"No active meal found with name '{name}' in category '{category}'")
                return False

            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error removing meal: {str(e)}")
            return False


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

        # Change credentials button
        if self.config["users"]:
            tk.Button(login_box, text="Change Login", font=FONT_MEDIUM,
                      bg=BUTTON_COLOR, fg=FG_COLOR, bd=0,
                      activebackground=ACCENT_COLOR, activeforeground=FG_COLOR,
                      command=self.show_change_credentials
                      ).grid(row=3, column=0, columnspan=2, pady=10, padx=10, sticky="ew")

        # Add user button (only visible to admin users)
        if any(user.get("is_admin", False) for user in self.config["users"].values()):
            tk.Button(login_box, text="Add New User", font=FONT_MEDIUM,
                      bg=BUTTON_COLOR, fg=FG_COLOR, bd=0,
                      activebackground=ACCENT_COLOR, activeforeground=FG_COLOR,
                      command=self.show_add_user_dialog
                      ).grid(row=4, column=0, columnspan=2, pady=10, padx=10, sticky="ew")
            tk.Button(login_box, text="Remove User", font=FONT_MEDIUM,
                      bg=ERROR_COLOR, fg=FG_COLOR, bd=0,
                      activebackground=HIGHLIGHT_COLOR, activeforeground=FG_COLOR,
                      command=self.show_remove_user_dialog
                      ).grid(row=5, column=0, columnspan=2, pady=10, padx=10, sticky="ew")

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

    def show_main_system(self):
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
        for category, name, price in db_meals:
            if category not in self.menu_items:
                self.menu_items[category] = {}
            self.menu_items[category][name] = price

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

            # Add meal items
            self.meal_entries[category] = {}
            if category in self.menu_items:
                for item, price in self.menu_items[category].items():
                    item_frame = tk.Frame(scrollable_frame, bg="#C2C2C8")
                    item_frame.pack(fill=tk.X, padx=5, pady=2)

                    tk.Label(item_frame, text=f"{item[:18]:<18} (ksh{price}):",
                             font=FONT_SMALL, bg="#C2C2C8", fg="#000",
                             width=20, anchor="w").pack(side=tk.LEFT, padx=5)

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
                            cost = qty * price
                            total_list.append(cost)
                            self.bill_txt.insert(tk.END, f"{item[:18]:<20}{qty:>5}{price:>8.2f}{cost:>9.2f}\n")

                            # Prepare sales data for recording
                            sales_to_record.append({
                                'user': self.current_user,
                                'date': datetime.now().strftime('%Y-%m-%d'),
                                'time': datetime.now().strftime('%H:%M:%S'),
                                'customer_name': customer_name,
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
                    self.db.record_sale(sale)

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

        tk.Label(header_frame, text="Meal", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=25, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(header_frame, text="Qty Sold", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=10, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(header_frame, text="Total (ksh)", font=FONT_MEDIUM, bg=BG_COLOR,
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

        for meal, qty, amt, method in sales_data:
            row_frame = tk.Frame(scrollable_frame, bg=BG_COLOR)
            row_frame.pack(fill=tk.X, pady=2)

            tk.Label(row_frame, text=meal, font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=25, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=str(qty), font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=10, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=f"{amt:.2f}", font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)

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
        for _, _, amt, method in sales_data:
            payment_methods[method] = payment_methods.get(method, 0) + amt

        for method, amount in payment_methods.items():
            row_frame = tk.Frame(payment_scrollable, bg=BG_COLOR)
            row_frame.pack(fill=tk.X, pady=2)

            tk.Label(row_frame, text=method, font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=25, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=f"{amount:.2f}", font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)

        # Total row (at bottom of main frame)
        total_frame = tk.Frame(main_frame, bg=BG_COLOR)
        total_frame.pack(fill=tk.X, pady=(20, 10))

        total_sales = daily_summary[1] if daily_summary else sum(amt for _, _, amt, _ in sales_data)

        tk.Label(total_frame, text="TOTAL SALES:", font=('Poppins', 14, 'bold'),
                 bg=BG_COLOR, fg=ACCENT_COLOR, anchor="e").pack(side=tk.LEFT, padx=5, expand=True)
        tk.Label(total_frame, text=f"ksh {total_sales:.2f}", font=('Poppins', 14, 'bold'),
                 bg=BG_COLOR, fg=ACCENT_COLOR).pack(side=tk.LEFT, padx=5)

        # Buttons
        btn_frame = tk.Frame(main_frame, bg=BG_COLOR)
        btn_frame.pack(pady=10)

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
        """Print a summary of daily sales"""
        summary = f"Daily Sales Summary - {date}\n"
        summary += "=" * 50 + "\n\n"

        summary += "Sales by Item:\n"
        summary += "-" * 50 + "\n"
        summary += f"{'Item':<25}{'Qty':>10}{'Amount':>15}\n"
        summary += "-" * 50 + "\n"

        for item, qty, amt, *_ in sales_data:
            summary += f"{item[:24]:<25}{qty:>10}{amt:>15.2f}\n"

        summary += "\nPayment Methods:\n"
        summary += "-" * 50 + "\n"
        summary += f"{'Method':<25}{'Amount':>25}\n"
        summary += "-" * 50 + "\n"

        for method, amount in payment_methods.items():
            summary += f"{method[:24]:<25}{amount:>25.2f}\n"

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
        add_meal_win.geometry("400x300")
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

        # Price
        tk.Label(add_meal_win, text="Price (Ksh):", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=2, column=0, padx=10, pady=10, sticky=tk.E)
        price_var = tk.StringVar()
        tk.Entry(add_meal_win, textvariable=price_var, font=FONT_MEDIUM,
                 bg="#2a2a40", fg=FG_COLOR).grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        # Button frame
        button_frame = tk.Frame(add_meal_win, bg=BG_COLOR)
        button_frame.grid(row=3, column=0, columnspan=2, pady=20)

        def save_meal():
            category = category_var.get().strip()
            name = meal_name_var.get().strip()
            price = price_var.get().strip()

            if not category or not name or not price:
                messagebox.showerror("Error", "All fields are required", parent=add_meal_win)
                return

            try:
                price = float(price)
                if price <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", "Please enter a valid price", parent=add_meal_win)
                return

            if self.db.add_meal(category, name, price):
                messagebox.showinfo("Success", f"{name} added to {category} category", parent=add_meal_win)
                add_meal_win.destroy()
                # Refresh the main system to show the new meal
                self.show_main_system()

        tk.Button(button_frame, text="Save", font=FONT_MEDIUM,
                  bg=SUCCESS_COLOR, fg=FG_COLOR, command=save_meal,
                  padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=add_meal_win.destroy,
                  padx=15, pady=5, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)

    def remove_existing_meal_dialog(self):
        remove_meal_win = tk.Toplevel(self.root)
        remove_meal_win.title("Remove Meal")
        remove_meal_win.geometry("400x300")
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
        tk.Label(remove_meal_win, text="Meal Name:", font=FONT_MEDIUM,
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=1, column=0, padx=10, pady=10, sticky=tk.E)
        meal_var = tk.StringVar()
        meal_dropdown = ttk.Combobox(remove_meal_win, textvariable=meal_var, font=FONT_MEDIUM)
        meal_dropdown.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        def update_meals(*args):
            selected_category = category_var.get()
            if selected_category in self.menu_items:
                meal_dropdown['values'] = list(self.menu_items[selected_category].keys())

        category_var.trace('w', update_meals)

        # Button frame
        button_frame = tk.Frame(remove_meal_win, bg=BG_COLOR)
        button_frame.grid(row=3, column=0, columnspan=2, pady=20)

        def delete_meal():
            category = category_var.get()
            name = meal_var.get()

            if not category or not name:
                messagebox.showerror("Error", "Please select both category and meal", parent=remove_meal_win)
                return

            if messagebox.askyesno("Confirm", f"Are you sure you want to remove {name} from {category}?",
                                   parent=remove_meal_win):
                if self.db.remove_meal(category, name):
                    messagebox.showinfo("Success", f"{name} removed from {category} category", parent=remove_meal_win)
                    remove_meal_win.destroy()
                    # Refresh the main system to reflect the removal
                    self.show_main_system()

        tk.Button(button_frame, text="Remove", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=delete_meal,
                  padx=15, pady=5, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=remove_meal_win.destroy,
                  padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)

    def payment_method_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Payment Method")
        dialog.geometry("400x300")
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
        mpesa_win.geometry("400x250")
        mpesa_win.configure(bg=BG_COLOR)
        mpesa_win.transient(self.root)
        mpesa_win.grab_set()

        # Mpesa API credentials (using sandbox credentials)
        self.consumer_key = "f4hFDXmMmj4jbSZXtVJnzGkeF0rClGfUmUzNjPbPlEpaoKmH"
        self.consumer_secret = "Nvbveu4nEZBNv6uOXX7UlmDAoDG7uOArqNjaiAqG2AVoZ5lIFYfnYlkKi6WYgiYD"
        self.business_short_code = "174379"
        self.passkey = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
        self.callback_url = "https://mydomain.com/path"
        self.transaction_type = "CustomerPayBillOnline"
        self.party_b = "174379"

        tk.Label(mpesa_win, text="Enter Client Phone Number (0XXXXXXXXX):",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)

        phone_entry = tk.Entry(mpesa_win, font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        phone_entry.pack(pady=5, ipady=3)

        tk.Label(mpesa_win, text="Enter Amount (Ksh):",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)

        amount_entry = tk.Entry(mpesa_win, font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        amount_entry.pack(pady=5, ipady=3)

        def send_mpesa():
            phone = phone_entry.get().strip()
            amount = amount_entry.get().strip()

            # Validate phone number
            if not phone or not phone.isdigit() or len(phone) != 10 or not phone.startswith('0'):
                messagebox.showerror("Error", "Enter a valid Kenyan phone number in format 0XXXXXXXXX",
                                     parent=mpesa_win)
                return

            # Convert phone to 254 format for API
            formatted_phone = "254" + phone[1:]

            try:
                amt = float(amount)
                if amt <= 0:
                    raise ValueError
            except Exception:
                messagebox.showerror("Error", "Enter a valid amount greater than 0", parent=mpesa_win)
                return

            # Generate access token
            try:
                access_token = self.generate_access_token()
                if not access_token:
                    raise Exception("Could not generate access token")

                # Initiate STK push
                response = self.initiate_stk_push(access_token, formatted_phone, amt)

                if response and response.get('ResponseCode') == '0':
                    messagebox.showinfo("Success",
                                        f"STK push sent to {phone} successfully!\n"
                                        f"Check your phone to complete payment.",
                                        parent=self.root)
                    self.payment_method_used = {
                        "method": "Mpesa",
                        "details": f"Phone: {phone}, Amount: {amt:.2f}"
                    }
                    mpesa_win.destroy()
                else:
                    error_msg = response.get('errorMessage', 'Unknown error occurred')
                    messagebox.showerror("Error", f"Failed to send STK push: {error_msg}", parent=mpesa_win)

            except Exception as e:
                messagebox.showerror("Error", f"MPesa API Error: {str(e)}", parent=mpesa_win)

        btn_frame = tk.Frame(mpesa_win, bg=BG_COLOR)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="Send Payment Request", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=send_mpesa,
                  padx=15, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=mpesa_win.destroy,
                  padx=15, pady=5, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)

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
                "Amount": amount,
                "PartyA": phone,
                "PartyB": self.business_short_code,
                "PhoneNumber": phone,
                "CallBackURL": self.callback_url,
                "AccountReference": "HotelPayment",
                "TransactionDesc": "Hotel Payment"
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
        cc_win.geometry("400x350")
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
        self.bill_txt.delete(1.0, tk.END)
        self.bill_txt.insert(tk.END, " HOTEL RECEIPT ".center(40, "=") + "\n")
        self.bill_txt.insert(tk.END, "Location, Address\n".center(40) + "\n")
        self.bill_txt.insert(tk.END, "Contact: 0123456789\n".center(40) + "\n")
        self.bill_txt.insert(tk.END, "=" * 40 + "\n")


if __name__ == "__main__":
    root = tk.Tk()
    app = HotelApp(root)
    root.mainloop()
