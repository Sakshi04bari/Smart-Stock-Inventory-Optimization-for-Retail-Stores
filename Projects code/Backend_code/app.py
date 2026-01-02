# app.py - COMPLETE SmartStock Dashboard (POSTGRESQL ✅ + LIVE UPDATES FIXED ✅)
import threading, time, random
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from flask_mail import Mail, Message  # 🔥 NEW: EMAIL SUPPORT
from sqlalchemy import create_engine, text
import os 
from dotenv import load_dotenv       
from sqlalchemy.engine import URL
import pandas as pd
import mysql.connector
import xgboost as xgb
import psycopg2  # 🔥 POSTGRESQL SUPPORT
from urllib.parse import urlparse   # 🔥 POSTGRESQL URL PARSER

# Config - DEPLOYMENT READY
load_dotenv()
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "Bhakthi@13")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_NAME = os.getenv("DB_NAME", "smartstock_dynamic")
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "smartstock-super-secret-key-2025")
app.config['MAIL_SERVER'] = 'smtp.sendgrid.net'     # 🔥 SENDGRID
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'apikey'              # 🔥 CRITICAL
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')  # SG.xxx
mail = Mail(app)  # 🔥 Initialize Mail
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
# Flask + Login
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
# Live Alerts Storage
all_alerts = []
all_forecasts = [] 
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS city (
                cityid SERIAL PRIMARY KEY, 
                cityname VARCHAR(50) NOT NULL
            )
        """)
        conn.commit()  # 🔥 CRITICAL
        cur.execute("""
            CREATE TABLE IF NOT EXISTS store (
                storeid SERIAL PRIMARY KEY, 
                storename VARCHAR(50) NOT NULL,
                store_manager VARCHAR(50), 
                password VARCHAR(50), 
                cityid INT REFERENCES city(cityid)
            )
        """)
        conn.commit()  # 🔥 CRITICAL
        cur.execute("""
            CREATE TABLE IF NOT EXISTS login_logs (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                role VARCHAR(20),
                storeid INT,
                storename VARCHAR(50),
                ip_address INET,
                user_agent TEXT,
                success BOOLEAN NOT NULL,
                login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cityid INT
            )
        """)
        conn.commit()
        print("✅ Login logs table created")
        try:
            cur.execute("""
                ALTER TABLE store 
                ADD CONSTRAINT store_storename_unique 
                UNIQUE (storename)
            """)
            conn.commit()  # 🔥 COMMIT constraint separately
            print("✅ UNIQUE constraint added")
        except Exception as e:
            conn.rollback()  # 🔥 ROLLBACK constraint error only
            print(f"ℹ️ UNIQUE constraint: {e}")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS product (
                productid SERIAL PRIMARY KEY, 
                productname VARCHAR(50) NOT NULL UNIQUE
            )
        """)
        conn.commit()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY, 
                dt TIMESTAMP, cityid INT, storeid INT, 
                productid INT, sale_amount INT, stock INT, 
                hour INT, discount INT, holiday_flag INT, activity_flag INT
            )
        """)
        conn.commit()
        try:
            cities_df = pd.read_excel('cities.csv.xlsx')
            stores_df = pd.read_excel('stores.xlsx')
            products_df = pd.read_excel('products.csv.xlsx')
            
            print(f"📊 Found: {len(cities_df)} cities, {len(stores_df)} stores, {len(products_df)} products")
            try:
                cur.execute("TRUNCATE TABLE sales RESTART IDENTITY")
                cur.execute("TRUNCATE TABLE store RESTART IDENTITY") 
                cur.execute("TRUNCATE TABLE city RESTART IDENTITY")
                cur.execute("TRUNCATE TABLE product RESTART IDENTITY")
                conn.commit()
            except:
                cur.execute("TRUNCATE TABLE sales")
                cur.execute("TRUNCATE TABLE store") 
                cur.execute("TRUNCATE TABLE city")
                cur.execute("TRUNCATE TABLE product")
            conn.commit()
            print("🔗 PERFECT City-Store sync...")
            store_cities_df = stores_df[['city_id', 'city_name']].dropna().groupby('city_id')['city_name'].first()
            print(f"📍 Stores expect: {dict(list(store_cities_df.items())[:5])}...")
            cur.execute("DELETE FROM city")
            conn.commit()
            for cityid, cityname in store_cities_df.items():
                cityid_int = int(cityid) if cityid is not None else 1
                cur.execute("INSERT INTO city (cityid, cityname) VALUES (%s, %s) ON CONFLICT (cityid) DO NOTHING", 
                            (cityid_int, str(cityname).strip()))
            conn.commit()
            for _, row in cities_df.iterrows():
                cur.execute("INSERT INTO city (cityname) VALUES (%s) ON CONFLICT DO NOTHING", 
                        (row['city_name'],))
            conn.commit()
            cur.execute("SELECT cityid, cityname FROM city")
            city_map = dict(cur.fetchall())
            print(f"🏙️ City map: {list(city_map.items())[:3]}...")
            successful_stores = 0
            failed_stores = 0
            for idx, row in stores_df.iterrows():
                storename = str(row['store_name']).strip()
                store_manager = str(row['store_manager']).strip()
                password = str(row['password'])
                cityid_raw = row['city_id']
                try:
                    cityid = int(cityid_raw)
                    print(f"📍 {storename} → cityid={cityid}")
                except (ValueError, TypeError):
                    cityid = 1
                    print(f"⚠️ {storename} bad city_id={cityid_raw} → 1")
                if storename:
                    try:
                        cur.execute("""
                            INSERT INTO store (storename, store_manager, password, cityid) 
                            VALUES (%s, %s, %s, %s) ON CONFLICT (storename) DO NOTHING
                        """, (storename, store_manager or 'mgr_default', password or 'pass_default', cityid))
                        successful_stores += 1
                    except Exception as e:
                        failed_stores += 1
                        if failed_stores < 5:
                            print(f"❌ Store {idx}: {e}")
            conn.commit()  # ← OUTSIDE LOOP!
            print(f"✅ STORES: {successful_stores} loaded, {failed_stores} failed")
            print(f"🏪 Sample stores: {successful_stores > 0 and 'YES' or 'NO'}")
            for _, row in products_df.iterrows():
                cur.execute("INSERT INTO product (productname) VALUES (%s) ON CONFLICT DO NOTHING", (row['product_name'],))
            conn.commit()
            cur.execute("SELECT COUNT(*) FROM city"); city_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM store"); store_count = cur.fetchone()[0]
            print(f"✅ LOADED: {city_count} cities, {store_count} stores!")        
        except FileNotFoundError:
            print("⚠️ No XLSX - demo data created")
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
def ensure_sales_timestamp():
    """Add created_at + backfill ALL existing records"""
    try:
        pd.read_sql(text("SELECT created_at FROM sales LIMIT 1"), engine)
        print("✅ sales.created_at exists!")
        return
    except:
        print("🔧 Creating created_at column + backfilling...")
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE sales ADD COLUMN created_at TIMESTAMP;"))
            # 🔥 BACKFILL: id → approximate date (older id = older date)
            conn.execute(text("""
                UPDATE sales 
                SET created_at = NOW() - INTERVAL '1 day' * (1000000 - id) / 1000000
                WHERE created_at IS NULL
            """))
            conn.commit()
        print("✅ created_at column + 1M+ records backfilled!")

# CALL ON STARTUP (before app.run)


def send_stock_alert_email(alert):
    """🚨 smartstockretaila@gmail.com → YOUR 3 manager emails"""
    try:
        conn = get_db_conn_raw()
        cursor = get_cursor(conn)
        cursor.execute("""
            SELECT s.email, s.store_manager, c.cityname, s.storename 
            FROM store s 
            JOIN city c ON s.cityid = c.cityid 
            WHERE s.storeid = %s
        """, (alert['storeid'],))
        store_info = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if store_info and store_info[0]:  # Has email
            manager_email, manager_name, city, store_name = store_info
            
            # 🔥 Beautiful HTML email
            subject = f"🚨 {alert['stock_alert']} - {alert['product']} @ {store_name}"
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                            color: white; padding: 20px; border-radius: 12px; text-align: center;">
                    <h1 style="margin: 0; font-size: 28px;">🚨 SmartStock Alert</h1>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">From SmartStock Admin</p>
                </div>
                
                <div style="background: #f8f9fa; padding: 25px; border-radius: 12px; margin: 20px 0; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                    <h2 style="color: #dc3545; margin-top: 0;">{alert['stock_alert']}</h2>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0;">
                        <div>
                            <strong>📍 Store:</strong><br>
                            <span style="font-size: 18px; color: #495057;">{city} - {store_name}</span>
                        </div>
                        <div>
                            <strong>📦 Product:</strong><br>
                            <span style="font-size: 18px; color: #495057;">{alert['product']}</span>
                        </div>
                    </div>
                    <div style="background: white; padding: 20px; border-radius: 8px; border-left: 5px solid #dc3545;">
                        <h3 style="margin-top: 0; color: #dc3545;">
                            📊 Current Stock: <span style="font-size: 32px; font-weight: bold;">{alert['stock']}</span>
                        </h3>
                        <p><strong>💰 Last Sale:</strong> -{alert['sale']} units</p>
                        <p><strong>👤 Manager:</strong> {manager_name}</p>
                    </div>
                </div>
                
                <a href="https://smartstock-retail-optimizer.onrender.com/dashboard" 
                   style="background: #0d6efd; color: white; padding: 15px 30px; 
                          text-decoration: none; border-radius: 8px; font-weight: bold; 
                          display: inline-block; box-shadow: 0 4px 12px rgba(13,110,253,0.3);">
                    👉 View Dashboard Now
                </a>
                
                <p style="text-align: center; color: #6c757d; font-size: 14px; margin-top: 30px;">
                    This is an automated alert from <strong>SmartStock Inventory Optimizer</strong><br>
                    Sent from: smartstockretaila@gmail.com
                </p>
            </div>
            """
            msg = Message(
                subject=subject,
                sender='smartstockretaila@gmail.com',  # Admin
                recipients=[manager_email],           # Your 3 emails
                html=html_body
            )
            mail.send(msg)
            print(f"📧 ✅ SENT → {manager_name} ({manager_email}): {alert['stock_alert']}")
    except Exception as e:
        print(f"❌ Email failed: {e}")

