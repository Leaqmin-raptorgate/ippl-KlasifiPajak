-- KlasifiPajak SQL syntax reference: database access.
--
-- Least privilege for the application account. The API may execute the
-- procedures and nothing else: no SELECT, INSERT, UPDATE, or DELETE against a
-- table or a view. Because every routine is SQL SECURITY DEFINER, it runs with
-- the definer's privileges and the caller needs only EXECUTE.
--
-- Replace the placeholder password from the secret store. No credential
-- belongs in this repository.

-- Account that owns the schema objects and performs migrations.
CREATE USER IF NOT EXISTS 'klasifipajak_ddl'@'%'
    IDENTIFIED BY 'CHANGE_ME_IN_SECRET_STORE';
GRANT SELECT, INSERT, UPDATE, DELETE
    ON klasifipajak.*
    TO 'klasifipajak_ddl'@'%';
GRANT CREATE, ALTER, DROP, INDEX, REFERENCES
    ON klasifipajak.*
    TO 'klasifipajak_ddl'@'%';
GRANT CREATE ROUTINE, ALTER ROUTINE, EXECUTE
    ON klasifipajak.*
    TO 'klasifipajak_ddl'@'%';

-- Account used by the API process.
CREATE USER IF NOT EXISTS 'klasifipajak_api'@'%'
    IDENTIFIED BY 'CHANGE_ME_IN_SECRET_STORE';

-- Start from no privileges at all, including any earlier grant.
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'klasifipajak_api'@'%';

GRANT EXECUTE ON PROCEDURE klasifipajak.sp_register_user
    TO 'klasifipajak_api'@'%';
GRANT EXECUTE ON PROCEDURE klasifipajak.sp_open_session
    TO 'klasifipajak_api'@'%';
GRANT EXECUTE ON PROCEDURE klasifipajak.sp_revoke_session
    TO 'klasifipajak_api'@'%';
GRANT EXECUTE ON PROCEDURE klasifipajak.sp_save_profile
    TO 'klasifipajak_api'@'%';
GRANT EXECUTE ON PROCEDURE klasifipajak.sp_record_transaction
    TO 'klasifipajak_api'@'%';
GRANT EXECUTE ON PROCEDURE klasifipajak.sp_upsert_month_snapshot
    TO 'klasifipajak_api'@'%';

FLUSH PRIVILEGES;

-- Verify: only the procedure grants and USAGE may appear.
SHOW GRANTS FOR 'klasifipajak_api'@'%';

-- The API user cannot read a table or a view directly.
-- SELECT * FROM klasifipajak.vw_transactions;  -- denied
--
-- The API user cannot create a temporary table directly. sp_open_session
-- creates one inside a DEFINER routine, so EXECUTE is enough.
