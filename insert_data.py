from datasets import load_dataset
import mysql.connector
import pandas as pd
import numpy as np

print("Loading FreshRetailNet-50K dataset...")

# Load dataset
dataset = load_dataset("Dingdong-Inc/FreshRetailNet-50K")
df = dataset["train"].to_pandas()

# 🟢 Stratified sampling to include multiple cities
# Take up to 5000 rows per city (adjust if needed)
df_sampled = df.groupby("city_id", group_keys=False).apply(
    lambda x: x.sample(n=min(len(x), 5000), random_state=42)
)

# If total rows >50,000, randomly sample 50k
if len(df_sampled) > 50000:
    df_sampled = df_sampled.sample(50000, random_state=42)

print(f"Sampled {len(df_sampled)} rows across multiple cities.")

# Keep only columns that exist in your MySQL table
cols = [
    "city_id", "store_id", "product_id", "dt", "sale_amount",
    "stock_hour6_22_cnt", "discount", "holiday_flag", "activity_flag"
]

df_sampled = df_sampled[cols].replace({np.nan: None})
df_sampled["dt"] = df_sampled["dt"].astype(str)

# Convert numpy types to native Python
def convert_value(x):
    if isinstance(x, (np.integer, np.floating)):
        return x.item()
    return x

data = []
for row in df_sampled.itertuples(index=False, name=None):
    data.append(tuple(convert_value(v) for v in row))

# Connect to MySQL
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Bhakthi@13",
    database="smartstock"
)
cursor = conn.cursor()

column_names = ", ".join(cols)
placeholders = ", ".join(["%s"] * len(cols))
query = f"INSERT INTO retail_data ({column_names}) VALUES ({placeholders})"

print("Inserting into MySQL...")
batch_size = 5000
for i in range(0, len(data), batch_size):
    batch = data[i:i+batch_size]
    cursor.executemany(query, batch)
    conn.commit()
    print(f"Inserted rows {i+1} to {i+len(batch)}")

cursor.close()
conn.close()
print("Done inserting sampled data.")