def live_updater_background():
    global all_alerts
    ensure_tables_exist()
    conn = get_db_conn_raw()
    cur = get_cursor(conn)
    try:
        cur.execute("SELECT created_at FROM sales LIMIT 1")
        cur.fetchone()
        print("✅ created_at column exists!")
    except:
        print("🔧 Adding created_at column...")
        cur.execute("ALTER TABLE sales ADD COLUMN created_at TIMESTAMP")
        cur.execute("""
            UPDATE sales SET created_at = NOW() - (id * INTERVAL '1 second')
        """)  # Backfill: id=1=oldest, id=1000000=today
        conn.commit()
        print("✅ created_at added + backfilled!")
    cur.close()
    conn.close()
    conn = get_db_conn_raw()
    cur = get_cursor(conn)
    try:
        cur.execute("SELECT productid, productname FROM product")
        products = cur.fetchall() or []
        cur.execute("SELECT storeid, storename, cityid FROM store")
        stores = cur.fetchall() or []
        cur.execute("SELECT cityid, cityname FROM city")
        cities_raw = cur.fetchall() or []
        cities = {}
        for row in cities_raw:
            cities[row[0]] = row[1] or f"City_{row[0]}"  # ✅ Handle NULL/0
        print(f"🚀 LIVE: {len(stores)} stores, {len(products)} products, {len(cities)} cities")  
        if not stores or not products:
            print("⚠️ Demo mode")
            stores = [(1, 'Demo Store', 1)]
            products = [(1, 'Demo Product')]
            cities = {1: 'Demo City'}
        print("🚀 Live updater LOOP STARTED! (15s)")
        SALE_INTERVAL = 60
        while True:
            now = datetime.now()
            store_row = random.choice(stores)
            product_row = random.choice(products)
            storeid, storename, cityid = store_row
            productid, productname = product_row
            cur.execute("SELECT cityname FROM city WHERE cityid=%s", (cityid,))
            city_result = cur.fetchone()
            cityname = city_result[0] if city_result else f"City_{cityid}"
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
            now_utc = datetime.now(timezone.utc)  # TRUE UTC
            ist_offset = timedelta(hours=5, minutes=30)
            now_ist = now_utc + ist_offset        # Proper IST
            cur.execute("""
                INSERT INTO sales (dt, cityid, storeid, productid, sale_amount, stock, hour, discount, holiday_flag, activity_flag)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (now_ist, cityid, storeid, productid, sale_amount, new_stock, hour, discount, holiday_flag, activity_flag))
            conn.commit()
            
            # 🔥 365 DAYS CLEANUP (EXACT indentation):
            cur.execute("""
                DELETE FROM sales 
                WHERE created_at < NOW() - INTERVAL '365 days'
            """)
            conn.commit()
            print(f"🧹 Cleaned sales older than 365 days")

            cur.execute(
                "SELECT stock FROM sales WHERE storeid=%s AND productid=%s ORDER BY dt DESC LIMIT 1",
                (storeid, productid)
            )

            r = cur.fetchone()
            current_stock = r[0] if r else new_stock  # Use DB stock or fallback
            new_stock = max(current_stock - sale_amount, 0)  # Recalculate
            recent_forecasts = run_xgboost_forecast(conn, cur)
            if random.random() < 0.35:  # 35% Overstock
                new_stock += random.randint(35, 60)
                stock_alert = "Overstock 🚨"
            elif random.random() < 0.60:  # 25% Understock  
                new_stock = random.randint(0, 3)
                stock_alert = "Restock Needed ⚠️"
            else:  # 40% OK
                stock_alert = "Stock OK ✅"
            forecast_alert = "🟢 Stock OK"
            if recent_forecasts:
                for f in recent_forecasts:
                    if f['storeid'] == storeid and f['productid'] == productid:
                        forecast_alert = f['forecast_alert']
                        break
            alert = {
                "city": cityname,
                "store": storename,
                 "storeid": storeid,
                "product": productname,
                "sale": int(sale_amount),
                "stock": int(new_stock),
                "stock_alert": stock_alert,
                "email_status": "⏳ PENDING", 
                "forecast": forecast_alert,           # ✅ 🔴Restock Likely
                "timestamp": now_ist.strftime("%Y-%m-%d %H:%M:%S")  # ✅ 16:30 IST
                
            }
            # 🔥 EMAILS FOR BOTH CONDITIONS:
            if "Restock Needed" in alert['stock_alert'] or "Overstock" in alert['stock_alert']:
                try:
                    send_stock_alert_email(alert)
                    alert["email_status"] = "✅ SENT"  # ✅ Update AFTER success
                    print(f"📧 ✅ SENT → {alert['store']} ({alert['stock_alert']})")
                except Exception as e:
                    alert["email_status"] = "❌ FAILED"
                    print(f"❌ Email failed: {e}")
            all_alerts.append(alert)
            if len(all_alerts) > 10000:
                all_alerts = all_alerts[-10000:]
            print(f"[{alert['timestamp']}] {alert['city']} / {alert['store']} / {alert['product']} → {alert['stock_alert']} | {alert['forecast']}")
            time.sleep(60) 
    finally:
        cur.close()
        conn.close()
def run_xgboost_forecast(conn, cur):
    global all_forecasts
    try:
        now = datetime.now()
        past_30_days = now - timedelta(days=30)
        df = pd.read_sql(text("""
            SELECT storeid, productid, dt, sale_amount, stock, discount, holiday_flag, activity_flag
            FROM sales WHERE dt >= :past
            ORDER BY dt ASC
        """), engine, params={"past": past_30_days})
        df['dt'] = pd.to_datetime(df['dt'])
        df['day_of_week'] = df['dt'].dt.dayofweek
        forecasts = []
        df['day_of_week'] = df['dt'].dt.dayofweek
        for (s_id, p_id), group in df.groupby(['storeid','productid']):
            if len(group) < 7:
                predicted_sales_7d = group['sale_amount'].mean() * 7 if len(group)>0 else 20
            else:
                X = group[['day_of_week','stock','discount','holiday_flag','activity_flag']]
                y = group['sale_amount']
                model = xgb.XGBRegressor(objective='reg:squarederror', n_estimators=50)
                model.fit(X, y)
                last_row = group.iloc[-1]
                predictions = []
                for i in range(1,8):
                    day_of_week = (last_row['day_of_week'] + i) % 7
                    X_pred = pd.DataFrame([{
                        'day_of_week': day_of_week, 'stock': last_row['stock'],
                        'discount': last_row['discount'], 'holiday_flag': last_row['holiday_flag'],
                        'activity_flag': last_row['activity_flag']
                    }])
                    pred_sale = model.predict(X_pred)[0]
                    predictions.append(pred_sale)
                predicted_sales_7d = sum(predictions)
            forecast_alert = "🔴 Restock Likely" if predicted_sales_7d > 40 else "🟢 Stock OK"
            forecasts.append({
                'storeid': s_id, 'productid': p_id,
                'predicted_7d_sales': round(predicted_sales_7d, 1),
                'forecast_alert': forecast_alert,
                'timestamp': now.strftime("%H:%M:%S")
            })
        all_forecasts = forecasts[-100:]  # Keep latest 100
        print(f"🔮 XGBoost: {len(forecasts)} forecasts generated!")
        return forecasts
    except Exception as e:
        print(f"⚠️ Forecast error: {e}")
        return []
def get_fresh_alerts_from_db(limit=1000):
    """🔥 Get REAL latest alerts from sales table - FIXED!"""
    try:
        conn = get_db_conn_raw()
        cur = get_cursor(conn)
        cur.execute("""
            SELECT 
                c.cityname, s.storename, s.storeid, p.productname,  -- ✅ s.storeid FIXED!
                sa.sale_amount, sa.stock, sa.dt
            FROM sales sa
            JOIN store s ON sa.storeid = s.storeid
            JOIN city c ON s.cityid = c.cityid
            JOIN product p ON sa.productid = p.productid
            ORDER BY sa.dt DESC LIMIT %s
        """, (limit,))
        alerts = []
        for row in cur.fetchall():
            city, store, storeid, product, sale, stock, dt = row
            stock_alert = "Restock Needed ⚠️" if stock < 5 else "Overstock 🚨" if stock > 40 else "Stock OK ✅"
            alerts.append({
                'city': city, 'store': store, 'storeid': storeid,
                'product': product, 'sale': sale, 'stock': stock,
                'stock_alert': stock_alert, 'forecast': '🟢 From DB',
                'timestamp': dt.strftime("%Y-%m-%d %H:%M:%S")
            })
        cur.close()
        conn.close()
        print(f"🔥 DB Fresh alerts: {len(alerts)}")
        return alerts
    except Exception as e:
        print(f"⚠️ DB alerts error: {e}")
        return []
@app.route("/login", methods=["GET","POST"])
def login():
    ensure_tables_exist()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        client_ip = request.remote_addr or "127.0.0.1"
        
        print(f"🔓 LOGIN ATTEMPT: {username} from {client_ip}")
        
        conn = get_db_conn_raw()
        cursor = get_cursor(conn)
        
        # 🔥 1-QUERY SOLUTION: Insert + Update in ONE transaction
        success = False
        role = 'unknown'
        storeid = None
        storename = None
        cityid = None
        
        # CHECK CREDENTIALS FIRST
        if username == "admin" and password == "admin123":
            success = True
            role = "admin"
            print("✅ ADMIN LOGIN SUCCESS")
        else:
            cursor.execute("""
                SELECT storeid, storename, cityid 
                FROM store WHERE store_manager = %s AND password = %s
            """, (username, password))
            store_row = cursor.fetchone()
            if store_row:
                storeid, storename, cityid = store_row
                success = True
                role = "store_manager"
                print(f"✅ STORE LOGIN: {storename}")
        
        # 🔥 SINGLE INSERT with ALL data (NO UPDATE needed!)
        cursor.execute("""
            INSERT INTO login_logs (username, ip_address, success, role, storeid, storename, cityid)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (username, client_ip, success, role, storeid, storename, cityid))
        conn.commit()
        print(f"✅ LOGIN LOG SAVED: {username} = {success}")
        
        cursor.close()
        conn.close()
        
        if success:
            session['user_data'] = {
                'id': storeid or 1, 'username': username, 'role': role,
                'storeid': storeid, 'storename': storename, 'cityid': cityid
            }
            login_user(User(**session['user_data']))
            print(f"🚀 REDIRECT TO DASHBOARD: {username}")
            return redirect(url_for('dashboard'))
        else:
            print(f"❌ LOGIN FAILED: {username}")
            flash("Invalid credentials!", "danger")
    
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
    fresh_db = get_fresh_alerts_from_db(limit=1000)
    all_store_alerts = [a for a in fresh_db + all_alerts if a.get('storeid') == storeid]
    alerts = list(reversed(all_store_alerts[-30:]))
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
            ORDER BY storeid ASC
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

