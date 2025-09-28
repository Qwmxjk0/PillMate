-- Initialize database with proper charset and collation
CREATE DATABASE IF NOT EXISTS pillmate_db 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

-- Use the database
USE pillmate_db;

-- Create user if not exists (this is handled by MySQL container environment)
-- The user creation is handled by the MYSQL_USER and MYSQL_PASSWORD environment variables
