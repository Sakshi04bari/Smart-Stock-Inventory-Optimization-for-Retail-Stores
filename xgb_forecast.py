import pandas as pd
import numpy as np
import joblib

# Load model and encoders
model = joblib.load("model/xgb_stock_forecast_model.pkl")
label_encoders = joblib.load("label_encoders.pkl")

# Load cleaned retail data
df = pd.read_csv("data/cleaned_retail_data_with_names.csv")
df["dt"] = pd.to_datetime(df["dt"])

# Latest row per store/product
latest_df = df.sort_values("dt").groupby(["store_id","product_id"]).tail(1).copy()

# Lag features
latest_df["sales_lag_1"] = df.groupby(["store_id","product_id"])["sale_amount"].shift(1).reindex(latest_df.index).fillna(0)
latest_df["sales_ma_7"] = df.groupby(["store_id","product_id"])["sale_amount"].transform(lambda x: x.rolling(7).mean()).reindex(latest_df.index).fillna(0)
latest_df["sales_ma_14"] = df.groupby(["store_id","product_id"])["sale_amount"].transform(lambda x: x.rolling(14).mean()).reindex(latest_df.index).fillna(0)

# Date features
latest_df["year"] = latest_df["dt"].dt.year
latest_df["month"] = latest_df["dt"].dt.month
latest_df["day"] = latest_df["dt"].dt.day
latest_df["day_of_week"] = latest_df["dt"].dt.dayofweek
latest_df["is_weekend"] = latest_df["day_of_week"].isin([5,6]).astype(int)

# Encode categorical features for model input
for col in ["city_name","company_name","branch_name","product_name"]:
    le = label_encoders[col]
    # unseen labels mapped to -1
    latest_df[col+"_enc"] = latest_df[col].apply(lambda x: le.transform([x])[0] if x in le.classes_ else -1)

# Model features
features = [
    "city_name_enc","store_id","company_name_enc","branch_name_enc","product_name_enc",
    "stock_hour6_22_cnt","discount","holiday_flag","activity_flag",
    "year","month","day","day_of_week","is_weekend",
    "sales_lag_1","sales_ma_7","sales_ma_14"
]

# Forecast next 7 days
forecast_days = 7
results = []

for idx, row in latest_df.iterrows():
    row_copy = row.copy()
    forecasts, alerts = [], []

    for d in range(forecast_days):
        X_pred = row_copy[features].values.reshape(1, -1)
        y_pred = model.predict(X_pred)[0]
        forecasts.append(round(y_pred,2))

        stock = row_copy["stock_hour6_22_cnt"]
        if y_pred > stock:
            alerts.append("UNDERSTOCK")
        elif y_pred < stock*0.5:
            alerts.append("OVERSTOCK")
        else:
            alerts.append("OK")

        # Update lag features
        row_copy["sales_lag_1"] = y_pred
        row_copy["sales_ma_7"] = (row_copy["sales_ma_7"]*6 + y_pred)/7
        row_copy["sales_ma_14"] = (row_copy["sales_ma_14"]*13 + y_pred)/14

    # Save results with original names
    res = {
        "store_id": row["store_id"],
        "product_id": row["product_id"],
        "city_name": row["city_name"],
        "company_name": row["company_name"],
        "branch_name": row["branch_name"],
        "product_name": row["product_name"],
        "stock_hour6_22_cnt": row["stock_hour6_22_cnt"]
    }

    for i in range(forecast_days):
        res[f"day_{i+1}_forecast"] = forecasts[i]
        res[f"day_{i+1}_alert"] = alerts[i]

    results.append(res)

# Save CSV
forecast_df = pd.DataFrame(results)
forecast_df.to_csv("data/stock_forecast_next_7_days_with_alerts.csv", index=False)
print("✅ Forecast saved with original names")
