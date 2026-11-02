-- KlasifiPajak MySQL bootstrap (HB-18 / TC-HARD-23).
-- Runtime app user: DML only. Migration user: DDL (+ DML).
-- Image MYSQL_USER (klasifipajak): DML on app schema; ALL on *_test for pytest.

CREATE DATABASE IF NOT EXISTS klasifipajak_test
  CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

CREATE DATABASE IF NOT EXISTS klasifipajak_migrate_test
  CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

-- Runtime application user (SELECT/INSERT/UPDATE/DELETE only).
CREATE USER IF NOT EXISTS 'klasifipajak_app'@'%' IDENTIFIED BY 'klasifipajak_app';
GRANT SELECT, INSERT, UPDATE, DELETE ON klasifipajak.* TO 'klasifipajak_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON klasifipajak_test.* TO 'klasifipajak_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON klasifipajak_migrate_test.* TO 'klasifipajak_app'@'%';

-- Migration / DDL user (Alembic).
CREATE USER IF NOT EXISTS 'klasifipajak_migrate'@'%' IDENTIFIED BY 'klasifipajak_migrate';
GRANT ALL PRIVILEGES ON klasifipajak.* TO 'klasifipajak_migrate'@'%';
GRANT ALL PRIVILEGES ON klasifipajak_test.* TO 'klasifipajak_migrate'@'%';
GRANT ALL PRIVILEGES ON klasifipajak_migrate_test.* TO 'klasifipajak_migrate'@'%';

-- Demote image MYSQL_USER on the app schema; keep DDL on the test schemas.
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'klasifipajak'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON klasifipajak.* TO 'klasifipajak'@'%';
GRANT ALL PRIVILEGES ON klasifipajak_test.* TO 'klasifipajak'@'%';
GRANT ALL PRIVILEGES ON klasifipajak_migrate_test.* TO 'klasifipajak'@'%';

FLUSH PRIVILEGES;
