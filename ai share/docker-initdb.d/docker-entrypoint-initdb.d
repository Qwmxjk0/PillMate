-- 01-create-users.sql
-- สร้างผู้ใช้สำหรับ web UI (dbadmin) และ grant เฉพาะฐาน DrugBank
CREATE USER IF NOT EXISTS 'dbadmin'@'%' IDENTIFIED BY 'verysecretroot';
GRANT SELECT, SHOW VIEW ON `DrugBank`.* TO 'dbadmin'@'%';

-- สร้าง/ปรับ druguser ให้เชื่อมจากภายนอกได้ (optional)
CREATE USER IF NOT EXISTS 'druguser'@'%' IDENTIFIED BY 'drugpass';
GRANT ALL PRIVILEGES ON `DrugBank`.* TO 'druguser'@'%';

-- (ถ้าต้องการให้ root สามารถเชื่อมจากทุก host — ระวังความปลอดภัย)
CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY 'verysecretroot';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;


-- ./docker-initdb.d/02-create-druguser.sql
CREATE USER IF NOT EXISTS 'druguser'@'%' IDENTIFIED BY 'drugpass';
GRANT ALL PRIVILEGES ON `DrugBank`.* TO 'druguser'@'%';

FLUSH PRIVILEGES;
