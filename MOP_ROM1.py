#!/usr/bin/env python
# coding: utf-8

# In[ ]:


#!/usr/bin/env python
# coding: utf-8

import os, sys, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkcalendar import DateEntry
import pandas as pd, pulp, requests, json, hashlib
from datetime import datetime, timedelta
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(__file__) if '__file__' in globals() else os.getcwd()
    return os.path.join(base_path, relative_path)

# =========================================================
# AUTHENTICATION WINDOW (GitHub JSON with hashes)
# =========================================================
class AuthWindow:
    def __init__(self, root, on_success):
        self.root = root
        self.root.title("Login")
        self.on_success = on_success

        # Explicit naming to match check_login
        tk.Label(root, text="Username").grid(row=0, column=0)
        self.user_entry = tk.Entry(root)
        self.user_entry.grid(row=0, column=1)

        tk.Label(root, text="Password").grid(row=1, column=0)
        self.pass_entry = tk.Entry(root, show="*")
        self.pass_entry.grid(row=1, column=1)

        tk.Label(root, text="Passkey").grid(row=2, column=0)
        self.key_entry = tk.Entry(root, show="*")
        self.key_entry.grid(row=2, column=1)

        tk.Button(root, text="Login", command=self.check_login).grid(row=3, column=0, columnspan=2)

    def check_login(self):
        username = self.user_entry.get()
        password = self.pass_entry.get()
        passkey = self.key_entry.get()

        try:
            # 🔗 Fetch JSON licence file from GitHub
            url = "https://raw.githubusercontent.com/tawandamukarati/MOP_ROM_PlanningTool/main/userpage.json"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # --- Licence check with decryption ---
            from cryptography.fernet import Fernet
            FERNET_KEY = b"oMSJG6m1FUmY4Rm4BznKQq3tSd6d99GwH0s6KN46V8k="  # same key used to encrypt JSON
            cipher = Fernet(FERNET_KEY)

            licence = data["licence"]
            valid_until_dec = cipher.decrypt(licence["valid_until_enc"].encode()).decode()
            active_dec = cipher.decrypt(licence["active_enc"].encode()).decode()

            if active_dec.lower() != "true":
                messagebox.showerror("Access Denied", "Licence inactive")
                return
            if datetime.now().strftime("%Y-%m-%d") > valid_until_dec:
                messagebox.showerror("Access Denied", "Licence expired")
                return

            # --- User check ---
            for user in data["users"]:
                if user["username"] == username:
                    pw_hash = hashlib.sha256(password.encode()).hexdigest()
                    pk_hash = hashlib.sha256(passkey.encode()).hexdigest()
                    if pw_hash == user["password_hash"] and pk_hash == user["passkey_hash"]:
                        self.root.destroy()
                        self.on_success()
                        return

            messagebox.showerror("Access Denied", "Invalid credentials")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to validate licence:\n{e}")