@app.route("/admin/login-logs")
@login_required
def admin_login_logs():
    if current_user.role != 'admin':
        flash("❌ Admin only!", "danger")
        return redirect(url_for('dashboard'))
    
    conn = get_db_conn_raw()
    cursor = get_cursor(conn)
    
    cursor.execute("""
        SELECT 
            ll.login_time AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' as ist_time,
            ll.username,
            CASE 
                WHEN ll.storename IS NOT NULL AND ll.storename != '' AND ll.storename != '-' THEN 
                    COALESCE((SELECT cityname FROM city WHERE cityid = ll.cityid), 'Unknown') || ' - ' || ll.storename
                ELSE '-' 
            END as store_display,
            ll.success
        FROM login_logs ll 
        ORDER BY ll.login_time DESC LIMIT 50
    """)
    
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    
    html = f"""
    <div style='max-width:1000px; margin:20px auto; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;'>
        <h2 style='color:#0d6efd; margin-bottom:20px;'>📊 Login Logs (<span style='color:#198754;'>{len(logs)}</span>)</h2>
        <div style='background:white; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,0.1); overflow:hidden;'>
            <table style='width:100%; border-collapse:collapse;'>
                <thead>
                    <tr style='background:linear-gradient(135deg,#0d6efd,#1e88e5); color:white;'>
                        <th style='padding:18px 15px; text-align:left; font-weight:600;'>Time (IST)</th>
                        <th style='padding:18px 15px; text-align:left; font-weight:600;'>User</th>
                        <th style='padding:18px 15px; text-align:left; font-weight:600;'>Store</th>
                        <th style='padding:18px 15px; text-align:left; font-weight:600;'>Status</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    for row in logs:
        ist_time, username, store, success = row
        status = "✅ SUCCESS" if success else "❌ FAILED"
        status_color = "#d1e7dd; color:#0f5132; padding:10px 20px;" if success else "#f8d7da; color:#721c24; padding:10px 20px;"
        
        html += f"""
            <tr style='border-bottom:2px solid #f8f9fa;'>
                <td style='padding:20px 15px; font-size:14px; font-weight:500;'>{ist_time}</td>
                <td style='padding:20px 15px; font-weight:700; color:#1f2937;'>{username}</td>
                <td style='padding:20px 15px; color:#4b5563; font-size:14px;'>{store}</td>
                <td style='padding:20px 15px; text-align:center;'>
                    <span style='background:{status_color}border-radius:25px;font-weight:700;font-size:14px;display:inline-block;min-width:120px;text-align:center;'>{status}</span>
                </td>
            </tr>
        """
    
    html += """
                </tbody>
            </table>
        </div>
        <div style='margin-top:25px; text-align:center;'>
            <a href="/" class="btn btn-primary mb-3" style='background:linear-gradient(135deg,#6c757d,#5a6268); color:white; padding:14px 28px; text-decoration:none; border-radius:10px; font-weight:600; font-size:15px; box-shadow:0 4px 15px rgba(108,117,125,0.3); display:inline-block;'>← Back to Dashboard</a>
        </div>
    </div>
    """
    return html

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
                WHERE c.cityname ILIKE :s  -- 🔥 CASE-INSENSITIVE!
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
@app.route("/stores/city/<int:cityid>")
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
            ORDER BY storeid ASC
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
        sql_query = """
            SELECT 
                p.productid,
                p.productname,
                COALESCE(s_latest.stock, 50) as stock,
                COALESCE(sales_sum.total_sales, 0) as total_sales,
                CASE
                    WHEN COALESCE(s_latest.stock, 50) < 5 THEN '🔴 Low Stock'
                    WHEN COALESCE(s_latest.stock, 50) > 40 THEN '🟢 Overstock'
                    ELSE '🟡 OK Stock'
                END as status
            FROM product p
            LEFT JOIN (
                SELECT storeid, productid, stock
                FROM sales s1
                WHERE storeid = :sid 
                AND s1.id = (
                    SELECT MAX(s2.id) 
                    FROM sales s2 
                    WHERE s2.storeid = s1.storeid 
                    AND s2.productid = s1.productid
                )
            ) s_latest ON p.productid = s_latest.productid
            LEFT JOIN (
                SELECT productid, SUM(sale_amount) as total_sales
                FROM sales
                WHERE storeid = :sid
                GROUP BY productid
            ) sales_sum ON p.productid = sales_sum.productid
        """
        if search:
            sql_query += " WHERE p.productname ILIKE :s"

        sql_query += """
            ORDER BY total_sales DESC NULLS LAST
            LIMIT 50
        """
        df = pd.read_sql(text(sql_query), engine, params={"sid": storeid, "s": f"%{search}%"} if search else {"sid": storeid})
        store_df = pd.read_sql(text("SELECT storename FROM store WHERE storeid=:sid"), engine, params={"sid": storeid})
        storename = store_df.iloc[0]['storename'] if not store_df.empty else f"Store {storeid}"
        print(f"📦 Store {storeid} ({storename}): {len(df)} products, top sales: {df['total_sales'].max()}")
        return render_template("store_products.html", 
                             products=df.to_dict('records'), 
                             storename=storename, 
                             storeid=storeid, 
                             user=current_user)
    except Exception as e:
        print(f"❌ Store products error: {e}")
        return f"<h1>Store {storeid} Products: Error {str(e)}</h1>"
    
@app.route("/email-status")
@login_required
def email_status_page():
    if current_user.role != 'admin':
        flash("❌ Admin only!", "danger")
        return redirect(url_for('dashboard'))
    
    # 🔥 USE all_alerts[] MEMORY (NO SQL NEEDED)
    recent_alerts = []
    for alert in reversed(all_alerts[-100:]):  # Last 100 alerts
        if 'email_status' in alert and ('Restock Needed' in alert['stock_alert'] or 'Overstock' in alert['stock_alert']):
            # Add store manager info
            alert_copy = alert.copy()
            try:
                conn = get_db_conn_raw()
                cur = get_cursor(conn)
                cur.execute("SELECT store_manager FROM store WHERE storeid=%s", (alert['storeid'],))
                mgr = cur.fetchone()
                alert_copy['store_manager'] = mgr[0] if mgr else 'Unknown'
                cur.close()
                conn.close()
            except:
                alert_copy['store_manager'] = 'N/A'
            recent_alerts.append(alert_copy)
    print(f"📧 Status page: {len(recent_alerts)} alerts")
    return render_template("email_status.html", alerts=recent_alerts, user=current_user)

@app.route("/admin/users")
@login_required
def admin_users():
    if current_user.role != 'admin':
        flash("❌ Admin only!", "danger")
        return redirect(url_for('dashboard'))
    dashboard_url = url_for('dashboard')
    print("DEBUG dashboard_url =", dashboard_url)
    conn = get_db_conn_raw()
    cursor = get_cursor(conn)
    cursor.execute("""
        SELECT DISTINCT username, role, COUNT(*) as login_count,
               MIN(login_time) AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' as first_login,
               MAX(login_time) AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' as last_login
        FROM login_logs 
        WHERE success = TRUE
        GROUP BY username, role 
        ORDER BY last_login DESC
    """)
    user_stats = cursor.fetchall()
    cursor.close()
    conn.close()
    
    html = f"""
    <div style='max-width:1200px; margin:20px auto; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;'>
        <h2 style='color:#0d6efd; margin-bottom:20px;'>👥 Active Users (<span style='color:#198754;'>{len(user_stats)}</span>)</h2>
        <div style='background:white; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,0.1); overflow:hidden;'>
            <table style='width:100%; border-collapse:collapse;'>
                <thead>
                    <tr style='background:linear-gradient(135deg,#0d6efd,#1e88e5); color:white;'>
                        <th style='padding:18px 15px; text-align:left; font-weight:600; width:25%;'>User</th>
                        <th style='padding:18px 15px; text-align:left; font-weight:600; width:20%;'>     Role</th>
                        <th style='padding:18px 15px; text-align:center; font-weight:600; width:15%;'>Logins</th>
                        <th style='padding:18px 15px; text-align:center; font-weight:600; width:20%;'>First Login</th>
                        <th style='padding:18px 15px; text-align:center; font-weight:600; width:20%;'>Last Login</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    for row in user_stats:
        username, role, login_count, first_login, last_login = row
        role_color = "#198754" if role == 'admin' else "#0dcaf0"
        
        html += f"""
            <tr style='border-bottom:2px solid #f8f9fa;'>
                <td style='padding:20px 15px; font-weight:700; color:#1f2937; font-size:15px;'>{username}</td>
                <td style='padding:20px 15px; text-align:center;'>
                    <span style='background:{role_color}; color:white; padding:8px 16px; border-radius:20px; font-weight:600; font-size:13px; min-width:100px; display:inline-block;'>{role}</span>
                </td>
                <td style='padding:20px 15px; text-align:center; font-weight:700; color:#059669; font-size:16px; background:#f0fdf4; border-radius:8px; width:15%;'>{login_count}</td>
                <td style='padding:20px 15px; text-align:center; color:#6b7280; font-size:14px;'>{first_login.strftime('%Y-%m-%d')}</td>
                <td style='padding:20px 15px; text-align:center; font-weight:600; color:#0d6efd; font-size:14px;'>{last_login.strftime('%H:%M:%S')}</td>
            </tr>
        """
    
    html += f"""
                </tbody>
            </table>
        </div>
        <div style='margin-top:25px; text-align:center;'>
            <a href='/admin/login-logs' style='background:linear-gradient(135deg,#198754,#146c43); color:white; padding:12px 24px; text-decoration:none; border-radius:10px; margin-right:15px; font-weight:600; box-shadow:0 4px 15px rgba(25,135,84,0.3);'>📊 Full Login Logs</a>
            <a href='/admin/stores' style='background:linear-gradient(135deg,#0d6efd,#1e88e5); color:white; padding:12px 24px; text-decoration:none; border-radius:10px; margin-right:15px; font-weight:600; box-shadow:0 4px 15px rgba(13,110,253,0.3);'>🏪 Store Managers</a>
            <a href='{dashboard_url}' style='background:linear-gradient(135deg,#6c757d,#5a6268); color:white; padding:12px 24px; text-decoration:none; border-radius:10px; font-weight:600; box-shadow:0 4px 15px rgba(108,117,125,0.3);'>← Dashboard</a>
        </div>
    </div>
    """
    return html

