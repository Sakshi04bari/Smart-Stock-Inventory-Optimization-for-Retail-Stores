-- create_users.sql
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'store_manager') NOT NULL,
    cityid INT NULL,
    storeid INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sample Admin (password: admin123)
INSERT INTO users (username, password_hash, role) VALUES 
('admin', 'admin123', 'admin')
ON DUPLICATE KEY UPDATE password_hash=password_hash;
