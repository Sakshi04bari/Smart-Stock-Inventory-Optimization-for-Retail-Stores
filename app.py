# app.py - COMPLETE SmartStock Dashboard (POSTGRESQL ✅ + LIVE UPDATES FIXED ✅)
import threading, time, random
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from sqlalchemy import create_engine, text
import os 
from dotenv import load_dotenv       
from sqlalchemy.engine import URL
import pandas as pd
import mysql.connector
import xgboost as xgb
import psycopg2  # 🔥 POSTGRESQL SUPPORT
from urllib.parse import urlparse   # 🔥 POSTGRESQL URL PARSER

# ----------------------------
# Config - DEPLOYMENT READY
# ----------------------------
load_dotenv()

DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "Bhakthi@13")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_NAME = os.getenv("DB_NAME", "smartstock_dynamic")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "smartstock-super-secret-key-2025")

# 🔥 DYNAMIC ENGINE (PostgreSQL + MySQL)
db_url = os.getenv('DATABASE_URL')
if db_url and 'postgres' in db_url:
    parsed = urlparse(db_url)
    engine_url = URL.create(
        drivername="postgresql+psycopg2",
        username=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path[1:],
        query={"sslmode": "require"}
    )
else:
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
    db_url = os.getenv('DATABASE_URL')
    if db_url and 'postgres' in db_url:
        parsed = urlparse(db_url)
        return psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path[1:]
        )
    else:
        return mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME
        )

def get_cursor(conn):
    return conn.cursor()

