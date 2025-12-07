import pandas as pd
import mysql.connector

# -------------------------------
# 1️⃣ Load Excel file (full path)
# -------------------------------
df = pd.read_excel(r"C:\Users\bhakt\OneDrive\Desktop\samrt_real\retail_data_sampled.csv.xlsx")

# -------------------------------
# 2️⃣ Handle missing values (NaN)
# -------------------------------
df['city_id'] = df['city_id'].fillna(0).astype(int)
df['city_name'] = df['city_name'].fillna('')
df['store_id'] = df['store_id'].fillna(0).astype(int)
df['store_name'] = df['store_name'].fillna('')
df['product_id'] = df['product_id'].fillna(0).astype(int)
df['product_name'] = df['product_name'].fillna('')
df['dt'] = pd.to_datetime(df['dt'], errors='coerce')   # converts invalid/missing dates to NaT
df['activity_flag'] = df['activity_flag'].fillna(0).astype(int)
df['holiday_flag'] = df['holiday_flag'].fillna(0).astype(int)
df['stock_hour6_22_cnt'] = df['stock_hour6_22_cnt'].fillna(0).astype(int)
df['discount'] = df['discount'].fillna(0).astype(int)
df['sale_amount'] = df['sale_amount'].fillna(0).astype(int)

# -------------------------------
# 3️⃣ Connect to MySQL
# -------------------------------
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Bhakthi@13",
    database="smartstock_dynamic"
)
cursor = conn.cursor()

# -------------------------------
# 4️⃣ Insert unique cities
# -------------------------------
cities = df[['city_id','city_name']].drop_duplicates()
for _, row in cities.iterrows():
    cursor.execute(
        "INSERT INTO city (cityid, cityname) VALUES (%s,%s) ON DUPLICATE KEY UPDATE cityname=cityname",
        (row['city_id'], row['city_name'])
    )

# -------------------------------
# 5️⃣ Insert unique stores
# -------------------------------
stores = df[['store_id','store_name','city_id']].drop_duplicates()
for _, row in stores.iterrows():
    cursor.execute(
        "INSERT INTO store (storeid, storename, cityid) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE storename=storename",
        (row['store_id'], row['store_name'], row['city_id'])
    )

# -------------------------------
# 6️⃣ Insert unique products
# -------------------------------
products = df[['product_id','product_name']].drop_duplicates()
for _, row in products.iterrows():
    cursor.execute(
        "INSERT INTO product (productid, productname) VALUES (%s,%s) ON DUPLICATE KEY UPDATE productname=productname",
        (row['product_id'], row['product_name'])
    )

# -------------------------------
# 7️⃣ Insert sales records
# -------------------------------
for _, row in df.iterrows():
    cursor.execute("""
        INSERT INTO sales 
        (dt, cityid, storeid, productid, sale_amount, stock, hour, discount, holiday_flag, activity_flag)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        row['dt'],
        row['city_id'],
        row['store_id'],
        row['product_id'],
        row['sale_amount'],
        row['stock_hour6_22_cnt'],  # correct stock column
        0,                          # hour placeholder
        row['discount'],
        row['holiday_flag'],
        row['activity_flag']
    ))

# -------------------------------
# 8️⃣ Commit and close connection
# -------------------------------
conn.commit()
cursor.close()
conn.close()

print("Database populated successfully!")
