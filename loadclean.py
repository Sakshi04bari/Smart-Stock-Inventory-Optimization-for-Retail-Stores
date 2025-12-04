import pandas as pd
import numpy as np

print("Loading cleaned retail data...")

# Load main cleaned data
df = pd.read_csv("data/cleaned_retail_data.csv")

# Load mapping CSVs
cities = pd.read_csv("data/cities.csv")       # city_id, city_name
stores = pd.read_csv("data/stores.csv")       # store_id, company_name, branch_name
products = pd.read_csv("data/products.csv")   # product_id, product_name

# Ensure IDs are integers
df["city_id"] = df["city_id"].astype(int)
df["store_id"] = df["store_id"].astype(int)
df["product_id"] = df["product_id"].astype(int)
cities["city_id"] = cities["city_id"].astype(int)
stores["store_id"] = stores["store_id"].astype(int)
products["product_id"] = products["product_id"].astype(int)

# Merge city names
df = df.merge(cities, on="city_id", how="left")

# Merge store names, fill missing automatically
df = df.merge(stores, on="store_id", how="left")
df['company_name'] = df['company_name'].fillna('Company_' + df['store_id'].astype(str))
df['branch_name'] = df['branch_name'].fillna('Branch_' + df['store_id'].astype(str))

# Merge product names, fill missing automatically
df = df.merge(products, on="product_id", how="left")
df['product_name'] = df['product_name'].fillna('Product_' + df['product_id'].astype(str))

# Check for missing names
missing_city = df["city_name"].isna().sum()
missing_store = df["company_name"].isna().sum()
missing_product = df["product_name"].isna().sum()
print(f"Missing city names: {missing_city}")
print(f"Missing store names: {missing_store}")
print(f"Missing product names: {missing_product}")

# Convert date column
df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
df = df.dropna(subset=["dt"])

# Extract date features
df["year"] = df["dt"].dt.year
df["month"] = df["dt"].dt.month
df["day"] = df["dt"].dt.day
df["day_of_week"] = df["dt"].dt.dayofweek
df["is_weekend"] = df["day_of_week"].isin([5,6]).astype(int)

# Sort and compute lag and 7-day moving average
df = df.sort_values(["store_id", "product_id", "dt"])
df["sales_lag_1"] = df.groupby(["store_id","product_id"])["sale_amount"].shift(1)
df["sales_ma_7"] = df.groupby(["store_id","product_id"])["sale_amount"].transform(lambda x: x.rolling(7).mean())

# Drop rows where new features are NaN
df = df.dropna(subset=["sales_lag_1","sales_ma_7"])

# Reorder columns
cols_order = [
    "city_id","city_name",
    "store_id","company_name","branch_name",
    "product_id","product_name",
    "dt","sale_amount","stock_hour6_22_cnt",
    "discount","holiday_flag","activity_flag",
    "year","month","day","day_of_week","is_weekend",
    "sales_lag_1","sales_ma_7"
]
cols_order = [c for c in cols_order if c in df.columns]
df = df[cols_order]

# Save final CSV
df.to_csv("data/cleaned_retail_data_with_names.csv", index=False)

print("Preprocessing complete!")
print("Saved: cleaned_retail_data_with_names.csv")
