import mysql.connector
import random
import time
from datetime import datetime, timedelta
import pandas as pd
import xgboost as xgb

# -------------------------------
# 1️⃣ MySQL connection
# -------------------------------
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Bhakthi@13",
    database="smartstock_dynamic"
)
cursor = conn.cursor()

# -------------------------------
# 2️⃣ Fetch initial product/store/city info
# -------------------------------
cursor.execute("SELECT productid, productname FROM product")
products = cursor.fetchall()

cursor.execute("SELECT storeid, storename, cityid FROM store")
stores = cursor.fetchall()

cursor.execute("SELECT cityid, cityname FROM city")
cities = dict(cursor.fetchall())

if not products or not stores:
    print("Error: No products or stores found in database.")
    cursor.close()
    conn.close()
    exit()

# -------------------------------
# 3️⃣ Settings
# -------------------------------
UNDERSTOCK_THRESHOLD = 10
OVERSTOCK_THRESHOLD = 50
SALE_INTERVAL = 30          # seconds for sales updates
FORECAST_INTERVAL = 60      # seconds for XGBoost predictions

last_forecast_time = datetime.now() - timedelta(seconds=FORECAST_INTERVAL)

print("Starting live dynamic updater with forecast fallback... (Ctrl+C to stop)")

# -------------------------------
# 4️⃣ Main loop
# -------------------------------
try:
    while True:
        now = datetime.now()

        # -------------------------------
        # 4a️⃣ Pick random store & product
        # -------------------------------
        store_id, store_name, city_id = random.choice(stores)
        product_id, product_name = random.choice(products)
        city_name = cities.get(city_id, "Unknown City")

        # Simulate sale amount
        sale_amount = random.randint(1, 10)

        # Get latest stock
        cursor.execute("""
            SELECT stock FROM sales
            WHERE storeid=%s AND productid=%s
            ORDER BY dt DESC LIMIT 1
        """, (store_id, product_id))
        result = cursor.fetchone()
        current_stock = result[0] if result else random.randint(20, 50)
        new_stock = max(current_stock - sale_amount, 0)

        discount = random.choice([0, 5, 10, 15])
        holiday_flag = random.choice([0, 1])
        activity_flag = random.choice([0, 1])
        hour = now.hour

        # -------------------------------
        # 4b️⃣ Insert new sales record
        # -------------------------------
        cursor.execute("""
            INSERT INTO sales
            (dt, cityid, storeid, productid, sale_amount, stock, hour, discount, holiday_flag, activity_flag)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (now, city_id, store_id, product_id, sale_amount, new_stock, hour, discount, holiday_flag, activity_flag))
        conn.commit()

        # -------------------------------
        # 4c️⃣ Live stock alert
        # -------------------------------
        if new_stock < UNDERSTOCK_THRESHOLD:
            stock_alert = "Restock Needed"
        elif new_stock > OVERSTOCK_THRESHOLD:
            stock_alert = "Overstock"
        else:
            stock_alert = "Stock OK"

        # -------------------------------
        # 4d️⃣ Forecast (XGBoost or fallback)
        # -------------------------------
        if (now - last_forecast_time).total_seconds() >= FORECAST_INTERVAL:
            last_forecast_time = now
            try:
                past_30_days = now - timedelta(days=30)
                query = """
                    SELECT storeid, productid, dt, sale_amount, stock, discount, holiday_flag, activity_flag
                    FROM sales
                    WHERE dt >= %s
                    ORDER BY dt ASC
                """
                df = pd.read_sql(query, conn, params=(past_30_days,))
                df['dt'] = pd.to_datetime(df['dt'])
                df['day_of_week'] = df['dt'].dt.dayofweek

                forecast_alerts = []

                for (s_id, p_id), group in df.groupby(['storeid','productid']):
                    # If too little data, use rolling average fallback
                    if len(group) < 7:
                        predicted_sales_7d = group['sale_amount'].mean() * 7
                    else:
                        X = group[['day_of_week','stock','discount','holiday_flag','activity_flag']]
                        y = group['sale_amount']
                        model = xgb.XGBRegressor(objective='reg:squarederror', n_estimators=50)
                        model.fit(X, y)

                        last_row = group.iloc[-1]
                        stock_feat = last_row['stock']
                        predictions = []
                        for i in range(1,8):
                            day_of_week = (last_row['day_of_week'] + i) % 7
                            X_pred = pd.DataFrame([{
                                'day_of_week': day_of_week,
                                'stock': stock_feat,
                                'discount': last_row['discount'],
                                'holiday_flag': last_row['holiday_flag'],
                                'activity_flag': last_row['activity_flag']
                            }])
                            pred_sale = model.predict(X_pred)[0]
                            predictions.append(pred_sale)
                        predicted_sales_7d = sum(predictions)

                    forecast_alerts.append({
                        'storeid': s_id,
                        'productid': p_id,
                        'predicted_7d_sales': predicted_sales_7d
                    })

                # Merge forecast with current stock for alerts
                for alert in forecast_alerts:
                    if alert['storeid']==store_id and alert['productid']==product_id:
                        if new_stock < alert['predicted_7d_sales']:
                            forecast_alert = "Restock Likely (7-day)"
                        else:
                            forecast_alert = "Stock OK (7-day)"
                        break
                else:
                    forecast_alert = "Insufficient data for forecast"

            except Exception as e:
                forecast_alert = f"Forecast error: {e}"

        # -------------------------------
        # 4e️⃣ Print live log
        # -------------------------------
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] City: {city_name}, Store: {store_name}, Product: {product_name}, "
              f"Sale: {sale_amount}, Stock: {new_stock}, Stock Alert: {stock_alert}, 7-Day Forecast Alert: {forecast_alert}")

        # Wait before next sale
        time.sleep(SALE_INTERVAL)

except KeyboardInterrupt:
    print("\nUpdater stopped by user.")

finally:
    cursor.close()
    conn.close()
    print("Database connection closed.")