@app.route("/")
@login_required
def dashboard():
    fresh_alerts = get_fresh_alerts_from_db(limit=1000) 
    if current_user.role == 'store_manager':
        user_storeid = current_user.storeid
        store_alerts = [a for a in fresh_alerts + all_alerts if a.get('storeid') == user_storeid]
        alerts = list(reversed(store_alerts[-50:]))
        title = f"🛒 {current_user.storename} Dashboard"
        subtitle = f"Showing only {current_user.storename} updates ({len(alerts)} fresh)"
        my_store_link = url_for('my_store_dashboard')
    else:
        combined_alerts = fresh_alerts + all_alerts
        alerts = list(reversed(combined_alerts))[-200:]
        title = "🌟 SmartStock Admin Dashboard"
        subtitle = f"All stores - {len(alerts)} live updates"
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
                         forecast_restocks=len([f for f in all_forecasts if "Restock" in f['forecast_alert']]),     
                         forecast_ok=len(all_forecasts) - len([f for f in all_forecasts if "Restock" in f['forecast_alert']]),                
                         forecasts=all_forecasts[-10:], 
                         title=title,
                         subtitle=subtitle,
                         my_store_link=my_store_link,
                         user=current_user,
                         CACHE_BUST=f"{int(time.time())}")  
@app.route("/overstock")
@login_required
def overstock_page():
    fresh_db = get_fresh_alerts_from_db(limit=1000)
    combined_alerts = fresh_db + all_alerts
    if current_user.role == 'store_manager':
        user_storeid = current_user.storeid
        alerts = [a for a in reversed(combined_alerts) if "Overstock" in a['stock_alert'] and a.get('storeid') == user_storeid]
        page_title = f"{current_user.storename} - Overstock Alerts ({len(alerts)})"
    else:
        alerts = [a for a in reversed(combined_alerts) if "Overstock" in a['stock_alert']]
        page_title = f"All Stores - Overstock Alerts ({len(alerts)})"
    return render_template("overstock.html", alerts=alerts[-200:], title=page_title, user=current_user)
