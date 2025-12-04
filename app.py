# app.py
import os
import subprocess
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, session, flash,
    send_file, jsonify
)
import pandas as pd
import numpy as np

# ---------- Configuration ----------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change_this_secret")

DATA_DIR = "data"
CLEANED_PATH = os.path.join(DATA_DIR, "cleaned_retail_data_with_names.csv")
FORECAST_PATH = os.path.join(DATA_DIR, "stock_forecast_next_7_days_with_alerts.csv")
FORECAST_SCRIPT = "xgb_forecast.py"   # or "daily_forecast.py" if you prefer

# Demo credentials (replace with real auth in production)
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

# ---------- Utility functions ----------
def safe_read_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)

def load_data():
    df = safe_read_csv(CLEANED_PATH)
    fc = safe_read_csv(FORECAST_PATH)
    return df, fc

def extract_store_list(df):
    if df.empty:
        return []
    cities = df[["city_id", "city_name"]].drop_duplicates().sort_values("city_name")
    stores = df[["city_id","city_name","store_id","company_name","branch_name"]].drop_duplicates()
    return cities, stores

def compute_alerts_summary(forecast_df, filter_city=None, filter_branch=None):
    if forecast_df.empty:
        return {}
    df = forecast_df.copy()
    # Optionally filter by city or branch (string names)
    if filter_city is not None:
        df = df[df["city_name"] == filter_city]
    if filter_branch is not None:
        df = df[df["branch_name"] == filter_branch]

    # Count understock per store and per product
    alert_cols = [c for c in df.columns if c.endswith("_alert")]
    understock_mask = np.column_stack([df[c] == "UNDERSTOCK" for c in alert_cols]).any(axis=1)
    overstock_mask  = np.column_stack([df[c] == "OVERSTOCK"  for c in alert_cols]).any(axis=1)

    under = df[understock_mask]
    over  = df[overstock_mask]

    top_under_products = under.groupby("product_name").size().sort_values(ascending=False).head(10)
    top_under_stores = under.groupby(["city_name","branch_name"]).size().sort_values(ascending=False).head(10)

    # Reorder suggestions (day_1...day_7 forecasts)
    forecast_cols = [c for c in df.columns if c.startswith("day_") and c.endswith("_forecast")]
    # simple reorder: if any forecast > stock -> qty = max(forecast - stock, 0)
    def calc_reorder(row):
        future = row[forecast_cols].values.astype(float)
        need = max(0, round(float(future.max() - row["stock_hour6_22_cnt"]),2))
        return need

    df["reorder_qty"] = df.apply(calc_reorder, axis=1)
    reorder_list = df[df["reorder_qty"] > 0].sort_values("reorder_qty", ascending=False).head(20)

    summary = {
        "total_rows": len(df),
        "total_understock": len(under),
        "total_overstock": len(over),
        "top_under_products": top_under_products.reset_index().values.tolist(),
        "top_under_stores": top_under_stores.reset_index().values.tolist(),
        "reorder_list": reorder_list[["store_id","product_id","city_name","branch_name","product_name","stock_hour6_22_cnt","reorder_qty"]].to_dict(orient="records")
    }
    return summary

# ---------- Routes ----------
@app.route("/", methods=["GET","POST"])
def login():
    df, fc = load_data()
    cities, stores = extract_store_list(df)

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")  # "admin" or "manager"

        # manager must select city and branch to "scope" to
        sel_city = request.form.get("city")
        sel_branch = request.form.get("branch")

        if role == "admin":
            if username == ADMIN_USER and password == ADMIN_PASS:
                session["logged_in"] = True
                session["role"] = "admin"
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid admin credentials.", "danger")
        else:
            # simple manager login: accept any non-empty username/password
            if username and password and sel_city and sel_branch:
                session["logged_in"] = True
                session["role"] = "manager"
                session["manager_username"] = username
                session["scope_city"] = sel_city
                session["scope_branch"] = sel_branch
                return redirect(url_for("dashboard"))
            else:
                flash("Enter username, password, city and branch for manager login.", "danger")

    return render_template("login.html", cities=cities.to_dict(orient="records") if len(cities)>0 else [], stores=stores.to_dict(orient="records") if len(stores)>0 else [])

