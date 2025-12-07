import pandas as pd
import mysql.connector

# Read Excel
df = pd.read_excel('stores.xlsx', sheet_name='in')
df = df[['store_id', 'store_name', 'city_id', 'store_manager', 'password']]

# Connect to MySQL (UPDATE YOUR CREDENTIALS)
cnx = mysql.connector.connect(
    user='root', 
    password='Bhakthi@13', 
    host='localhost', 
    database='smartstock_dynamic'
)
cursor = cnx.cursor()

# UPSERT all columns
upsert_query = """
INSERT INTO store (storeid, storename, cityid, store_manager, password) 
VALUES (%s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE 
    storename=VALUES(storename), 
    cityid=VALUES(cityid),
    store_manager=VALUES(store_manager),
    password=VALUES(password)
"""

for row in df.itertuples(index=False):
    cursor.execute(upsert_query, row)

cnx.commit()
cursor.close()
cnx.close()
print(f"Updated {len(df)} stores successfully.")
