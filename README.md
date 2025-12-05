# Smart-Stock-Inventory-Optimization-for-Retail-Stores
AI-Driven Forecasting • Inventory Monitoring • Alerts Dashboard

This project is a Flask-based retail stock-optimization dashboard designed to help retailers forecast demand, identify understock/overstock situations, and generate automated reorder suggestions using machine-learning outputs.

The application reads pre-processed retail data and ML forecasts, then provides:

📉 Understock & Overstock Alerts

📊 Top Products / Stores at Risk

🧠 7-day Forecast Imports (from xgb_forecast.py / daily_forecast.py)

🏬 Role-based Login (Admin & Store Manager)

📈 Interactive dashboard & tables

📂 Downloadable forecast reports

🚀 Features
🔐 Role-Based Login

Admin: full system access

Managers: must select city + branch → see only their store’s data

📈 Dashboard Features

Summary of understock & overstock counts

Top 10 understocked products

Top 10 affected stores

Reorder quantity suggestions (based on forecast − current stock)

Quick preview of ML forecast results