@app.route("/get_branches_for_city")
def get_branches_for_city():
    city = request.args.get("city")
    df, _ = load_data()
    if df.empty:
        return jsonify([])
    branches = df[df["city_name"]==city][["branch_name","store_id","company_name"]].drop_duplicates().sort_values("branch_name")
    return jsonify(branches.to_dict(orient="records"))

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    df, fc = load_data()

    scope_city = None
    scope_branch = None
    if session.get("role") == "manager":
        scope_city = session.get("scope_city")
        scope_branch = session.get("scope_branch")

    summary = compute_alerts_summary(fc, filter_city=scope_city, filter_branch=scope_branch)
    # Prepare chart data
    top_products = summary.get("top_under_products", [])
    prod_names = [x[0] for x in top_products]
    prod_counts = [int(x[1]) for x in top_products]

    top_stores = summary.get("top_under_stores", [])
    store_labels = [f"{x[0]} / {x[1]}" for x in top_stores]
    store_counts = [int(x[2]) for x in top_stores]

    # small preview table
    preview_table = fc.copy()
    if scope_city:
        preview_table = preview_table[preview_table["city_name"]==scope_city]
    if scope_branch:
        preview_table = preview_table[preview_table["branch_name"]==scope_branch]

    preview_html = preview_table.head(50).to_html(classes="table table-sm table-hover", index=False)

    return render_template(
        "dashboard.html",
        role=session.get("role"),
        username=session.get("manager_username","admin"),
        summary=summary,
        prod_names=prod_names, prod_counts=prod_counts,
        store_labels=store_labels, store_counts=store_counts,
        preview_table=preview_html
    )

@app.route("/predictions")
def predictions():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    df, fc = load_data()
    scope_city = None
    scope_branch = None
    if session.get("role") == "manager":
        scope_city = session.get("scope_city")
        scope_branch = session.get("scope_branch")
    table = fc.copy()
    if scope_city:
        table = table[table["city_name"]==scope_city]
    if scope_branch:
        table = table[table["branch_name"]==scope_branch]

    # reorder cols to show names first
    cols_order = ["store_id","product_id","city_name","company_name","branch_name","product_name","stock_hour6_22_cnt"]
    for c in table.columns:
        if c not in cols_order:
            cols_order.append(c)
    table = table[cols_order]
    table_html = table.to_html(classes="table table-sm table-striped", index=False)
    return render_template("predictions.html", table_html=table_html)

@app.route("/alerts")
def alerts():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    _, fc = load_data()
    if fc.empty:
        flash("No forecast found.", "warning")
        return redirect(url_for("dashboard"))

    # list all rows that have any UNDERSTOCK
    alert_cols = [c for c in fc.columns if c.endswith("_alert")]
    mask = np.column_stack([fc[c]=="UNDERSTOCK" for c in alert_cols]).any(axis=1)
    under = fc[mask].sort_values(["city_name","branch_name"])
    return render_template("alerts.html", table_html=under.to_html(classes="table table-sm table-striped", index=False))

@app.route("/run_forecast", methods=["POST"])
def run_forecast():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    # Run forecast script (non-blocking can be implemented; here we run and wait)
    try:
        # If you have a wrapper script daily_forecast.py prefer that
        script = FORECAST_SCRIPT
        if not os.path.exists(script):
            flash(f"Forecast script not found: {script}", "danger")
            return redirect(url_for("dashboard"))
        subprocess.run(["python", script], check=True)
        flash("Forecast completed successfully.", "success")
    except subprocess.CalledProcessError as e:
        flash(f"Forecast script failed: {e}", "danger")
    return redirect(url_for("dashboard"))

@app.route("/download_forecast")
def download_forecast():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    if not os.path.exists(FORECAST_PATH):
        flash("No forecast file available.", "warning")
        return redirect(url_for("dashboard"))
    return send_file(FORECAST_PATH, as_attachment=True)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Simple API endpoint for chart data (optional)
@app.route("/api/top_products")
def api_top_products():
    _, fc = load_data()
    top = fc[fc.filter(like="_alert").apply(lambda r: (r=="UNDERSTOCK").any(), axis=1)]
    top_prod = top.groupby("product_name").size().sort_values(ascending=False).head(10)
    return jsonify(top_prod.reset_index().to_dict(orient="records"))

# ---------- Run ----------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
