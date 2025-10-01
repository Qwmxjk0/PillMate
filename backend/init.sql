-- Initialize database with proper charset and collation
CREATE DATABASE IF NOT EXISTS DrugBank 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

-- Use the database
USE DrugBank;

-- Create user if not exists (this is handled by MariaDB container environment)
-- The user creation is handled by the MARIADB_USER and MARIADB_PASSWORD environment variables
