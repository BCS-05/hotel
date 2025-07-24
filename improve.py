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

CONFIG_FILE = "hotel_config.json"
DEFAULT_CREDENTIALS = {
    "username": "clin",
    "password": "1234"
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    else:
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CREDENTIALS, f)
        return DEFAULT_CREDENTIALS

def save_config(username, password):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"username": username, "password": password}, f)

class Marquee(tk.Label):
    def __init__(self, parent, text, **kwargs):
        super().__init__(parent, **kwargs)
        self.full_text = " " * 50 + text + " " * 50
        self.pos = 0
        self.delay = 100
        self.configure(font=('Arial', 30, 'bold'),
                       fg='yellow', bg="purple", bd=10, relief=tk.RIDGE)
        self.update_text()
        self.after(self.delay, self.scroll)

    def update_text(self):
        display_text = self.full_text[self.pos:self.pos+50]
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
        self.root.geometry("900x700")
        self.root.minsize(400, 400)
        self.root.configure(bg="purple")
        self.credentials = load_config()
        self.setup_sales_db()
        self.show_login_page()

    def setup_sales_db(self):
        self.conn = sqlite3.connect('sales.db')
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                meal TEXT,
                quantity INTEGER,
                amount REAL
            )
        ''')
        self.conn.commit()

    def record_sale(self, meal, quantity, amount):
        date = datetime.now().strftime('%Y-%m-%d')
        self.cursor.execute('INSERT INTO sales (date, meal, quantity, amount) VALUES (?, ?, ?, ?)',
                            (date, meal, quantity, amount))
        self.conn.commit()

    def show_daily_sales(self):
        date = datetime.now().strftime('%Y-%m-%d')
        self.cursor.execute('SELECT meal, SUM(quantity), SUM(amount) FROM sales WHERE date=? GROUP BY meal', (date,))
        rows = self.cursor.fetchall()
        self.cursor.execute('SELECT SUM(amount) FROM sales WHERE date=?', (date,))
        total = self.cursor.fetchone()[0]
        sales_window = tk.Toplevel(self.root)
        sales_window.title('Daily Sales Summary')
        sales_window.geometry('700x500')
        sales_window.minsize(350, 300)
        sales_window.configure(bg='#eaeaea')
        sales_window.resizable(True, True)
        tk.Label(sales_window, text=f"Sales Summary for {date}", font=('Segoe UI', 14, 'bold'), bg='#eaeaea', fg='#283655').pack(pady=10)
        frame = tk.Frame(sales_window, bg='#eaeaea')
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # Table headers
        tk.Label(frame, text="Meal", font=('Segoe UI', 12, 'bold'), bg='#eaeaea', fg='#1a2238', borderwidth=1, relief="solid", width=20).grid(row=0, column=0, sticky="nsew")
        tk.Label(frame, text="Qty Sold", font=('Segoe UI', 12, 'bold'), bg='#eaeaea', fg='#1a2238', borderwidth=1, relief="solid", width=10).grid(row=0, column=1, sticky="nsew")
        tk.Label(frame, text="Total (ksh)", font=('Segoe UI', 12, 'bold'), bg='#eaeaea', fg='#1a2238', borderwidth=1, relief="solid", width=15).grid(row=0, column=2, sticky="nsew")
        # Table rows
        for i, (meal, qty, amt) in enumerate(rows, start=1):
            tk.Label(frame, text=meal, font=('Segoe UI', 12), bg='#eaeaea', fg='#1a2238', borderwidth=1, relief="solid").grid(row=i, column=0, sticky="nsew")
            tk.Label(frame, text=str(qty), font=('Segoe UI', 12), bg='#eaeaea', fg='#1a2238', borderwidth=1, relief="solid").grid(row=i, column=1, sticky="nsew")
            tk.Label(frame, text=f"{amt:.2f}", font=('Segoe UI', 12), bg='#eaeaea', fg='#1a2238', borderwidth=1, relief="solid").grid(row=i, column=2, sticky="nsew")
        # Make columns expand
        for col in range(3):
            frame.grid_columnconfigure(col, weight=1)
        tk.Label(frame, text="", bg='#eaeaea').grid(row=len(rows)+1, column=0)
        tk.Label(frame, text=f"Total Sales: ksh {total if total else 0:.2f}", font=('Segoe UI', 13, 'bold'), bg='#eaeaea', fg='#f6c90e').grid(row=len(rows)+2, column=0, columnspan=3, sticky="w", pady=10)
        tk.Button(sales_window, text="Close", command=sales_window.destroy, bg="#283655", fg="#f6c90e", font=('Segoe UI', 11, 'bold')).pack(pady=10)

    def confirm_exit(self):
        if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            self.root.destroy()

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def show_login_page(self):
        self.clear_window()
        title_marquee = Marquee(self.root, text="Welcome to Hiram Hotel Management System")
        title_marquee.configure(bg="#283655", fg="#f6c90e")
        title_marquee.pack(side=tk.TOP, fill=tk.X, pady=10)

        main_frame = tk.Frame(self.root, bg="#eaeaea", bd=6, relief=tk.GROOVE)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        main_frame.pack_propagate(True)
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        login_lbl = tk.Label(main_frame, text="Login", bd=6, relief=tk.GROOVE,
                             anchor=tk.CENTER, bg="#21e6c1", fg="#1a2238",
                             font=('Segoe UI', 20, 'bold'))
        login_lbl.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        entry_frame = tk.LabelFrame(main_frame, text="Enter Details", bd=6,
                                   relief=tk.GROOVE, bg="#eaeaea",
                                   font=('Segoe UI', 15, 'bold'), fg="#1a2238")
        entry_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        entry_frame.grid_columnconfigure(0, weight=1)
        entry_frame.grid_columnconfigure(1, weight=2)

        username_var = tk.StringVar()
        tk.Label(entry_frame, text="Username:", bg="#eaeaea", fg="#1a2238",
                 font=("Segoe UI", 12, 'bold')).grid(row=0, column=0, padx=10, pady=10, sticky=tk.E)
        username_entry = tk.Entry(entry_frame, font=('Segoe UI', 12), bd=3,
                                  bg="#f6f6f6", fg="#1a2238", insertbackground="#1a2238", textvariable=username_var)
        username_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        password_var = tk.StringVar()
        tk.Label(entry_frame, text="Password:", bg="#eaeaea", fg="#1a2238",
                 font=("Segoe UI", 12, 'bold')).grid(row=1, column=0, padx=10, pady=10, sticky=tk.E)
        password_entry = tk.Entry(entry_frame, font=('Segoe UI', 12), bd=3,
                                  bg="#f6f6f6", fg="#1a2238", insertbackground="#1a2238", textvariable=password_var, show="*")
        password_entry.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        button_frame = tk.Frame(entry_frame, bg="#eaeaea")
        button_frame.grid(row=2, column=0, columnspan=2, pady=10)

        tk.Button(button_frame, text="Login", font=("Segoe UI", 12, 'bold'),
                  bg="#283655", fg="#f6c90e", bd=3, width=10,
                  activebackground="#f6c90e", activeforeground="#283655",
                  command=lambda: self.check_login(username_var.get(), password_var.get())
                  ).pack(side=tk.LEFT, padx=10)

        tk.Button(button_frame, text="Reset", font=("Segoe UI", 12, 'bold'),
                  bd=3, bg="#21e6c1", fg="#1a2238", width=10,
                  activebackground="#1a2238", activeforeground="#21e6c1",
                  command=lambda: self.reset_login(username_var, password_var)
                  ).pack(side=tk.LEFT, padx=10)

        tk.Button(entry_frame, text="Change Login", font=("Segoe UI", 10, 'bold'),
                  bg="#f6c90e", fg="#1a2238", bd=3,
                  activebackground="#283655", activeforeground="#f6c90e",
                  command=self.show_change_credentials
                  ).grid(row=3, column=0, columnspan=2, pady=10)

    def check_login(self, username, password):
        if username == self.credentials["username"] and password == self.credentials["password"]:
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Logging In...")
            progress_window.geometry("300x100")
            progress_window.transient(self.root)
            progress_window.grab_set()

            progress_bar = ttk.Progressbar(progress_window, orient="horizontal",
                                           length=200, mode="determinate")
            progress_bar.pack(pady=20)

            def simulate_login_progress():
                for i in range(101):
                    progress_bar['value'] = i
                    progress_window.update_idletasks()
                    time.sleep(0.01)
                progress_window.destroy()
                self.show_main_system()

            login_thread = threading.Thread(target=simulate_login_progress)
            login_thread.start()
        else:
            messagebox.showerror("Login Failed", "Invalid username or password. Please try again.")

    def reset_login(self, username_var, password_var):
        username_var.set("")
        password_var.set("")

    def show_change_credentials(self):
        change_window = tk.Toplevel(self.root)
        change_window.title("Change Login Credentials")
        change_window.geometry("400x300")
        change_window.configure(bg="aqua")
        change_window.transient(self.root)
        change_window.grab_set()

        current_frame = tk.LabelFrame(change_window, text="Current Credentials",
                                      font=("Arial", 10), bd=5, bg="lightgrey")
        current_frame.pack(pady=10, padx=10, fill=tk.X)

        tk.Label(current_frame, text=f"Username: {self.credentials['username']}", bg="lightgrey").pack(padx=5, pady=2)
        tk.Label(current_frame, text=f"Password: {'*' * len(self.credentials['password'])}", bg="lightgrey").pack(padx=5, pady=2)

        new_frame = tk.LabelFrame(change_window, text="New Credentials",
                                 font=("Arial", 10), bd=5, bg="lightgrey")
        new_frame.pack(pady=10, padx=10, fill=tk.X)

        new_username_var = tk.StringVar()
        tk.Label(new_frame, text="New Username:", bg="lightgrey").grid(row=0, column=0, padx=5, pady=5, sticky=tk.E)
        new_username_entry = tk.Entry(new_frame, textvariable=new_username_var)
        new_username_entry.grid(row=0, column=1, padx=5, pady=5)

        new_password_var = tk.StringVar()
        tk.Label(new_frame, text="New Password:", bg="lightgrey").grid(row=1, column=0, padx=5, pady=5, sticky=tk.E)
        new_password_entry = tk.Entry(new_frame, textvariable=new_password_var, show="*")
        new_password_entry.grid(row=1, column=1, padx=5, pady=5)

        confirm_password_var = tk.StringVar()
        tk.Label(new_frame, text="Confirm Password:", bg="lightgrey").grid(row=2, column=0, padx=5, pady=5, sticky=tk.E)
        confirm_password_entry = tk.Entry(new_frame, textvariable=confirm_password_var, show="*")
        confirm_password_entry.grid(row=2, column=1, padx=5, pady=5)

        button_frame = tk.Frame(change_window, bg="aqua")
        button_frame.pack(pady=10)

        def save_new_credentials():
            new_username = new_username_var.get()
            new_password = new_password_var.get()
            confirm_password = confirm_password_var.get()

            if not new_username or not new_password:
                messagebox.showerror("Error", "Username and password cannot be empty")
                return

            if new_password != confirm_password:
                messagebox.showerror("Error", "Passwords do not match")
                return

            save_config(new_username, new_password)
            self.credentials["username"] = new_username
            self.credentials["password"] = new_password
            messagebox.showinfo("Success", "Credentials updated successfully")
            change_window.destroy()

        tk.Button(button_frame, text="Save", bg="green", fg="white", command=save_new_credentials).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", bg="red", fg="white", command=change_window.destroy).pack(side=tk.LEFT, padx=5)

    def show_main_system(self):
        self.clear_window()
        title_marquee = Marquee(self.root, text="HOTEL MANAGEMENT SYSTEM")
        title_marquee.configure(bg="#283655", fg="#f6c90e")
        title_marquee.grid(row=0, column=0, columnspan=4, sticky="ew", padx=10, pady=10)

        main_frame = tk.Frame(self.root, bg="lightgrey")
        main_frame.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=10, pady=10)

        self.root.grid_rowconfigure(1, weight=1)
        for i in range(4):
            self.root.grid_columnconfigure(i, weight=1)
        for i in range(4):
            main_frame.grid_columnconfigure(i, weight=1)
        for i in range(5):
            main_frame.grid_rowconfigure(i, weight=1)

        customer_frame = tk.Frame(main_frame, bg="lightgrey")
        customer_frame.grid(row=0, column=0, columnspan=4, sticky="ew", pady=5)

        tk.Label(customer_frame, text="Customer Name:", font=('Arial', 12), fg="blue", bg="lightgrey"
                ).pack(side=tk.LEFT, padx=5)
        customer_name_entry = tk.Entry(customer_frame, bd=5, width=20, font=('Arial', 12))
        customer_name_entry.pack(side=tk.LEFT, padx=5)

        tk.Button(customer_frame, text="Logout", font=("Arial", 10), bg="red", fg="white",
                  command=self.show_login_page
                  ).pack(side=tk.RIGHT, padx=5)

        menu_items = {
            "Cold Drinks": {
                "Soda": 60,
                "Water": 50,
                "Juice": 40,
                "Ice": 25,
                "Wine": 200
            },
            "Hot Drinks": {
                "Coffee": 30,
                "Milk": 25,
                "White Tea": 40,
                "Cocoa Tea": 35,
                "Black Tea": 20
            },
            "Foods": {
                "Matooke": 80,
                "Rice": 70,
                "Ugali": 50,
                "chips": 125,
                "Posho": 60
            },
            "Sauce": {
                "Meat": 200,
                "Beans": 35,
                "Fish": 150,
                "Hot Sauce": 60,
                "Vegetables": 45
            }
        }

        frames = {}
        entries = {}

        for idx, (category, items) in enumerate(menu_items.items()):
            row = (idx // 2) + 1
            col = idx % 2
            frame = tk.LabelFrame(main_frame, text=category, fg='blue',
                                 font=('Arial', 12), bd=7, relief=tk.GROOVE, bg="lightgrey")
            frame.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            frames[category] = frame

            main_frame.grid_columnconfigure(col, weight=1)
            main_frame.grid_rowconfigure(row, weight=1)

            row_idx = 0
            entries[category] = {}
            for item, price in items.items():
                tk.Label(frame, text=f"{item} (ksh{price}):",
                         font=("Arial", 10), fg='magenta', bg="lightgrey"
                         ).grid(row=row_idx, column=0, padx=5, pady=2, sticky=tk.W)

                entry = tk.Entry(frame, bd=5, bg='aqua', font=('Arial', 10), width=8)
                entry.grid(row=row_idx, column=1, padx=5, pady=2)
                entries[category][item] = entry

                row_idx += 1

        bill_frame = tk.LabelFrame(main_frame, text="Receipt", font=("Arial", 12),
                                  bg="lightgrey", bd=8, relief=tk.GROOVE)
        bill_frame.grid(row=1, column=2, rowspan=2, sticky="nsew", padx=5, pady=5)

        y_scroll = tk.Scrollbar(bill_frame, orient="vertical")
        bill_txt = tk.Text(bill_frame, bg="white", yscrollcommand=y_scroll.set, width=30, height=15)
        y_scroll.config(command=bill_txt.yview)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        bill_txt.pack(fill=tk.BOTH, expand=True)

        def default_bill():
            bill_txt.delete(1.0, tk.END)
            bill_txt.insert(tk.END, "Burudani Club\n")
            bill_txt.insert(tk.END, "Jujacitymall, Thika Road\n")
            bill_txt.insert(tk.END, "Contact: 0796939191\n")
            bill_txt.insert(tk.END, "=======================\n")

        default_bill()

        calc_frame = tk.LabelFrame(main_frame, text="Calculator",
                                  font=("Arial", 12), bg="lightgrey",
                                  bd=8, relief=tk.GROOVE)
        calc_frame.grid(row=1, column=3, rowspan=2, sticky="nsew", padx=5, pady=5)

        calc_var = tk.StringVar()
        num_ent = tk.Entry(calc_frame, bd=4, bg="white",
                           textvariable=calc_var, font=("Arial", 12),
                           width=15, justify=tk.RIGHT)
        num_ent.grid(row=0, column=0, columnspan=4, padx=5, pady=5)

        def button_click(char):
            current = calc_var.get()
            if char == "=":
                try:
                    result = str(eval(current))
                    calc_var.set(result)
                except Exception:
                    calc_var.set("Error")
            elif char == "C":
                calc_var.set("")
            else:
                calc_var.set(current + char)

        buttons = [
            ("7", 1, 0), ("8", 1, 1), ("9", 1, 2), ("+", 1, 3),
            ("4", 2, 0), ("5", 2, 1), ("6", 2, 2), ("-", 2, 3),
            ("1", 3, 0), ("2", 3, 1), ("3", 3, 2), ("*", 3, 3),
            ("0", 4, 0), (".", 4, 1), ("C", 4, 2), ("/", 4, 3),
            ("=", 5, 0, 4)
        ]

        for btn in buttons:
            if len(btn) == 4:
                text, row, col, colspan = btn
                button = tk.Button(calc_frame, text=text, bd=5,
                                   width=2, font=('Arial', 12),
                                   command=lambda t=text: button_click(t))
                button.grid(row=row, column=col, columnspan=colspan, sticky="nsew", padx=2, pady=2)
            else:
                text, row, col = btn
                button = tk.Button(calc_frame, text=text, bd=5,
                                   width=2, font=('Arial', 12),
                                   command=lambda t=text: button_click(t))
                button.grid(row=row, column=col, padx=2, pady=2)

        control_frame = tk.Frame(main_frame, bg="lightgrey")
        control_frame.grid(row=3, column=2, columnspan=2, sticky="ew", padx=5, pady=5)

        tk.Label(control_frame, text="Tax:", font=("Arial", 12), fg="purple", bg="lightgrey"
                 ).grid(row=0, column=0, padx=5, pady=2, sticky=tk.E)
        tax_btn_entry = tk.Entry(control_frame, bd=5, bg='aqua', font=('Arial', 12), width=15)
        tax_btn_entry.grid(row=0, column=1, padx=5, pady=2)

        tk.Label(control_frame, text="Total:", font=("Arial", 12), fg="purple", bg="lightgrey"
                 ).grid(row=1, column=0, padx=5, pady=2, sticky=tk.E)
        total_btn_entry = tk.Entry(control_frame, bd=5, bg='aqua', font=('Arial', 12), width=15)
        total_btn_entry.grid(row=1, column=1, padx=5, pady=2)

        def calculate_total():
            customer_name = customer_name_entry.get().strip()
            if not customer_name:
                messagebox.showerror("Error", "Please enter customer name")
                return

            total_list = []
            bill_txt.delete(1.0, tk.END)
            default_bill()
            bill_txt.insert(tk.END, f"Customer: {customer_name}\n")
            bill_txt.insert(tk.END, "=======================\n")

            items_selected = False
            sales_to_record = []

            try:
                for category, items in menu_items.items():
                    for item, price in items.items():
                        qty = entries[category][item].get().strip()
                        if qty:
                            qty = int(qty)
                            if qty > 0:
                                cost = qty * price
                                total_list.append(cost)
                                bill_txt.insert(tk.END, f"{item} ({qty}x): ksh{cost}\n")
                                sales_to_record.append((item, qty, cost))
                                items_selected = True

                if items_selected:
                    # Record all sales in the database
                    for item, qty, cost in sales_to_record:
                        self.record_sale(item, qty, cost)

                    total_cost = sum(total_list)
                    tax = total_cost * 0.02
                    grand_total = total_cost + tax

                    bill_txt.insert(tk.END, "=======================\n")
                    bill_txt.insert(tk.END, f"Subtotal: ksh{total_cost}\n")
                    bill_txt.insert(tk.END, f"Tax: ksh{tax:.2f}\n")
                    bill_txt.insert(tk.END, f"Grand Total: ksh{grand_total:.2f}\n")
                    bill_txt.insert(tk.END, "=======================\n")

                    tax_btn_entry.delete(0, tk.END)
                    tax_btn_entry.insert(0, f"ksh{tax:.2f}")
                    total_btn_entry.delete(0, tk.END)
                    total_btn_entry.insert(0, f"ksh{grand_total:.2f}")
                else:
                    bill_txt.insert(tk.END, "No items selected.\n")
                    tax_btn_entry.delete(0, tk.END)
                    total_btn_entry.delete(0, tk.END)
            except ValueError:
                messagebox.showerror("Error", "Please enter valid quantities (whole numbers)")
                bill_txt.insert(tk.END, "No items selected.\n")
                tax_btn_entry.delete(0, tk.END)
                total_btn_entry.delete(0, tk.END)

        def generate_bill_with_items():
            customer_name = customer_name_entry.get().strip()
            if not customer_name:
                messagebox.showerror("Error", "Please enter customer name")
                return False

            bill_txt.delete(1.0, tk.END)
            bill_txt.insert(tk.END, "\n")
            bill_txt.insert(tk.END, f"{' BURUDANI CLUB ':-^20}\n")
            bill_txt.insert(tk.END, f"{' Jujacitymall, Thika Road ':^40}\n")
            bill_txt.insert(tk.END, f"{' Contact: 0796939191 ':^40}\n")
            bill_txt.insert(tk.END, f"{'':-^40}\n")
            bill_txt.insert(tk.END, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            bill_txt.insert(tk.END, f"Customer: {customer_name}\n")
            bill_txt.insert(tk.END, f"{'':-^40}\n")

            total_list = []
            items_selected = False

            try:
                for category, items in menu_items.items():
                    for item, price in items.items():
                        qty = entries[category][item].get().strip()
                        if qty:
                            qty = int(qty)
                            if qty > 0:
                                cost = qty * price
                                total_list.append(cost)
                                line = f"{item[:18]:<18} {qty:>2}x {cost:>7,.2f}"
                                bill_txt.insert(tk.END, line + "\n")
                                items_selected = True

                if items_selected:
                    total_cost = sum(total_list)
                    tax = total_cost * 0.02
                    grand_total = total_cost + tax

                    bill_txt.insert(tk.END, f"{'':-^40}\n")
                    bill_txt.insert(tk.END, f"{'Subtotal:':<30}ksh{total_cost:>9,.2f}\n")
                    bill_txt.insert(tk.END, f"{'Tax (2%):':<30}ksh{tax:>9,.2f}\n")
                    bill_txt.insert(tk.END, f"{'':-^40}\n")
                    bill_txt.insert(tk.END, f"{'GRAND TOTAL:':<30}ksh{grand_total:>9,.2f}\n")
                    bill_txt.insert(tk.END, f"{'':=^40}\n")
                    bill_txt.insert(tk.END, "\nThank you for your business!\n")

                    tax_btn_entry.delete(0, tk.END)
                    tax_btn_entry.insert(0, f"ksh{tax:,.2f}")
                    total_btn_entry.delete(0, tk.END)
                    total_btn_entry.insert(0, f"ksh{grand_total:,.2f}")
                    return True
                else:
                    bill_txt.insert(tk.END, "No items selected.\n")
                    tax_btn_entry.delete(0, tk.END)
                    total_btn_entry.delete(0, tk.END)
                    return False
            except ValueError:
                messagebox.showerror("Error", "Please enter valid quantities (whole numbers)")
                total_btn_entry.delete(0, tk.END)
                return False

        def print_receipt():
            if not generate_bill_with_items():
                return

            bill_content = bill_txt.get("1.0", tk.END)
            try:
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp:
                    tmp.write(bill_content)
                    tmp_path = tmp.name
                if os.name == 'nt':
                    os.startfile(tmp_path, "print")
                    messagebox.showinfo("Printing", "Receipt sent to printer!")
                elif os.name == 'posix':
                    if subprocess.call(['lp', tmp_path]) == 0:
                        messagebox.showinfo("Printing", "Receipt sent to printer!")
                    else:
                        messagebox.showerror("Error", "Failed to send to printer")
                else:
                    messagebox.showerror("Error", "Printing not supported on this platform")
                threading.Timer(5.0, os.unlink, args=[tmp_path]).start()
            except Exception as e:
                messagebox.showerror("Print Error", f"Failed to print receipt:\n{str(e)}")

        def reset_all():
            customer_name_entry.delete(0, tk.END)
            for category in entries:
                for item in entries[category]:
                    entries[category][item].delete(0, tk.END)
            tax_btn_entry.delete(0, tk.END)
            total_btn_entry.delete(0, tk.END)
            calc_var.set("")
            bill_txt.delete(1.0, tk.END)
            default_bill()

        button_frame = tk.Frame(main_frame, bg="lightgrey")
        button_frame.grid(row=4, column=0, columnspan=4, pady=10)

        tk.Button(button_frame, text="Print Receipt", font=("Arial", 10), bg="purple", fg="white",
                  bd=1, relief=tk.GROOVE, command=print_receipt
                  ).pack(side=tk.LEFT, padx=5)

        tk.Button(button_frame, text="Total", font=("Arial", 10), bg="purple", fg="white",
                  bd=1, relief=tk.GROOVE, command=calculate_total
                  ).pack(side=tk.LEFT, padx=5)

        tk.Button(button_frame, text="Show Daily Sales", font=("Arial", 10), bg="#21e6c1", fg="#1a2238",
                  bd=1, relief=tk.GROOVE, command=self.show_daily_sales
                  ).pack(side=tk.LEFT, padx=5)

        tk.Button(button_frame, text="Reset", font=("Arial", 10), bg="purple", fg="white",
                  bd=1, relief=tk.GROOVE, command=reset_all
                  ).pack(side=tk.LEFT, padx=5)

        tk.Button(button_frame, text="Exit", font=("Arial", 10), bg="red", fg="white",
                  bd=1, relief=tk.GROOVE, command=self.confirm_exit
                  ).pack(side=tk.LEFT, padx=5)

if __name__ == "__main__":
    root = tk.Tk()
    app = HotelApp(root)
    root.mainloop()