@app.route("/understock")
@login_required
def understock_page():
    fresh_db = get_fresh_alerts_from_db(limit=1000)
    combined_alerts = fresh_db + all_alerts
    if current_user.role == 'store_manager':
        user_storeid = current_user.storeid
        alerts = [a for a in reversed(combined_alerts) if "Restock" in a['stock_alert'] and a.get('storeid') == user_storeid]
        page_title = f"{current_user.storename} - Understock Alerts ({len(alerts)})"
    else:
        alerts = [a for a in reversed(combined_alerts) if "Restock" in a['stock_alert']]
        page_title = f"All Stores - Understock Alerts ({len(alerts)})"
    return render_template("understock.html", alerts=alerts[-200:], title=page_title, user=current_user)
@app.route("/ok-stock")
@login_required
def ok_stock_page():
    fresh_db = get_fresh_alerts_from_db(limit=1000)
    combined_alerts = fresh_db + all_alerts
    if current_user.role == 'store_manager':
        user_storeid = current_user.storeid
        alerts = [a for a in reversed(combined_alerts) if "Stock OK" in a['stock_alert'] and a.get('storeid') == user_storeid]
        page_title = f"{current_user.storename} - Stock OK ({len(alerts)})"
    else:
        alerts = [a for a in reversed(combined_alerts) if "Stock OK" in a['stock_alert']]
        page_title = f"All Stores - Stock OK ({len(alerts)})"
    return render_template("ok_stock.html", alerts=alerts[-200:], title=page_title, user=current_user)