# ----------------------------
# Flask + Login
# ----------------------------
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
# Live Alerts Storage
# ----------------------------
all_alerts = []
# ----------------------------
# 🔥 LIVE UPDATER (15s + AUTO-CREATE TABLES)
# ----------------------------
init_done = False
def ensure_tables_exist():
    global init_done
    if init_done:
        return
    
    print("🛠️ Creating tables (PostgreSQL-safe)...")
    conn = None
    cur = None
    try:
        conn = get_db_conn_raw()
        cur = get_cursor(conn)
        
        # ✅ TABLES WITH UNIQUE CONSTRAINTS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS city (
                cityid SERIAL PRIMARY KEY, 
                cityname VARCHAR(50) NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS store (
                storeid SERIAL PRIMARY KEY, 
                storename VARCHAR(50) NOT NULL,
                store_manager VARCHAR(50), 
                password VARCHAR(50), 
                cityid INT REFERENCES city(cityid)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS product (
                productid SERIAL PRIMARY KEY, 
                productname VARCHAR(50) NOT NULL UNIQUE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY, 
                dt TIMESTAMP, cityid INT, storeid INT, 
                productid INT, sale_amount INT, stock INT, 
                hour INT, discount INT, holiday_flag INT, activity_flag INT
            )
        """)
        conn.commit()
        
        # 🔥 LOAD YOUR XLSX DATA
        try:
            cities_df = pd.read_excel('cities.csv.xlsx')
            stores_df = pd.read_excel('stores.xlsx')
            products_df = pd.read_excel('products.csv.xlsx')
            
            print(f"📊 Found: {len(cities_df)} cities, {len(stores_df)} stores, {len(products_df)} products")
            
            # TRUNCATE & RELOAD
            cur.execute("TRUNCATE TABLE sales, store, city, product RESTART IDENTITY CASCADE")
            conn.commit()
            
            # 1. CITIES (city_name column)
            for _, row in cities_df.iterrows():
                cur.execute("INSERT INTO city (cityname) VALUES (%s) ON CONFLICT DO NOTHING", (row['city_name'],))
            conn.commit()
            
            # 2. STORES (YOUR COLUMN ORDER: store_id, city_id, store_name, city_name, store_manager, password)
            # 2. STORES - DEBUG VERSION (REPLACED)
            cur.execute("SELECT cityid, cityname FROM city")
            city_map = dict(cur.fetchall())
            print(f"🏙️ City map: {list(city_map.items())[:3]}...")  # DEBUG

            successful_stores = 0
            failed_stores = 0
            # 2. STORES - USE city_id DIRECTLY (NO city_name lookup!)
            for idx, row in stores_df.iterrows():
                # ✅ YOUR PERFECT COLUMNS
                storename = str(row['store_name']).strip()
                store_manager = str(row['store_manager']).strip()
                password = str(row['password'])
                cityid_raw = row['city_id']  # USE THIS DIRECTLY!
                
                # 🔥 Convert to int, default to 1 if invalid
                try:
                    cityid = int(cityid_raw)
                except:
                    cityid = 1  # Mumbai fallback
                
                if storename and store_manager and cityid > 0:
                    cur.execute("""
                        INSERT INTO store (storename, store_manager, password, cityid) 
                        VALUES (%s, %s, %s, %s) ON CONFLICT (storename) DO NOTHING
                    """, (storename, store_manager, password, cityid))
                    successful_stores += 1

            conn.commit()
            print(f"✅ STORES LOADED: {successful_stores}/897 using city_id directly!")


            # 3. PRODUCTS
            for _, row in products_df.iterrows():
                cur.execute("INSERT INTO product (productname) VALUES (%s) ON CONFLICT DO NOTHING", (row['product_name'],))
            conn.commit()
            
            # ✅ COUNTS
            cur.execute("SELECT COUNT(*) FROM city"); city_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM store"); store_count = cur.fetchone()[0]
            print(f"✅ LOADED: {city_count} cities, {store_count} stores!")
            
        except FileNotFoundError:
            print("⚠️ No XLSX - demo data created")
            # Demo fallback
            cur.execute("INSERT INTO city (cityname) VALUES ('Mumbai') ON CONFLICT DO NOTHING")
            cur.execute("INSERT INTO store (storename, store_manager, password, cityid) VALUES ('Demo Store', 'mgr1', 'pass1', 1)")
            conn.commit()
        
        init_done = True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()




def live_updater_background():
    global all_alerts
    ensure_tables_exist()
    
    conn = get_db_conn_raw()
    cur = get_cursor(conn)
    
    # ✅ FIXED: Safe data loading
    cur.execute("SELECT productid, productname FROM product LIMIT 10")
    products = cur.fetchall()
    cur.execute("SELECT storeid, storename, cityid FROM store LIMIT 10")
    stores = cur.fetchall()
    cur.execute("SELECT cityid, cityname FROM city")
    cities = dict(cur.fetchall())
    
    if not stores or not products:
        print("⚠️ No stores/products - demo mode")
        stores = [(1, 'Demo Store', 1)]
        products = [(1, 'Demo Product')]
        cities = {1: 'Demo City'}
    
    print("🚀 Live updater started! (15s updates)")
    SALE_INTERVAL = 15
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

            # 🔥 BETTER ALERTS
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
                "storeid": storeid,
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
    ensure_tables_exist()  # 🔥 TABLES FIRST!
    if request.method=="POST":
        username = request.form.get("username")
        password = request.form.get("password")
        print(f"🔓 LOGIN ATTEMPT: {username}/{password}")
        
        # ADMIN LOGIN FIRST (NO DB NEEDED)
        if username == "admin" and password == "admin123":
            print("✅ ADMIN LOGIN SUCCESS!")
            session['user_data'] = {
                'id': 1,
                'username': 'admin',
                'role': 'admin'
            }
            user_obj = User(**session['user_data'])
            login_user(user_obj)
            return redirect(url_for('dashboard'))
        
        # STORE MANAGER LOGIN
        conn = get_db_conn_raw()
        cursor = get_cursor(conn)
        cursor.execute("SELECT storeid, storename, store_manager, cityid FROM store WHERE store_manager = %s AND password = %s", (username, password))
        store_user = cursor.fetchone()
        
        if store_user:
            print(f"✅ STORE MANAGER LOGIN: {username}")
            session['user_data'] = {
                'id': store_user[0],  # storeid
                'username': store_user[2],  # store_manager
                'role': 'store_manager',
                'storeid': store_user[0],
                'storename': store_user[1],
                'cityid': store_user[3]
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

@app.route("/my-store")
@login_required
def my_store_dashboard():
    if current_user.role != 'store_manager':
        flash("❌ Admin cannot access My Store dashboard!", "danger")
        return redirect(url_for('dashboard'))
    
    storeid = current_user.storeid
    store_alerts = [a for a in all_alerts if a.get('storeid') == storeid]
    alerts = list(reversed(store_alerts[-30:]))
    
    understock_count = len([a for a in alerts if "Restock Needed" in a['stock_alert']])
    overstock_count = len([a for a in alerts if "Overstock" in a['stock_alert']])
    okstock_count = len([a for a in alerts if "Stock OK" in a['stock_alert']])
    total_count = len(alerts)
    
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

@app.route("/admin/stores")
@login_required
def admin_stores():
    if current_user.role != 'admin':
        flash("❌ Store managers cannot access confidential admin pages!", "danger")
        return redirect(url_for('dashboard'))
    
    search = request.args.get('search', '').strip()
    conn = get_db_conn_raw()
    cursor = get_cursor(conn)
    
    if search:
        cursor.execute("""
            SELECT storeid, storename, store_manager, password, cityid 
            FROM store 
            WHERE storename LIKE %s OR store_manager LIKE %s
            ORDER BY storeid
        """, (f'%{search}%', f'%{search}%'))
    else:
        cursor.execute("SELECT storeid, storename, store_manager, password, cityid FROM store ORDER BY storeid")
    
    stores_raw = cursor.fetchall()
    stores = []
    for row in stores_raw:
        stores.append({
            'storeid': row[0],
            'storename': row[1], 
            'store_manager': row[2],
            'password': row[3],
            'cityid': row[4]
        })
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

@app.route("/")
@login_required
def dashboard():
    if current_user.role == 'store_manager':
        user_storeid = current_user.storeid
        store_alerts = [a for a in all_alerts if a.get('storeid') == user_storeid]
        alerts = list(reversed(store_alerts[-50:]))
        title = f"🛒 {current_user.storename} Dashboard"
        subtitle = f"Showing only {current_user.storename} updates"
        my_store_link = url_for('my_store_dashboard')
    else:
        alerts = list(reversed(all_alerts[-50:]))
        title = "🌟 SmartStock Admin Dashboard"
        subtitle = "All stores - Live updates"
        my_store_link = None
    
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
# 🔥 START LIVE UPDATER
def start_live_updater():
    t = threading.Thread(target=live_updater_background, daemon=True)
    t.start()
    print("🚀 Live updater started!")
def init_app():
    with app.app_context():
        ensure_tables_exist()
        t = threading.Thread(target=live_updater_background, daemon=True)
        t.start()
        print("🚀 Live updater started!")
init_app()  
if __name__ == "__main__":
    start_live_updater()  # 🔥 THIS WAS MISSING!
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    debug = os.environ.get('DEBUG', 'True').lower() == 'true'
    
    print("🌟 SmartStock Dashboard ready!")
    print("🔓 ADMIN: admin/admin123")
    print("🔓 STORE MGR: mgr1/pass1")
    app.run(host=host, port=port, debug=debug)
