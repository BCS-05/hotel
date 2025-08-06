        # Reduced height since we removed reference field
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
import datetime
from datetime import datetime
date = datetime.now().strftime('%Y-%m-%d')

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
DEFAULT_CREDENTIALS = {
    "username": "admin",
    "password": "password",
    "manager_password": "manager123"
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        if "manager_password" not in config:
            config["manager_password"] = DEFAULT_CREDENTIALS["manager_password"]
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f)
        return config
    else:
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CREDENTIALS, f)
        return DEFAULT_CREDENTIALS


def save_config(username, password, manager_password=None):
    config = {"username": username, "password": password}
    if manager_password is not None:
        config["manager_password"] = manager_password
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)


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
        self.root.title("Hiram Hotel Management System")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        self.root.configure(bg=BG_COLOR)
        self.credentials = load_config()
        self.products = []
        self.payment_method_used = {"method": "Cash", "details": ""}
        self.setup_databases()
        self.show_login_page()

    def setup_databases(self):
        """Initialize all database connections in the main thread"""
        self.setup_sales_db()
        self.setup_meals_db()

    def setup_sales_db(self):
        self.sales_conn = sqlite3.connect('sales.db', check_same_thread=False)
        self.sales_cursor = self.sales_conn.cursor()
        self.sales_cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                meal TEXT,
                quantity INTEGER,
                amount REAL
            )
        ''')
        self.sales_conn.commit()

    def setup_meals_db(self):
        self.meals_conn = sqlite3.connect('meals.db', check_same_thread=False)
        self.meals_cursor = self.meals_conn.cursor()
        self.meals_cursor.execute('''
            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                name TEXT,
                price REAL,
                UNIQUE(category, name)
            )
        ''')
        self.meals_conn.commit()

        # Initialize with default meals if table is empty
        self.meals_cursor.execute("SELECT COUNT(*) FROM meals")
        if self.meals_cursor.fetchone()[0] == 0:
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
            self.meals_cursor.executemany("INSERT INTO meals (category, name, price) VALUES (?, ?, ?)", default_meals)
            self.meals_conn.commit()

    def get_all_meals(self):
        """Get all meals from database - must be called from main thread"""
        try:
            self.meals_cursor.execute("SELECT category, name, price FROM meals ORDER BY category, name")
            return self.meals_cursor.fetchall()
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to get meals: {str(e)}")
            return []

    def add_new_meal(self, category, name, price):
        """Add a new meal to the database"""
        try:
            self.meals_cursor.execute("INSERT INTO meals (category, name, price) VALUES (?, ?, ?)",
                                      (category, name, price))
            self.meals_conn.commit()
            return True
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", f"A meal with name '{name}' already exists in category '{category}'")
            return False
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to add meal: {str(e)}")
            return False

    def remove_meal(self, category, name):
        """Remove a meal from the database"""
        try:
            self.meals_cursor.execute("DELETE FROM meals WHERE category=? AND name=?", (category, name))
            if self.meals_cursor.rowcount == 0:
                messagebox.showerror("Error", f"No meal found with name '{name}' in category '{category}'")
                return False
            self.meals_conn.commit()
            return True
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to remove meal: {str(e)}")
            return False

    def record_sale(self, meal, quantity, amount):
        """Record a sale in the database"""
        try:
            date = datetime.now().strftime('%Y-%m-%d')
            self.sales_cursor.execute("INSERT INTO sales (date, meal, quantity, amount) VALUES (?, ?, ?, ?)",
                                      (date, meal, quantity, amount))
            self.sales_conn.commit()
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to record sale: {str(e)}")

    def show_daily_sales(self):
        date = datetime.now().strftime('%Y-%m-%d')
        self.sales_cursor.execute('SELECT meal, SUM(quantity), SUM(amount) FROM sales WHERE date=? GROUP BY meal',
                                  (date,))
        rows = self.sales_cursor.fetchall()
        self.sales_cursor.execute('SELECT SUM(amount) FROM sales WHERE date=?', (date,))
        total = self.sales_cursor.fetchone()[0] or 0

        sales_window = tk.Toplevel(self.root)
        sales_window.title('Daily Sales Summary')
        sales_window.geometry('800x600')
        sales_window.configure(bg=BG_COLOR)

        # Main frame
        main_frame = tk.Frame(sales_window, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Title
        tk.Label(main_frame, text=f"Sales Summary for {date}",
                 font=('Poppins', 16, 'bold'), bg=BG_COLOR, fg=ACCENT_COLOR).pack(pady=10)

        # Create a frame with scrollbar
        container = tk.Frame(main_frame, bg=BG_COLOR)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, bg=BG_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=BG_COLOR)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Header row
        header_frame = tk.Frame(scrollable_frame, bg=BG_COLOR)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(header_frame, text="Meal", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=25, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(header_frame, text="Qty Sold", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=10, anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(header_frame, text="Total (ksh)", font=FONT_MEDIUM, bg=BG_COLOR,
                 fg=ACCENT_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)

        # Sales data rows
        for meal, qty, amt in rows:
            row_frame = tk.Frame(scrollable_frame, bg=BG_COLOR)
            row_frame.pack(fill=tk.X, pady=2)

            tk.Label(row_frame, text=meal, font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=25, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=str(qty), font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=10, anchor="w").pack(side=tk.LEFT, padx=5)
            tk.Label(row_frame, text=f"{amt:.2f}", font=FONT_SMALL, bg=BG_COLOR,
                     fg=FG_COLOR, width=15, anchor="w").pack(side=tk.LEFT, padx=5)

        # Total row
        total_frame = tk.Frame(scrollable_frame, bg=BG_COLOR)
        total_frame.pack(fill=tk.X, pady=(20, 10))

        tk.Label(total_frame, text="TOTAL SALES:", font=('Poppins', 14, 'bold'),
                 bg=BG_COLOR, fg=ACCENT_COLOR, anchor="e").pack(side=tk.LEFT, padx=5, expand=True)
        tk.Label(total_frame, text=f"ksh {total:.2f}", font=('Poppins', 14, 'bold'),
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
            btn_frame, text="Close",
            command=sales_window.destroy,
            bg=BUTTON_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
            activebackground=ACCENT_COLOR, bd=0, padx=15, pady=5
        ).pack(side=tk.LEFT, padx=10)

    def clear_today_sales(self, sales_window=None):
        def do_clear():
            date = datetime.now().strftime('%Y-%m-%d')
            self.sales_cursor.execute('DELETE FROM sales WHERE date=?', (date,))
            self.sales_conn.commit()
            messagebox.showinfo("Cleared", "Today's sales have been cleared.")
            if sales_window:
                sales_window.destroy()
                self.show_daily_sales()

        # Prompt for manager password
        pw_window = tk.Toplevel(self.root)
        pw_window.title("Manager Password Required")
        pw_window.geometry("400x200")
        pw_window.configure(bg=BG_COLOR)
        pw_window.transient(self.root)
        pw_window.grab_set()

        tk.Label(pw_window, text="Enter manager password to clear today's sales:",
                 font=FONT_MEDIUM, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)

        pw_var = tk.StringVar()
        pw_entry = tk.Entry(pw_window, textvariable=pw_var, show="*", font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        pw_entry.pack(pady=10, ipady=5)
        pw_entry.focus_set()

        btn_frame = tk.Frame(pw_window, bg=BG_COLOR)
        btn_frame.pack(pady=10)

        def check_pw():
            if pw_var.get() == self.credentials.get("manager_password", "manager123"):
                pw_window.destroy()
                do_clear()
            else:
                messagebox.showerror("Error", "Incorrect manager password. Cannot clear today's sales.")
                pw_window.lift()
                pw_entry.delete(0, tk.END)

        tk.Button(btn_frame, text="OK", command=check_pw,
                  bg=BUTTON_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=20, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Cancel", command=pw_window.destroy,
                  bg=ERROR_COLOR, fg=FG_COLOR, font=FONT_MEDIUM,
                  padx=20, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)

    def confirm_exit(self):
        if messagebox.askyesno("Exit", "Are you sure you want to exit?", parent=self.root):
            self.root.destroy()

    def confirm_logout(self):
        if messagebox.askyesno("Logout", "Are you sure you want to logout?", parent=self.root):
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
        title_marquee = Marquee(main_container, text="Welcome to Furaha Hotel Management System")
        title_marquee.pack(fill=tk.X, pady=(0, 20))

        # Login frame
        login_frame = tk.Frame(main_container, bg=BG_COLOR, bd=0)
        login_frame.pack(expand=True)

        # Login box
        login_box = tk.LabelFrame(login_frame, text="Login", font=('Poppins', 20, 'bold'),
                                  bg=BG_COLOR, fg=ACCENT_COLOR, bd=0)
        login_box.pack(padx=50, pady=20, ipadx=30, ipady=20)

        # Username
        tk.Label(login_box, text="Username:", bg=BG_COLOR, fg=FG_COLOR,
                 font=FONT_LARGE).grid(row=0, column=0, padx=10, pady=10, sticky=tk.E)
        username_var = tk.StringVar()
        username_entry = tk.Entry(login_box, font=FONT_LARGE, bd=2,
                                  bg='#2a2a40', fg=FG_COLOR, insertbackground=FG_COLOR,
                                  textvariable=username_var)
        username_entry.grid(row=0, column=1, padx=10, pady=10, ipady=5, sticky="ew")

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
        tk.Button(login_box, text="Change Login", font=FONT_MEDIUM,
                  bg=BG_COLOR, fg=ACCENT_COLOR, bd=0,
                  activebackground=BG_COLOR, activeforeground=FG_COLOR,
                  command=self.show_change_credentials
                  ).grid(row=3, column=0, columnspan=2, pady=10)

    def reset_login(self, username_var, password_var):
        username_var.set("")
        password_var.set("")

    def check_login(self, username, password):
        if username == self.credentials["username"] and password == self.credentials["password"]:
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Logging In...")
            progress_window.geometry("400x100")
            progress_window.configure(bg=BG_COLOR)
            progress_window.transient(self.root)
            progress_window.grab_set()

            tk.Label(progress_window, text="Logging in, please wait...",
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

    def show_change_credentials(self):
        change_window = tk.Toplevel(self.root)
        change_window.title("Change Login Credentials")
        change_window.geometry("500x400")
        change_window.configure(bg=BG_COLOR)
        change_window.transient(self.root)
        change_window.grab_set()

        # Current credentials
        current_frame = tk.LabelFrame(change_window, text="Current Credentials",
                                      font=FONT_LARGE, bg=BG_COLOR, fg=ACCENT_COLOR)
        current_frame.pack(pady=10, padx=20, fill=tk.X)

        tk.Label(current_frame, text=f"Username: {self.credentials['username']}",
                 bg=BG_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(padx=10, pady=5)
        tk.Label(current_frame, text=f"Password: {'*' * len(self.credentials['password'])}",
                 bg=BG_COLOR, fg=FG_COLOR, font=FONT_MEDIUM).pack(padx=10, pady=5)

        # New credentials
        new_frame = tk.LabelFrame(change_window, text="New Credentials",
                                  font=FONT_LARGE, bg=BG_COLOR, fg=ACCENT_COLOR)
        new_frame.pack(pady=10, padx=20, fill=tk.X)

        # New username
        tk.Label(new_frame, text="New Username:", bg=BG_COLOR, fg=FG_COLOR,
                 font=FONT_MEDIUM).grid(row=0, column=0, padx=10, pady=10, sticky=tk.E)
        new_username_var = tk.StringVar()
        new_username_entry = tk.Entry(new_frame, font=FONT_MEDIUM, bg='#2a2a40',
                                      fg=FG_COLOR, textvariable=new_username_var)
        new_username_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        # New password
        tk.Label(new_frame, text="New Password:", bg=BG_COLOR, fg=FG_COLOR,
                 font=FONT_MEDIUM).grid(row=1, column=0, padx=10, pady=10, sticky=tk.E)
        new_password_var = tk.StringVar()
        new_password_entry = tk.Entry(new_frame, font=FONT_MEDIUM, bg='#2a2a40',
                                      fg=FG_COLOR, textvariable=new_password_var, show="*")
        new_password_entry.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        # Confirm password
        tk.Label(new_frame, text="Confirm Password:", bg=BG_COLOR, fg=FG_COLOR,
                 font=FONT_MEDIUM).grid(row=2, column=0, padx=10, pady=10, sticky=tk.E)
        confirm_password_var = tk.StringVar()
        confirm_password_entry = tk.Entry(new_frame, font=FONT_MEDIUM, bg='#2a2a40',
                                          fg=FG_COLOR, textvariable=confirm_password_var, show="*")
        confirm_password_entry.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        # Admin password verification
        tk.Label(new_frame, text="Current Admin Password:", bg=BG_COLOR, fg=FG_COLOR,
                 font=FONT_MEDIUM).grid(row=3, column=0, padx=10, pady=10, sticky=tk.E)
        admin_password_var = tk.StringVar()
        admin_password_entry = tk.Entry(new_frame, font=FONT_MEDIUM, bg='#2a2a40',
                                        fg=FG_COLOR, textvariable=admin_password_var, show="*")
        admin_password_entry.grid(row=3, column=1, padx=10, pady=10, sticky="ew")

        # Buttons
        button_frame = tk.Frame(change_window, bg=BG_COLOR)
        button_frame.pack(pady=20)

        def save_new_credentials():
            new_username = new_username_var.get()
            new_password = new_password_var.get()
            confirm_password = confirm_password_var.get()
            admin_password = admin_password_var.get()

            if not new_username or not new_password:
                messagebox.showerror("Error", "All fields are required")
                return

            if new_password != confirm_password:
                messagebox.showerror("Error", "Passwords do not match")
                return

            if admin_password != self.credentials["password"]:
                messagebox.showerror("Error", "Only the admin can change the username. Incorrect admin password.")
                return

            save_config(new_username, new_password)
            self.credentials["username"] = new_username
            self.credentials["password"] = new_password
            messagebox.showinfo("Success", "Credentials updated successfully")
            change_window.destroy()

        tk.Button(button_frame, text="Save", font=FONT_MEDIUM,
                  bg=BUTTON_COLOR, fg=FG_COLOR, command=save_new_credentials,
                  padx=20, pady=5, activebackground=ACCENT_COLOR).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=change_window.destroy,
                  padx=20, pady=5, activebackground=HIGHLIGHT_COLOR).pack(side=tk.LEFT, padx=10)

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
        main_frame = tk.Frame(self.root, bg="#1e1e2e")
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
        customer_frame.grid(row=0, column=0, columnspan=4, sticky="ew", pady=5)

        tk.Label(customer_frame, text="Customer Name:",
                 font=FONT_MEDIUM, fg=ACCENT_COLOR, bg="#1e1e2e").pack(side=tk.LEFT, padx=5)

        self.customer_name_entry = tk.Entry(customer_frame, bd=2, width=30,
                                            font=FONT_MEDIUM, bg="#2a2a40", fg=FG_COLOR)
        self.customer_name_entry.pack(side=tk.LEFT, padx=5, ipady=3)

        tk.Button(customer_frame, text="Logout", font=FONT_MEDIUM,
                  bg=ERROR_COLOR, fg=FG_COLOR, command=self.confirm_logout,
                  padx=15, pady=3, activebackground=HIGHLIGHT_COLOR).pack(side=tk.RIGHT, padx=5)

        # Load meals from database
        db_meals = self.get_all_meals()
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
            canvas = tk.Canvas(frame, bg="#1e1e2e", highlightthickness=0)
            scrollbar = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
            scrollable_frame = tk.Frame(canvas, bg="#1e1e2e")

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
                    item_frame = tk.Frame(scrollable_frame, bg="#1e1e2e")
                    item_frame.pack(fill=tk.X, padx=5, pady=2)

                    tk.Label(item_frame, text=f"{item[:18]:<18} (ksh{price}):",
                             font=FONT_SMALL, bg="#1e1e2e", fg=FG_COLOR,
                             width=20, anchor="w").pack(side=tk.LEFT, padx=5)

                    entry = tk.Entry(item_frame, bd=1, bg="#2a2a40", fg=FG_COLOR,
                                     font=FONT_SMALL, width=6, justify=tk.CENTER)
                    entry.pack(side=tk.LEFT, padx=5)
                    self.meal_entries[category][item] = entry

        # Receipt frame
        bill_frame = tk.LabelFrame(main_frame, text="Receipt", font=FONT_MEDIUM,
                                   bg="#2a2a40", fg=ACCENT_COLOR, bd=2, relief=tk.GROOVE)
        bill_frame.grid(row=1, column=2, rowspan=2, sticky="nsew", padx=5, pady=5, ipadx=5)
        bill_frame.grid_rowconfigure(0, weight=1)
        bill_frame.grid_columnconfigure(0, weight=1)

        # Text widget for receipt
        self.bill_txt = tk.Text(bill_frame, bg="#2a2a40", fg=FG_COLOR,
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
        num_ent = tk.Entry(calc_frame, bd=1, bg="#2a2a40", fg=FG_COLOR,
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
        control_frame = tk.Frame(main_frame, bg="#1e1e2e")
        control_frame.grid(row=3, column=2, columnspan=2, sticky="nsew", padx=5, pady=5)

        tk.Label(control_frame, text="Tax:", font=FONT_MEDIUM,
                 fg=ACCENT_COLOR, bg="#1e1e2e").grid(row=0, column=0, padx=5, pady=2, sticky=tk.E)

        self.tax_btn_entry = tk.Entry(control_frame, bd=1, bg="#2a2a40", fg=FG_COLOR,
                                      font=FONT_MEDIUM, width=15, justify=tk.RIGHT)
        self.tax_btn_entry.grid(row=0, column=1, padx=5, pady=2)

        tk.Label(control_frame, text="Total:", font=FONT_MEDIUM,
                 fg=ACCENT_COLOR, bg="#1e1e2e").grid(row=1, column=0, padx=5, pady=2, sticky=tk.E)

        self.total_btn_entry = tk.Entry(control_frame, bd=1, bg="#2a2a40", fg=FG_COLOR,
                                        font=FONT_MEDIUM, width=15, justify=tk.RIGHT)
        self.total_btn_entry.grid(row=1, column=1, padx=5, pady=2)

        # Action buttons frame
        button_frame = tk.Frame(main_frame, bg="#1e1e2e")
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
            ("Reset", self.reset_all, ERROR_COLOR, FG_COLOR),
            ("Add Meal", self.add_new_meal_dialog, SUCCESS_COLOR, FG_COLOR),
            ("Remove Meal", self.remove_existing_meal_dialog, ERROR_COLOR, FG_COLOR)
        ]

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
        self.bill_txt.insert(tk.END, f"Customer: {customer_name}\n")
        self.bill_txt.insert(tk.END, "=" * 40 + "\n")

        items_selected = False
        sales_to_record = []

        try:
            for category, items in self.menu_items.items():
                # Skip if category doesn't exist in meal_entries
                if category not in self.meal_entries:
                    continue

                for item, price in items.items():
                    # Skip if item doesn't exist in the category
                    if item not in self.meal_entries[category]:
                        continue

                    qty = self.meal_entries[category][item].get().strip()
                    if qty:
                        qty = int(qty)
                        if qty > 0:
                            cost = qty * price
                            total_list.append(cost)
                            self.bill_txt.insert(tk.END, f"{item[:18]:<20}{qty:>5}{price:>8.2f}{cost:>9.2f}\n")
                            sales_to_record.append((item, qty, cost))
                            items_selected = True

            if items_selected:
                # Record all sales in the database
                for item, qty, cost in sales_to_record:
                    self.record_sale(item, qty, cost)

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

            if self.add_new_meal(category, name, price):
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
                if self.remove_meal(category, name):
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



    # ... (keep all previous imports and code until the mpesa_payment method)

    def mpesa_payment(self):
        mpesa_win = tk.Toplevel(self.root)
        mpesa_win.title("Mpesa Payment")
        mpesa_win.geometry("400x250")  # Reduced height since we removed reference field
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
        self.party_b = "174379"  # Using the same as business short code

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

            # Validate phone number (must be 10 digits starting with 0)
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
            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
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
                "AccountReference": "HotelPayment",  # Fixed reference since we removed the field
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

    # ... (keep the rest of the existing code)

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
        self.bill_txt.insert(tk.END, " BURUDANI CLUB ".center(40, "=") + "\n")
        self.bill_txt.insert(tk.END, "Jujacitymall, Thika Road\n".center(40) + "\n")
        self.bill_txt.insert(tk.END, "Contact: 0796939191\n".center(40) + "\n")
        self.bill_txt.insert(tk.END, "=" * 40 + "\n")


if __name__ == "__main__":
    root = tk.Tk()
    app = HotelApp(root)
    root.mainloop()