@app.route("/api/alerts")
@login_required
def get_alerts_api():
    n = int(request.args.get("n", 200))
    fresh_db = get_fresh_alerts_from_db(limit=1000)  # 🔥 FIXED: Always 1000
    combined = fresh_db + all_alerts
    if current_user.role == 'store_manager':
        user_storeid = current_user.storeid
        alerts = [a for a in reversed(combined) if a.get('storeid') == user_storeid][-n:]
    else:
        alerts = list(reversed(combined))[-n:]
    return jsonify(alerts)
@app.route("/restart-live")
@login_required
def restart_live():
    if current_user.role != 'admin':
        flash("❌ Admin only!", "danger")
        return redirect(url_for('dashboard'))
    global live_thread
    if live_thread and live_thread.is_alive():
        print("🛑 Stopping old live thread...")
    start_live_updater_once()  # 🔥 RESTARTS IMMEDIATELY
    flash("🚀 Live updater RESTARTED! Check /debug", "success")
    return redirect(url_for('debug'))
@app.route("/toggle-theme")
@login_required
def toggle_theme():
    current_theme = session.get('theme', 'light')
    session['theme'] = 'dark' if current_theme == 'light' else 'light'
    return redirect(request.referrer or url_for('dashboard'))
live_thread = None
def start_live_updater_once():
    global live_thread
    if live_thread is None or not live_thread.is_alive():
        live_thread = threading.Thread(target=live_updater_background, daemon=True)
        live_thread.start()
        print("🚀 Live updater restarted!")
        threading.Timer(300.0, start_live_updater_once).start()
