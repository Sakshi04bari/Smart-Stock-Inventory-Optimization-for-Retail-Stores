# create_admin.py
import bcrypt
import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Bhakthi@13",
    database="smartstock_dynamic"
)
cursor = conn.cursor()

username = "admin"
password = "Admin@123"   # change this to a strong password

pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
               (username, pw_hash, "admin"))
conn.commit()
cursor.close()
conn.close()

print("Admin user created:", username)