# =========================================================
# MAIN GUI CLASS
# =========================================================
class RehandleFeedPlanner:
    def __init__(self, root):
        self.root = root
        self.root.title("Weekly Rehandle & Daily Feed Planner")
        self.root.geometry("1800x1000")

        self.df = pd.DataFrame()
        self.feed_targets_df = pd.DataFrame()
        self.performance_df = pd.DataFrame()
        self.rehandle_results = pd.DataFrame()
        self.feed_results = pd.DataFrame()
        self.csv_folder = None

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)

        tabs = {
            "Load Data": "load_tab",
            "Weekly Rehandle": "rehandle_tab",
            "Daily Feed Targets": "feed_target_tab",
            "Feed Results": "feed_result_tab",
            "Summary & Variance Chart": "summary_tab",
            "Inventory Projection": "inventory_tab"
        }
        for name, attr in tabs.items():
            frame = ttk.Frame(self.notebook)
            setattr(self, attr, frame)
            self.notebook.add(frame, text=name)

        self.build_load_tab()
        self.build_rehandle_tab()
        self.build_feed_target_tab()
        self.build_feed_result_tab()
        self.build_summary_tab()
        self.build_inventory_tab()

    # --- Helpers ---
    def load_csv(self, default_filename, target_attr, callback=None):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")]) or resource_path(default_filename)
        df = pd.read_csv(file_path)
        setattr(self, target_attr, df)
        self.csv_folder = os.path.dirname(file_path)
        if callback: callback()
        messagebox.showinfo("Loaded", f"{os.path.basename(file_path)} loaded successfully.")

    def build_treeview(self, parent, columns, width=150, height=14):
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=height)
        for col in columns:
            tree.heading(col, text=col); tree.column(col, width=width)
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        return tree

    # --- Load Tab ---
    def build_load_tab(self):
        top = ttk.Frame(self.load_tab); top.pack(fill="x", padx=10, pady=10)
        ttk.Label(top, text="Planning Start Date").grid(row=0, column=0, padx=5)
        self.start_date = DateEntry(top, width=15, date_pattern='dd-mm-yyyy'); self.start_date.grid(row=0, column=1, padx=5)

        ttk.Button(top, text="Load Inventory CSV",
                   command=lambda: self.load_csv("stockpiles_29052026.csv", "df", self.after_inventory_load)).grid(row=1, column=0, padx=10, pady=5)
        ttk.Button(top, text="Load Feed Targets CSV",
                   command=lambda: self.load_csv("Feed_Targets.csv", "feed_targets_df", self.display_feed_targets)).grid(row=1, column=1, padx=10, pady=5)
        ttk.Button(top, text="Load Plant Performance CSV",
                   command=lambda: self.load_csv("Plant_Performance.csv", "performance_df", self.compare_plan_vs_actual)).grid(row=1, column=2, padx=10, pady=5)

    def after_inventory_load(self):
        self.df["Tonnes"] = self.df["Tonnes"].astype(float)
        self.refresh_mop_listbox()
        self.update_inventory_projection()

        # --- Rehandle Tab ---
    def build_rehandle_tab(self):
        left = ttk.LabelFrame(self.rehandle_tab, text="Available MOP Stockpiles")
        left.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.mop_listbox = tk.Listbox(left, selectmode=tk.MULTIPLE, width=70)
        self.mop_listbox.pack(fill="both", expand=True)

        middle = ttk.LabelFrame(self.rehandle_tab, text="Weekly Rehandle Targets")
        middle.pack(side="left", fill="y", padx=10, pady=10)
        labels = ["Weekly ROMP Target", "Weekly ROMS Target", "Max Daily Rehandle", "Max MOPs to Use"]
        entries = []
        for i, lbl in enumerate(labels):
            ttk.Label(middle, text=lbl).grid(row=i, column=0, sticky="w", pady=5)
            e = ttk.Entry(middle); e.grid(row=i, column=1, pady=5); entries.append(e)
        self.weekly_romp_entry, self.weekly_roms_entry, self.max_daily_rehandle_entry, self.max_mops_entry = entries
        ttk.Button(middle, text="Run Weekly Rehandle Plan", command=self.run_rehandle_plan).grid(row=4, column=0, columnspan=2, pady=20)

        right = ttk.LabelFrame(self.rehandle_tab, text="Daily Rehandle Schedule")
        right.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.rehandle_tree = self.build_treeview(right, ("Date","From","To","Tonnes","Grade","Grade_bin"), width=120)

    def refresh_mop_listbox(self):
        self.mop_listbox.delete(0, tk.END)
        if self.df.empty or "Location" not in self.df.columns: return
        mop_df = self.df.copy(); mop_df["Location"] = mop_df["Location"].astype(str).str.strip().str.upper()
        mop_df = mop_df[mop_df["Location"] == "MOP"]
        for _, row in mop_df.iterrows():
            text = f"{row['Name']} | Bin: {row['Grade_bin']} | Tonnes: {row['Tonnes']:.0f} | Grade: {row['Grade (g/t)']:.2f}"
            self.mop_listbox.insert(tk.END, text)

    def run_rehandle_plan(self):
        if self.df.empty:
            messagebox.showwarning("No Data", "Load Inventory CSV first."); return
        try:
            weekly_romp = float(self.weekly_romp_entry.get())
            weekly_roms = float(self.weekly_roms_entry.get())
            max_daily = float(self.max_daily_rehandle_entry.get())
            max_mops = int(self.max_mops_entry.get()) if self.max_mops_entry.get().strip() else None
        except:
            messagebox.showerror("Invalid Input", "Please enter valid numeric targets."); return

        horizon, start_date = 7, datetime.strptime(self.start_date.get(), "%d-%m-%Y")
        mop_df = self.df.copy(); mop_df["Location"] = mop_df["Location"].astype(str).str.strip().str.upper()
        mop_df = mop_df[mop_df["Location"] == "MOP"].reset_index(drop=True)

        selected = self.mop_listbox.curselection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select MOP stockpiles to rehandle."); return
        selected_df = mop_df.iloc[list(selected)].copy(); selected_df["Tonnes"] = selected_df["Tonnes"].astype(float)

        results, bins = [], selected_df["Grade_bin"].unique()
        daily_romp, daily_roms = weekly_romp / horizon, weekly_roms / horizon
        bin_groups = {b: selected_df[selected_df["Grade_bin"] == b].copy() for b in bins}

        for day in range(horizon):
            current_date = (start_date + timedelta(days=day)).strftime("%d-%m-%Y")
            romp_remaining, roms_remaining, moved_today, mops_used_today = daily_romp, daily_roms, 0, set()
            for binval, bin_df in bin_groups.items():
                if bin_df.empty: continue
                for idx, row in bin_df.iterrows():
                    if max_mops and len(mops_used_today) >= max_mops and row["Name"] not in mops_used_today: continue
                    tonnes, grade, stockpile = row["Tonnes"], row["Grade (g/t)"], row["Name"]
                    if tonnes <= 0: continue
                    for dest, share in [("ROMP", romp_remaining/len(bins)), ("ROMS", roms_remaining/len(bins))]:
                        if share > 0 and moved_today < max_daily and bin_groups[binval].at[idx, "Tonnes"] > 0:
                            move = min(bin_groups[binval].at[idx, "Tonnes"], share, max_daily - moved_today)
                            if move > 0:
                                results.append([current_date, stockpile, dest, round(move, 2), round(grade, 3), binval])
                                bin_groups[binval].at[idx, "Tonnes"] -= move
                                moved_today += move; mops_used_today.add(stockpile)

        self.rehandle_tree.delete(*self.rehandle_tree.get_children())
        for row in results: self.rehandle_tree.insert("", "end", values=row)
        self.rehandle_results = pd.DataFrame(results, columns=["Date","From","To","Tonnes","Grade","Grade_bin"])
        messagebox.showinfo("Complete", "Weekly rehandle plan generated successfully.")
        file_path = os.path.join(self.csv_folder or os.getcwd(), f"RehandlePlan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        self.rehandle_results.to_csv(file_path, index=False)
        messagebox.showinfo("Saved", f"Rehandle plan saved to:\n{file_path}")

    # --- Feed Target Tab ---
    def build_feed_target_tab(self):
        self.feed_target_tree = self.build_treeview(self.feed_target_tab,
            ("Date", "Feed Tonnes", "Target Grade", "ROMP %", "ROMS %"), width=180)
        ttk.Label(self.feed_target_tab, text="Minimum Stockpile Feed Tonnes").pack(pady=5)
        self.minimum_feed_tonnes_entry = ttk.Entry(self.feed_target_tab, width=12)
        self.minimum_feed_tonnes_entry.insert(0, "0"); self.minimum_feed_tonnes_entry.pack(pady=5)
        ttk.Button(self.feed_target_tab, text="Run Feed Plan", command=self.run_feed_plan).pack(pady=10)

    def display_feed_targets(self):
        self.feed_target_tree.delete(*self.feed_target_tree.get_children())
        if self.feed_targets_df.empty: return
        start_date = datetime.strptime(self.start_date.get(), "%d-%m-%Y")
        for idx, row in self.feed_targets_df.iterrows():
            date_value = (start_date + timedelta(days=idx)).strftime("%d-%m-%Y")
            total_feed = row["ROMP Tonnes"] + row["ROMS Tonnes"]
            romp_pct = (row["ROMP Tonnes"] / total_feed * 100) if total_feed > 0 else 0
            roms_pct = (row["ROMS Tonnes"] / total_feed * 100) if total_feed > 0 else 0
            self.feed_target_tree.insert("", "end",
                values=(date_value, total_feed, row["Target Grade"], f"{romp_pct:.1f}", f"{roms_pct:.1f}"))

        # --- Feed Result Tab ---
    def build_feed_result_tab(self):
        self.feed_result_tree = self.build_treeview(
            self.feed_result_tab,
            ("Date", "Feed Point", "Stockpile", "Tonnes", "Target Gra", "Achieved G", "% Variance"), width=150)
        self.feed_summary_text = tk.Text(self.feed_result_tab, height=10)
        self.feed_summary_text.pack(fill="x", padx=10, pady=10)
        tk.Button(self.feed_result_tab, text="Run Feed Plan", command=self.run_feed_plan).pack(pady=5)

    def run_feed_plan(self):
        if self.df.empty or self.feed_targets_df.empty:
            messagebox.showwarning("Missing Data", "Load Inventory and Feed Targets CSV first.")
            return

        self.feed_result_tree.delete(*self.feed_result_tree.get_children())
        self.feed_summary_text.delete("1.0", tk.END)

        try:
            minimum_feed_tonnes = float(self.minimum_feed_tonnes_entry.get())
        except:
            minimum_feed_tonnes = 0

        combined_df = self.df.copy()
        combined_df["Location"] = combined_df["Location"].astype(str).str.strip().str.upper()
        combined_df = combined_df[combined_df["Location"].isin(["ROMP", "ROMS"])].reset_index(drop=True)
        combined_df["Tonnes"] = combined_df["Tonnes"].astype(float)
        inventory_df = combined_df.copy()

        all_results = []
        start_date = datetime.strptime(self.start_date.get(), "%d-%m-%Y")

        # --- Optimization loop per day ---
        for idx, values in self.feed_targets_df.iterrows():
            plan_date = (start_date + timedelta(days=idx)).strftime("%d-%m-%Y")
            feed_tonnes = float(values["ROMP Tonnes"] + values["ROMS Tonnes"])
            target_grade = float(values["Target Grade"])
            romp_split = values["ROMP Tonnes"] / feed_tonnes if feed_tonnes > 0 else 0
            roms_split = values["ROMS Tonnes"] / feed_tonnes if feed_tonnes > 0 else 0

            active_inventory = inventory_df[inventory_df["Tonnes"] > 0].copy()
            romp_df = active_inventory[active_inventory["Location"] == "ROMP"].reset_index()
            roms_df = active_inventory[active_inventory["Location"] == "ROMS"].reset_index()

            problem = pulp.LpProblem(f"FeedPlan_{plan_date}", pulp.LpMinimize)
            variables, binaries = {}, {}

            # helper now takes problem explicitly
            def add_vars(df, prefix, problem, variables, binaries):
                for i in df.index:
                    tonnes_available = df.loc[i, "Tonnes"]
                    variables[f"{prefix}_{i}"] = pulp.LpVariable(f"{prefix}_{i}", lowBound=0, upBound=tonnes_available)
                    binaries[f"{prefix}_BIN_{i}"] = pulp.LpVariable(f"{prefix}_BIN_{i}", cat="Binary")
                    problem += variables[f"{prefix}_{i}"] <= tonnes_available * binaries[f"{prefix}_BIN_{i}"]
                    if minimum_feed_tonnes > 0:
                        problem += variables[f"{prefix}_{i}"] >= minimum_feed_tonnes * binaries[f"{prefix}_BIN_{i}"]

            add_vars(romp_df, "ROMP", problem, variables, binaries)
            add_vars(roms_df, "ROMS", problem, variables, binaries)

            total_feed = pulp.lpSum(variables.values())
            total_metal = pulp.lpSum(
                [variables[f"ROMP_{i}"] * romp_df.loc[i, "Grade (g/t)"] for i in romp_df.index] +
                [variables[f"ROMS_{i}"] * roms_df.loc[i, "Grade (g/t)"] for i in roms_df.index]
            )

            dev_tonnes, dev_grade = pulp.LpVariable("dev_tonnes", lowBound=0), pulp.LpVariable("dev_grade", lowBound=0)
            problem += total_feed >= feed_tonnes - dev_tonnes
            problem += total_feed <= feed_tonnes + dev_tonnes
            target_metal = target_grade * feed_tonnes
            problem += total_metal >= target_metal - dev_grade
            problem += total_metal <= target_metal + dev_grade

            problem += pulp.lpSum([variables[f"ROMP_{i}"] for i in romp_df.index]) >= romp_split * feed_tonnes
            problem += pulp.lpSum([variables[f"ROMS_{i}"] for i in roms_df.index]) >= roms_split * feed_tonnes

            problem += 5000 * dev_grade + 1000 * dev_tonnes + 5 * pulp.lpSum(binaries.values()) - total_feed
            solver = pulp.COIN_CMD(path=resource_path(os.path.join("solvers", "bin", "cbc.exe")), msg=False)
            problem.solve(solver)

            if pulp.LpStatus[problem.status] != "Optimal":
                messagebox.showerror("Optimization Failed", f"Status: {pulp.LpStatus[problem.status]} on {plan_date}")

            def record_results(df, prefix):
                for i in df.index:
                    value = variables[f"{prefix}_{i}"].varValue
                    if value and value > 0:
                        stockpile, grade, binval, original_index = df.loc[i, ["Name","Grade (g/t)","Grade_bin","index"]]
                        all_results.append([plan_date, prefix, stockpile, round(value, 2), grade, binval])
                        inventory_df.loc[original_index, "Tonnes"] -= value

            record_results(romp_df, "ROMP")
            record_results(roms_df, "ROMS")

        # --- Build daily report ---
        day_summary = {}
        for date, feed_point, stockpile, tonnes, grade, binval in all_results:
            if date not in day_summary: day_summary[date] = {"rows": [], "tonnes": 0, "metal": 0}
            day_summary[date]["rows"].append((feed_point, stockpile, tonnes, grade, binval))
            day_summary[date]["tonnes"] += tonnes; day_summary[date]["metal"] += tonnes * grade

        report_rows = []
        for idx, (date, info) in enumerate(day_summary.items()):
            achieved_tonnes, achieved_grade = info["tonnes"], info["metal"]/info["tonnes"] if info["tonnes"]>0 else 0
            target_row, target_grade = self.feed_targets_df.iloc[idx], self.feed_targets_df.iloc[idx]["Target Grade"]
            variance = ((achieved_grade - target_grade) / target_grade * 100) if target_grade > 0 else 0
            first = True
            for feed_point, stockpile, tonnes, grade, binval in info["rows"]:
                values = (date if first else "", feed_point, stockpile, tonnes,
                          f"{target_grade:.2f}" if first else "", f"{achieved_grade:.2f}" if first else "",
                          f"{variance:.2f}%" if first else "")
                self.feed_result_tree.insert("", "end", values=values); report_rows.append(values); first=False

        self.feed_results = pd.DataFrame(report_rows,
            columns=["Date","Feed Point","Stockpile","Tonnes","Target Gra","Achieved G","% Variance"])
        out_path = os.path.join(self.csv_folder or os.getcwd(), f"FeedPlan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        self.feed_results.to_csv(out_path, index=False)
        messagebox.showinfo("Saved", f"Feed plan saved to:\n{out_path}")

        summary_lines = []
        for idx, (date, info) in enumerate(day_summary.items()):
            achieved_tonnes, achieved_grade = info["tonnes"], info["metal"]/info["tonnes"] if info["tonnes"]>0 else 0
            target_row = self.feed_targets_df.iloc[idx]; target_grade = target_row["Target Grade"]
            target_tonnes = target_row["ROMP Tonnes"] + target_row["ROMS Tonnes"]
            tonnes_var, grade_var = achieved_tonnes - target_tonnes, achieved_grade - target_grade
            summary_lines.append(
                f"{date}: Target {target_tonnes}t @ {target_grade:.2f}g/t | "
                f"Achieved {achieved_tonnes:.1f}t @ {achieved_grade:.2f}g/t | "
                f"ΔTonnes {tonnes_var:.1f}, ΔGrade {grade_var:.2f}"
            )
        self.feed_summary_text.insert("1.0", "\n".join(summary_lines))
        messagebox.showinfo("Blend Complete", "Daily feed plan has been run and results saved successfully.")

        # --- Summary Tab ---
    def build_summary_tab(self):
        self.summary_text = tk.Text(self.summary_tab, height=15)
        self.summary_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.figure = Figure(figsize=(8, 5))
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.summary_tab)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def compare_plan_vs_actual(self):
        if self.feed_targets_df.empty or self.performance_df.empty:
            return
        merged = pd.merge(self.feed_targets_df, self.performance_df, on="Date", how="inner")
        self.summary_text.delete("1.0", tk.END)
        self.ax.clear()

        for _, row in merged.iterrows():
            planned_tonnes = row["ROMP Tonnes"] + row["ROMS Tonnes"]
            planned_grade, actual_tonnes, actual_grade = row["Target Grade"], row["Actual Feed Tonnes"], row["Actual Grade"]
            tonnes_var, grade_var = actual_tonnes - planned_tonnes, actual_grade - planned_grade
            self.summary_text.insert(
                tk.END,
                f"{row['Date']}: Planned {planned_tonnes}t @ {planned_grade:.2f}g/t | "
                f"Actual {actual_tonnes}t @ {actual_grade:.2f}g/t | "
                f"ΔTonnes {tonnes_var:.1f}, ΔGrade {grade_var:.2f}\n"
            )

        x = range(len(merged["Date"]))
        width = 0.35
        self.ax.bar([i - width/2 for i in x], merged["ROMP Tonnes"] + merged["ROMS Tonnes"],
                    width=width, label="Planned Tonnes", color="tab:blue")
        self.ax.bar([i + width/2 for i in x], merged["Actual Feed Tonnes"],
                    width=width, label="Actual Tonnes", color="tab:cyan")
        self.ax.set_xticks(x)
        self.ax.set_xticklabels(merged["Date"], rotation=45, ha="right")

        ax2 = self.ax.twinx()
        ax2.set_ylabel("Grade (g/t)")
        ax2.plot(x, merged["Target Grade"], label="Planned Grade", marker="o", color="tab:red")
        ax2.plot(x, merged["Actual Grade"], label="Actual Grade", marker="x", color="tab:orange")

        lines, labels = self.ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        self.ax.legend(lines + lines2, labels + labels2, loc="upper left")
        self.canvas.draw()

    # --- Inventory Tab ---
    def build_inventory_tab(self):
        self.inventory_projection_tree = self.build_treeview(
            self.inventory_tab,
            ("Stockpile", "Location", "Remaining Tonnes", "Grade (g/t)"), width=180
        )
        ttk.Button(self.inventory_tab, text="Update Projection", command=self.update_inventory_projection).pack(pady=10)

    def update_inventory_projection(self):
        if self.df.empty:
            messagebox.showwarning("No Data", "Load Inventory CSV first.")
            return
        self.inventory_projection_tree.delete(*self.inventory_projection_tree.get_children())
        self.df["Tonnes"] = self.df["Tonnes"].astype(float)
        self.df["Location"] = self.df["Location"].astype(str).str.strip().str.upper()
        for _, row in self.df.iterrows():
            self.inventory_projection_tree.insert(
                "", "end",
                values=(row["Name"], row["Location"], round(row["Tonnes"], 2), round(row["Grade (g/t)"], 3))
            )

# =========================================================
# ENTRY POINT
# =========================================================
def launch_main_gui():
    main_root = tk.Tk()
    app = RehandleFeedPlanner(main_root)
    main_root.mainloop()

if __name__ == "__main__":
    solver_path = resource_path(os.path.join("solvers", "bin", "cbc.exe"))
    pulp.LpSolverDefault = pulp.COIN_CMD(path=solver_path, msg=False)
    login_root = tk.Tk()
    AuthWindow(login_root, on_success=launch_main_gui)
    login_root.mainloop()


# In[ ]:




