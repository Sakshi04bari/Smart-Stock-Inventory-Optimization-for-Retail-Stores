# app.py - COMPLETE SmartStock Dashboard (MY-STORE PAGE ✅ + ALL FIXES)
import threading, time, random
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from sqlalchemy import create_engine, text
import threading, time, random, os 
from dotenv import load_dotenv       
from sqlalchemy.engine import URL
import pandas as pd
import mysql.connector
import xgboost as xgb

# ----------------------------
# Config - DEPLOYMENT READY
# ----------------------------
load_dotenv()  # 🔥 NEW: Load environment variables

DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "Bhakthi@13")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_NAME = os.getenv("DB_NAME", "smartstock_dynamic")

# 🔥 Move app creation BEFORE engine_url
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "smartstock-super-secret-key-2025")

engine_url = URL.create(
    drivername="mysql+mysqlconnector",
    username=DB_USER,
    password=DB_PASS,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME
)
engine = create_engine(engine_url, pool_pre_ping=True)

def get_db_conn_raw():
    return mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME
    )

# ----------------------------
# Flask + Login (FIXED)
# ----------------------------
app = Flask(__name__)
app.secret_key = "smartstock-super-secret-key-2025"

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Login required!"
login_manager.login_message_category = "warning"
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id, username, role, cityid=None, storeid=None, storename=None, cityname=None):
        self.id = str(id)
        self.username = username
        self.role = role
        self.cityid = cityid
        self.storeid = storeid
        self.storename = storename
        self.cityname = cityname

    def get_id(self):
        return self.id

@login_manager.user_loader
def load_user(user_id):
    if 'user_data' in session:
        data = session['user_data']
        return User(
            id=data['id'],
            username=data['username'],
            role=data['role'],
            cityid=data.get('cityid'),
            storeid=data.get('storeid'),
            storename=data.get('storename'),
            cityname=data.get('cityname')
        )
    return None

# ----------------------------
# Live Alerts Storage (PER-USER FILTERING)
# ----------------------------
all_alerts = []

# ----------------------------
# 🔥 LIVE UPDATER (15s + BETTER ALERTS)
# ----------------------------
def live_updater_background():
    global all_alerts
    conn = get_db_conn_raw()
    cur = conn.cursor()

    cur.execute("SELECT productid, productname FROM product")
    products = cur.fetchall()
    cur.execute("SELECT storeid, storename, cityid FROM store")
    stores = cur.fetchall()
    cur.execute("SELECT cityid, cityname FROM city")
    cities = dict(cur.fetchall())

    if not products or not stores:
        print("DB empty: populate first")
        cur.close()
        conn.close()
        return

    SALE_INTERVAL = 15
    print("🚀 Live updater started! (15s updates)")
    try:
        while True:
            now = datetime.now()
            store_row = random.choice(stores)
            product_row = random.choice(products)
            storeid, storename, cityid = store_row
            productid, productname = product_row
            cityname = cities.get(cityid, "Unknown City")

            sale_amount = random.randint(2, 15)
            cur.execute(
                "SELECT stock FROM sales WHERE storeid=%s AND productid=%s ORDER BY dt DESC LIMIT 1",
                (storeid, productid)
            )
            r = cur.fetchone()
            current_stock = r[0] if r else random.randint(10, 40)
            new_stock = max(current_stock - sale_amount, 0)

            discount = random.choice([0,5,10,15])
            holiday_flag = random.choice([0,1])
            activity_flag = random.choice([0,1])
            hour = now.hour

            cur.execute("""
                INSERT INTO sales (dt, cityid, storeid, productid, sale_amount, stock, hour, discount, holiday_flag, activity_flag)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (now, cityid, storeid, productid, sale_amount, new_stock, hour, discount, holiday_flag, activity_flag))
            conn.commit()

            # 🔥 BETTER ALERTS (35% Overstock, 25% Understock, 40% OK)
            if random.random() < 0.35:  # 35% Overstock
                new_stock += random.randint(35, 60)
                stock_alert = "Overstock 🚨"
            elif random.random() < 0.60:  # 25% Understock  
                new_stock = random.randint(0, 3)
                stock_alert = "Restock Needed ⚠️"
            else:  # 40% OK
                stock_alert = "Stock OK ✅"

            alert = {
                "city": cityname,
                "store": storename,
                "storeid": storeid,  # 🔥 ADDED for filtering
                "product": productname,
                "sale": int(sale_amount),
                "stock": int(new_stock),
                "stock_alert": stock_alert,
                "timestamp": now.strftime("%Y-%m-%d %H:%M:%S")
            }
            all_alerts.append(alert)
            if len(all_alerts) > 10000:
                all_alerts = all_alerts[-10000:]

            print(f"[{alert['timestamp']}] {alert['city']} / {alert['store']} / {alert['product']} → {alert['stock_alert']}")
            time.sleep(SALE_INTERVAL)
    finally:
        cur.close()
        conn.close()

# ----------------------------
# ROUTES
# ----------------------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        username = request.form.get("username")
        password = request.form.get("password")
        print(f"🔓 LOGIN ATTEMPT: {username}/{password}")
        
        conn = get_db_conn_raw()
        cursor = conn.cursor(dictionary=True)
        
        # STORE MANAGER LOGIN
        cursor.execute("SELECT * FROM store WHERE store_manager = %s AND password = %s", (username, password))
        store_user = cursor.fetchone()
        
        if store_user:
            print(f"✅ STORE MANAGER LOGIN: {username}")
            session['user_data'] = {
                'id': store_user['storeid'],
                'username': store_user['store_manager'],
                'role': 'store_manager',
                'storeid': store_user['storeid'],
                'storename': store_user['storename'],
                'cityid': store_user['cityid']
            }
            user_obj = User(**session['user_data'])
            login_user(user_obj)
            conn.close()
            return redirect(url_for('dashboard'))
        
        # ADMIN LOGIN
        if username == "admin" and password == "admin123":
            print("✅ ADMIN LOGIN SUCCESS!")
            session['user_data'] = {
                'id': 1,
                'username': 'admin',
                'role': 'admin'
            }
            user_obj = User(**session['user_data'])
            login_user(user_obj)
            conn.close()
            return redirect(url_for('dashboard'))
        
        conn.close()
        flash("Invalid credentials! Try: admin/admin123", "danger")
    
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('login'))

# 🔥 NEW: MY-STORE PAGE (Replaces store_manager.html - No conflicts!)
@app.route("/my-store")
@login_required
def my_store_dashboard():
    if current_user.role != 'store_manager':
        flash("❌ Admin cannot access My Store dashboard!", "danger")
        return redirect(url_for('dashboard'))
    
    storeid = current_user.storeid
    store_alerts = [a for a in all_alerts if a.get('storeid') == storeid]
    alerts = list(reversed(store_alerts[-30:]))
    
    # Store-specific stats
    understock_count = len([a for a in alerts if "Restock Needed" in a['stock_alert']])
    overstock_count = len([a for a in alerts if "Overstock" in a['stock_alert']])
    okstock_count = len([a for a in alerts if "Stock OK" in a['stock_alert']])
    total_count = len(alerts)
    
    # Get store products summary
    try:
        df = pd.read_sql(text("""
            SELECT p.productname, COALESCE(s.stock, 0) as stock
            FROM product p 
            LEFT JOIN (
                SELECT storeid, productid, stock 
                FROM sales WHERE storeid=:sid ORDER BY dt DESC LIMIT 1000
            ) s ON p.productid = s.productid
            LIMIT 10
        """), engine, params={"sid": storeid})
        recent_products = df.to_dict('records')
    except:
        recent_products = []
    
    return render_template("my_store.html", 
                         alerts=alerts, 
                         understock_count=understock_count,
                         overstock_count=overstock_count,
                         okstock_count=okstock_count,
                         total_count=total_count,
                         recent_products=recent_products,
                         user=current_user)

# 🔥 FIXED ADMIN STORES (897 stores + managers + passwords) - STORE MANAGER BLOCKED
@app.route("/admin/stores")
@login_required
def admin_stores():
    if current_user.role != 'admin':
        flash("❌ Store managers cannot access confidential admin pages!", "danger")
        return redirect(url_for('dashboard'))
    
    search = request.args.get('search', '').strip()
    conn = get_db_conn_raw()
    cursor = conn.cursor(dictionary=True)
    
    if search:
        cursor.execute("""
            SELECT storeid, storename, store_manager, password, cityid 
            FROM store 
            WHERE storename LIKE %s OR store_manager LIKE %s
            ORDER BY storeid
        """, (f'%{search}%', f'%{search}%'))
    else:
        cursor.execute("SELECT storeid, storename, store_manager, password, cityid FROM store ORDER BY storeid")
    
    stores = cursor.fetchall()
    print(f"🔍 Admin stores query returned: {len(stores)} stores")
    cursor.close()
    conn.close()
    
    return render_template("admin_stores.html", stores=stores, search=search, user=current_user)

@app.route("/admin/users")
@login_required
def admin_users():
    if current_user.role != 'admin':
        flash("❌ Store managers cannot access confidential admin pages!", "danger")
        return redirect(url_for('dashboard'))
    return render_template("admin_users.html", user=current_user)

@app.route("/cities")
@login_required
def cities_page():
    if current_user.role != 'admin':
        flash("❌ Store managers can only view their store dashboard!", "danger")
        return redirect(url_for('dashboard'))
    
    try:
        search = request.args.get("search","").strip()
        if search:
            df = pd.read_sql(text("""
                SELECT c.cityid, c.cityname, COUNT(s.storeid) as store_count
                FROM city c 
                LEFT JOIN store s ON c.cityid = s.cityid 
                WHERE c.cityname LIKE :s 
                GROUP BY c.cityid, c.cityname 
                ORDER BY c.cityname
            """), engine, params={"s": f"%{search}%"})
        else:
            df = pd.read_sql(text("""
                SELECT c.cityid, c.cityname, COUNT(s.storeid) as store_count
                FROM city c 
                LEFT JOIN store s ON c.cityid = s.cityid 
                GROUP BY c.cityid, c.cityname 
                ORDER BY c.cityname
            """), engine)
        
        print(f"🌆 Cities loaded: {len(df)} cities, total stores: {df['store_count'].sum()}")
        return render_template("cities.html", cities=df.to_dict('records'), search=search, user=current_user)
    except Exception as e:
        print(f"❌ Cities error: {e}")
        return f"<h1>Cities Error: {str(e)}</h1>"

@app.route("/cities/<int:cityid>/stores")
@login_required
def city_stores_page(cityid):
    if current_user.role != 'admin':
        flash("❌ Store managers can only view their store dashboard!", "danger")
        return redirect(url_for('dashboard'))
    
    try:
        df = pd.read_sql(text("""
            SELECT storeid, storename, cityid 
            FROM store 
            WHERE cityid=:cid 
            ORDER BY storename
        """), engine, params={"cid": cityid})
        
        city_df = pd.read_sql(text("SELECT cityname FROM city WHERE cityid=:cid"), engine, params={"cid": cityid})
        cityname = city_df.iloc[0]['cityname'] if not city_df.empty else f"City {cityid}"
        
        print(f"🏪 City {cityid} ({cityname}): {len(df)} stores")
        return render_template("city_stores.html", stores=df.to_dict('records'), cityid=cityid, cityname=cityname, user=current_user)
    except Exception as e:
        print(f"❌ City stores error: {e}")
        return f"<h1>Stores in City {cityid}: Error {str(e)}</h1>"

@app.route("/stores/<int:storeid>/products")
@login_required
def store_products_page(storeid):
    # 🔥 STORE MANAGER CAN ONLY VIEW THEIR OWN STORE
    if current_user.role == 'store_manager' and current_user.storeid != storeid:
        flash("❌ You can only view your own store products!", "danger")
        return redirect(url_for('dashboard'))
    
    try:
        search = request.args.get("search","").strip()
        if search:
            df = pd.read_sql(text("""
                SELECT p.productid, p.productname, COALESCE(s.stock, 0) as stock
                FROM product p 
                LEFT JOIN (
                    SELECT storeid, productid, stock 
                    FROM sales WHERE storeid=:sid ORDER BY dt DESC LIMIT 1000
                ) s ON p.productid = s.productid
                WHERE p.productname LIKE :s LIMIT 50
            """), engine, params={"sid": storeid, "s": f"%{search}%"})
        else:
            df = pd.read_sql(text("""
                SELECT p.productid, p.productname, COALESCE(s.stock, 0) as stock
                FROM product p 
                LEFT JOIN (
                    SELECT storeid, productid, stock 
                    FROM sales WHERE storeid=:sid ORDER BY dt DESC LIMIT 1000
                ) s ON p.productid = s.productid
                LIMIT 50
            """), engine, params={"sid": storeid})
        
        store_df = pd.read_sql(text("SELECT storename FROM store WHERE storeid=:sid"), engine, params={"sid": storeid})
        storename = store_df.iloc[0]['storename'] if not store_df.empty else f"Store {storeid}"
        
        print(f"📦 Store {storeid} ({storename}): {len(df)} products")
        return render_template("store_products.html", products=df.to_dict('records'), storename=storename, storeid=storeid, user=current_user)
    except Exception as e:
        print(f"❌ Store products error: {e}")
        return f"<h1>Store {storeid} Products: Error {str(e)}</h1>"

# 🔥 FIXED DASHBOARD (STORE MANAGER SEES ONLY THEIR STORE UPDATES ✅)
@app.route("/")
@login_required
def dashboard():
    # 🔥 STORE MANAGER FILTER: Only show their store's alerts
    if current_user.role == 'store_manager':
        user_storeid = current_user.storeid
        store_alerts = [a for a in all_alerts if a.get('storeid') == user_storeid]
        alerts = list(reversed(store_alerts[-50:]))
        title = f"🛒 {current_user.storename} Dashboard"
        subtitle = f"Showing only {current_user.storename} updates"
        my_store_link = url_for('my_store_dashboard')
    else:  # ADMIN sees everything
        alerts = list(reversed(all_alerts[-50:]))
        title = "🌟 SmartStock Admin Dashboard"
        subtitle = "All stores - Live updates"
        my_store_link = None
    
    # 🔥 LIVE COUNTERS (Filtered for store manager)
    understock_count = len([a for a in alerts if "Restock Needed" in a['stock_alert']])
    overstock_count = len([a for a in alerts if "Overstock" in a['stock_alert']])
    okstock_count = len([a for a in alerts if "Stock OK" in a['stock_alert']])
    total_count = len(alerts)
    
    return render_template("dashboard.html", 
                         alerts=alerts, 
                         understock_count=understock_count,
                         overstock_count=overstock_count,
                         okstock_count=okstock_count,
                         total_count=total_count,
                         title=title,
                         subtitle=subtitle,
                         my_store_link=my_store_link,
                         user=current_user)

@app.route("/overstock")
@login_required
def overstock_page():
    # 🔥 STORE MANAGER FILTER
    if current_user.role == 'store_manager':
        user_storeid = current_user.storeid
        alerts = [a for a in reversed(all_alerts) if "Overstock" in a['stock_alert'] and a.get('storeid') == user_storeid]
        page_title = f"{current_user.storename} - Overstock Alerts"
    else:
        alerts = [a for a in reversed(all_alerts) if "Overstock" in a['stock_alert']]
        page_title = "All Stores - Overstock Alerts"
    return render_template("overstock.html", alerts=alerts[-20:], title=page_title, user=current_user)

@app.route("/understock")
@login_required
def understock_page():
    # 🔥 STORE MANAGER FILTER
    if current_user.role == 'store_manager':
        user_storeid = current_user.storeid
        alerts = [a for a in reversed(all_alerts) if "Restock" in a['stock_alert'] and a.get('storeid') == user_storeid]
        page_title = f"{current_user.storename} - Understock Alerts"
    else:
        alerts = [a for a in reversed(all_alerts) if "Restock" in a['stock_alert']]
        page_title = "All Stores - Understock Alerts"
    return render_template("understock.html", alerts=alerts[-20:], title=page_title, user=current_user)

@app.route("/ok-stock")
@login_required
def ok_stock_page():
    # 🔥 STORE MANAGER FILTER
    if current_user.role == 'store_manager':
        user_storeid = current_user.storeid
        alerts = [a for a in reversed(all_alerts) if "Stock OK" in a['stock_alert'] and a.get('storeid') == user_storeid]
        page_title = f"{current_user.storename} - Stock OK"
    else:
        alerts = [a for a in reversed(all_alerts) if "Stock OK" in a['stock_alert']]
        page_title = "All Stores - Stock OK"
    return render_template("ok_stock.html", alerts=alerts[-20:], title=page_title, user=current_user)

@app.route("/api/alerts")
@login_required
def get_alerts_api():
    n = int(request.args.get("n", 200))
    # 🔥 API also respects store manager filtering
    if current_user.role == 'store_manager':
        user_storeid = current_user.storeid
        alerts = [a for a in reversed(all_alerts) if a.get('storeid') == user_storeid][-n:]
    else:
        alerts = list(reversed(all_alerts))[-n:]
    return jsonify(alerts)

@app.route("/toggle-theme")
@login_required
def toggle_theme():
    current_theme = session.get('theme', 'light')
    session['theme'] = 'dark' if current_theme == 'light' else 'light'
    return redirect(request.referrer or url_for('dashboard'))

if __name__=="__main__":
    t = threading.Thread(target=live_updater_background, daemon=True)
    t.start()
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    debug = os.environ.get('DEBUG', 'True').lower() == 'true'
    
    print("🌟 SmartStock Dashboard: http://{}:{}".format(host, port))
    print("🔓 ADMIN: admin / admin123 → Sees ALL stores + /admin/stores (897 stores)")
    print("🔓 MANAGER: Ahm-Store 1-mgr / Ahm.Store@1 → /my-store (THEIR STORE ONLY)")
    print("✅ /my-store page added - Uses my_store.html (no conflicts!)")
    app.run(host=host, port=port, debug=debug)