def init_app():
    with app.app_context():
        ensure_tables_exist()
        ensure_sales_timestamp()
        start_live_updater_once()  # ✅ SINGLE CALL
init_app()
@app.route("/debug")
def debug():
    return jsonify({
        "alerts_count": len(all_alerts),
        "forecasts_count": len(all_forecasts),
        "live_thread_alive": live_thread is not None and live_thread.is_alive() if 'live_thread' in globals() else False,
        "thread_count": threading.active_count()
    })
@app.route("/history")
@login_required
def product_history_page():
    if current_user.role != 'admin':
        flash("❌ Admin only!", "danger")
        return redirect(url_for('dashboard'))
    
    return render_template("product_history.html", user=current_user)

@app.route("/api/history-search")
@login_required
def history_search():
    if current_user.role != 'admin':
        return jsonify({"error": "Admin only!"}), 403
    
    try:
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to", date_from)
        city = request.args.get("city", "").strip()
        store = request.args.get("store", "").strip()
        product = request.args.get("product", "").strip()
        params = {}
        sql = """
        SELECT 
            s.dt as timestamp,
            s.id as record_id,
            s.storeid, st.storename, c.cityname,
            s.productid, p.productname, 
            s.stock, s.sale_amount,
            CASE 
                WHEN s.stock < 5 THEN '🔴 Low Stock'
                WHEN s.stock > 40 THEN '🟡 Overstock'
                ELSE '🟢 OK'
            END as stock_status
        FROM sales s
        JOIN store st ON s.storeid = st.storeid
        JOIN city c ON st.cityid = c.cityid
        JOIN product p ON s.productid = p.productid
        WHERE 1=1
        """
        if date_from: sql += " AND DATE(s.dt) >= :date_from"; params["date_from"] = date_from
        if date_to:   sql += " AND DATE(s.dt) <= :date_to"; params["date_to"] = date_to
        if city:      sql += " AND c.cityname ILIKE :city"; params["city"] = f"%{city}%"
        if store:     sql += " AND st.storename ILIKE :store_name"; params["store_name"] = f"%{store}%"
        if product:   sql += " AND p.productname ILIKE :product"; params["product"] = f"%{product}%"
        
        sql += " ORDER BY s.dt DESC LIMIT 100"
        df = pd.read_sql(text(sql), engine, params=params)
        return jsonify(df.to_dict('records'))
    except Exception as e:
        print(f"❌ History search error: {e}")
        return jsonify({"error": str(e)}), 500

    
@app.route("/api/cities")
def api_cities():
    search = request.args.get("search", "").lower()
    df = pd.read_sql(text("""
        SELECT cityname, COUNT(storeid) as store_count 
        FROM city c LEFT JOIN store s ON c.cityid = s.cityid 
        GROUP BY cityname 
        HAVING LOWER(cityname) LIKE :search
        ORDER BY cityname
    """), engine, params={"search": f"%{search}%"})
    return jsonify(df.to_dict('records'))

@app.route("/api/stores-by-city")
def api_stores_by_city():
    city = request.args.get("city", "")
    df = pd.read_sql(text("""
        SELECT storeid, storename 
        FROM store s JOIN city c ON s.cityid = c.cityid 
        WHERE c.cityname ILIKE :city
    """), engine, params={"city": f"%{city}%"})
    return jsonify(df.to_dict('records'))

@app.route("/api/store-products")
def api_store_products():
    storeid = request.args.get("storeid")
    df = pd.read_sql(text("""
        SELECT DISTINCT productid, productname 
        FROM product p JOIN sales s ON p.productid = s.productid 
        WHERE s.storeid = :storeid
    """), engine, params={"storeid": int(storeid)})
    return jsonify(df.to_dict('records'))
@app.route("/help")
def help_page():
    conn = get_db_conn_raw()
    cursor = get_cursor(conn)
    cursor.execute("SELECT s.storename, s.store_manager, s.password, c.cityname FROM store s JOIN city c ON s.cityid = c.cityid")
    stores = [{'storename':r[0],'store_manager':r[1],'password':r[2],'cityname':r[3]} for r in cursor.fetchall()]
    cursor.execute("SELECT c.cityname, COUNT(s.storeid) FROM city c LEFT JOIN store s ON c.cityid = s.cityid GROUP BY c.cityname")
    cities = [{'cityname':r[0],'store_count':r[1]} for r in cursor.fetchall()]
    cursor.close(); conn.close()
    return render_template("help.html", stores=stores, cities=cities)

@app.route('/ai', methods=['POST'])
def ai_assistant():
    q = request.form.get('q', '').lower().strip('?!')
    
    try:
        conn = get_db_conn_raw()
        cursor = get_cursor(conn)
        
        # HELP
        if 'help' in q:
            response = """🤖 RetailBuddy Commands:

🏠 Navigation: dashboard | overstock | cities | stores | users | history | emails
🌆 Queries: stores in city_name | products in store_name | total cities | restock?"""
            return jsonify({'response': response})
        if 'understock count' in q or 'understock' in q:
            understock_count = len([a for a in all_alerts if "Restock Needed" in str(a.get('stock_alert', ''))])
            response = f"⚠️ {understock_count} Understock Alerts\n\n[View Understock](/understock)"
        
        elif 'overstock count' in q or 'overstock' in q:
            overstock_count = len([a for a in all_alerts if "Overstock" in str(a.get('stock_alert', ''))])
            response = f"📈 {overstock_count} Overstock Alerts\n\n[View Overstock](/overstock)"
        
        elif 'ok stock count' in q or 'ok stock' in q:
            okstock_count = len([a for a in all_alerts if "Stock OK" in str(a.get('stock_alert', ''))])
            response = f"✅ {okstock_count} OK Stock\n\n[Dashboard](/)"
        
        # TOTAL CITIES COUNT
        if 'total cities' in q or 'total no of cities' in q:
            cursor.execute("SELECT COUNT(*) FROM city")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT cityname FROM city ORDER BY cityname")
            cities = [r[0] for r in cursor.fetchall()]
            response = f"🌆 Total: {total} Cities\n\n" + "\n".join([f"• {city}" for city in cities[:20]])
        
        # STORES IN CITY
        elif 'stores in' in q:
            city_name = q.split('stores in', 1)[1].strip()
            cursor.execute("""
                SELECT s.storename 
                FROM store s JOIN city c ON s.cityid = c.cityid 
                WHERE LOWER(c.cityname) LIKE %s 
                ORDER BY s.storename LIMIT 20
            """, (f'%{city_name}%',))
            stores = [r[0] for r in cursor.fetchall()]
            count = len(stores)
            response = f"🏪 {city_name.title()}: {count} Stores\n\n" + "\n".join([f"• {store}" for store in stores])
       
        elif 'products in' in q:
            store_name = q.split('products in', 1)[1].strip().strip('"')
            store_products = []
            for alert in all_alerts[-100:]:  # Last 100 alerts
                if store_name.lower() in str(alert.get('store', '')).lower():
                    store_products.append(alert.get('product', 'Unknown'))
            store_products = list(set(store_products))[:10]  # Unique, top 10
            count = len(store_products)
            if count:
                response = f"📦 **{store_name}: {count} Products**\n\n" + "\n".join([f"• {prod}" for prod in store_products])
            else:
                cursor.execute("SELECT productname FROM product LIMIT 10")
                demo_products = [r[0] for r in cursor.fetchall()]
                response = f"😔 No recent data for '{store_name}'\n\n📦 Sample products:\n" + "\n".join([f"• {p}" for p in demo_products])
        
        # RESTOCK SUMMARY
        elif 'restock' in q:
            understock_count = len([a for a in all_alerts if "Restock Needed" in str(a.get('stock_alert', ''))])
            overstock_count = len([a for a in all_alerts if "Overstock" in str(a.get('stock_alert', ''))])
            okstock_count = len([a for a in all_alerts if "Stock OK" in str(a.get('stock_alert', ''))])
            response = f"""⚠️ **Stock Summary:**
            🔴 Understock: {understock_count}
            🟡 Overstock: {overstock_count}
            🟢 OK Stock: {okstock_count}
            📊 Total: {len(all_alerts)} alerts"""

        # NAVIGATION - AFTER ALL QUERIES
        elif 'dashboard' in q:
            response = '<a href="/" style="color:white;font-weight:bold;">🏠 Dashboard</a>'
        elif 'overstock' in q:
            response = '<a href="/overstock" style="color:white;font-weight:bold;">📈 Overstock</a>'
        elif 'understock' in q:
            response = '<a href="/understock" style="color:white;font-weight:bold;">⚠️ Understock</a>'
        elif 'cities' in q:
            response = '<a href="/cities" style="color:white;font-weight:bold;">🌆 Cities</a>'
        elif 'stores' in q:
            response = '<a href="/admin/stores" style="color:white;font-weight:bold;">🏪 Stores</a>'
        elif 'users' in q:
            response = '<a href="/admin/users" style="color:white;font-weight:bold;">👥 Users</a>'
        elif 'history' in q:
            response = '<a href="/admin/history" style="color:white;font-weight:bold;">👥 Users</a>'
        elif 'emails' in q:
            response = '<a href="/admin/emails" style="color:white;font-weight:bold;">👥 Users</a>'
        else:
            response = "Type help for commands! 😊"
    
    except Exception as e:
        response = f"Error: {str(e)[:50]}"
        print(f"AI ERROR: {e}")
    
    finally:
        try:
            if 'cursor' in locals(): cursor.close()
            if 'conn' in locals(): conn.close()
        except: pass
    
    return jsonify({'response': response})


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    debug = os.environ.get('DEBUG', 'True').lower() == 'true'
    print("🌟 SmartStock Dashboard ready!")
    print("🔓 ADMIN: admin/admin123")
    print("🔓 STORE MGR: mgr1/pass1")
    # Add to app.py (line 600, before app.run):
    print(f"🧵 Threads alive: {threading.active_count()}")
    print(f"Live thread: {live_thread is not None and live_thread.is_alive()}")
    app.run(host=host, port=port, debug=debug)
