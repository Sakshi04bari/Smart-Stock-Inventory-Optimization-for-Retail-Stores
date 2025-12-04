import os
import pandas as pd
import subprocess
from datetime import datetime

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

print(f"[{datetime.now()}] Starting daily forecast pipeline...")

# 1️⃣ Run loadclean.py to refresh cleaned data with names
print("Step 1: Cleaning data...")
subprocess.run(["python", os.path.join(BASE_DIR, "loadclean.py")], check=True)

# 2️⃣ Optional: retrain model if you want daily retraining
# Uncomment below if you want to retrain every day
# print("Step 2: Training XGBoost model...")
# subprocess.run(["python", os.path.join(BASE_DIR, "xgb_train.py")], check=True)

# 3️⃣ Run forecast
print("Step 3: Running 7-day stock forecast...")
subprocess.run(["python", os.path.join(BASE_DIR, "xgb_forecast.py")], check=True)

print(f"[{datetime.now()}] Daily forecast pipeline completed!")
