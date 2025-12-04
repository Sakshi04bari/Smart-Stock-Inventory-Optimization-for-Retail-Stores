# xgb_train.py
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_squared_error
import xgboost as xgb
import joblib

# 1️⃣ Load enriched data
df = pd.read_csv("data/cleaned_retail_data_with_names.csv")
df["dt"] = pd.to_datetime(df["dt"])
df = df.sort_values(["store_id","product_id","dt"])

# 2️⃣ Create lag features
df["sales_lag_1"] = df.groupby(["store_id","product_id"])["sale_amount"].shift(1)
df["sales_ma_7"] = df.groupby(["store_id","product_id"])["sale_amount"].transform(lambda x: x.rolling(7).mean())
df["sales_ma_14"] = df.groupby(["store_id","product_id"])["sale_amount"].transform(lambda x: x.rolling(14).mean())

df = df.dropna(subset=["sales_lag_1","sales_ma_7","sales_ma_14"])

# 3️⃣ Target: next 7-day total sales
df["sales_next_7"] = df.groupby(["store_id","product_id"])["sale_amount"].shift(-7).rolling(7).sum()
df = df.dropna(subset=["sales_next_7"])

# 4️⃣ Encode categorical features
categorical_cols = ["city_name","company_name","branch_name","product_name"]
label_encoders = {}
for col in categorical_cols:
    le = LabelEncoder()
    df[col+"_enc"] = le.fit_transform(df[col])
    label_encoders[col] = le

# 5️⃣ Features and target
features = [
    "city_name_enc","store_id","company_name_enc","branch_name_enc","product_name_enc",
    "stock_hour6_22_cnt","discount","holiday_flag","activity_flag",
    "year","month","day","day_of_week","is_weekend",
    "sales_lag_1","sales_ma_7","sales_ma_14"
]

# Add date features
df["year"] = df["dt"].dt.year
df["month"] = df["dt"].dt.month
df["day"] = df["dt"].dt.day
df["day_of_week"] = df["dt"].dt.dayofweek
df["is_weekend"] = df["day_of_week"].isin([5,6]).astype(int)

X = df[features]
y = df["sales_next_7"]

# 6️⃣ Time-based train/test split
split_date = df["dt"].max() - pd.Timedelta(days=7)
X_train = X[df["dt"] <= split_date]
y_train = y[df["dt"] <= split_date]
X_test = X[df["dt"] > split_date]
y_test = y[df["dt"] > split_date]

# 7️⃣ Train XGBoost
xgb_model = xgb.XGBRegressor(
    n_estimators=500,
    learning_rate=0.1,
    max_depth=6,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    n_jobs=-1
)
xgb_model.fit(X_train, y_train)

# 8️⃣ Evaluate
y_pred = xgb_model.predict(X_test)
rmse = np.sqrt(mean_squared_error(y_test, y_pred))
print(f"Stock Forecasting RMSE (next 7 days): {rmse:.2f}")

# 9️⃣ Save model and encoders
joblib.dump(xgb_model, "model/xgb_stock_forecast_model.pkl")
joblib.dump(label_encoders, "label_encoders.pkl")
print("Model and encoders saved!")
