-- KlasifiPajak SQL syntax reference: stored functions.
--
-- A function returns exactly one value. It reads through vw_* views, never a
-- base table, and never writes. A view or trigger must not call a function.
-- Tax formulas stay in the Python engine; these functions answer lookups and
-- derived sums that a procedure needs.

DELIMITER $$

DROP FUNCTION IF EXISTS fn_active_session_count$$
CREATE FUNCTION fn_active_session_count(
    p_user_id VARCHAR(64),
    p_now_utc DATETIME(6)
)
RETURNS INT
READS SQL DATA
SQL SECURITY DEFINER
BEGIN
    -- FR-40 to FR-42: live sessions for the five-session cap.
    DECLARE v_count INT;

    SELECT COUNT(*) INTO v_count
      FROM vw_sessions
     WHERE user_id = p_user_id
       AND revoked_at IS NULL
       AND expires_at_utc > p_now_utc;

    RETURN v_count;
END$$

DROP FUNCTION IF EXISTS fn_duplicate_invoice_id$$
CREATE FUNCTION fn_duplicate_invoice_id(
    p_user_id VARCHAR(64),
    p_client_name_norm VARCHAR(255),
    p_invoice_no_norm VARCHAR(64),
    p_amount_idr BIGINT,
    p_tx_date DATE
)
RETURNS VARCHAR(64)
READS SQL DATA
SQL SECURITY DEFINER
BEGIN
    -- FR-2.2: return the id of an existing row with the same duplicate key.
    DECLARE v_id VARCHAR(64);

    IF p_invoice_no_norm IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT MAX(id) INTO v_id
      FROM vw_transactions
     WHERE user_id = p_user_id
       AND client_name_norm = p_client_name_norm
       AND invoice_no_norm = p_invoice_no_norm
       AND amount_idr = p_amount_idr
       AND tx_date = p_tx_date;

    RETURN v_id;
END$$

DROP FUNCTION IF EXISTS fn_profile_version$$
CREATE FUNCTION fn_profile_version(
    p_user_id VARCHAR(64),
    p_tax_year INT
)
RETURNS INT
READS SQL DATA
SQL SECURITY DEFINER
BEGIN
    -- FR-1.2: current version for optimistic concurrency, NULL when absent.
    DECLARE v_version INT;

    SELECT MAX(version) INTO v_version
      FROM vw_profiles
     WHERE user_id = p_user_id
       AND tax_year = p_tax_year;

    RETURN v_version;
END$$

DROP FUNCTION IF EXISTS fn_ytd_usaha_omzet$$
CREATE FUNCTION fn_ytd_usaha_omzet(
    p_user_id VARCHAR(64),
    p_tax_year INT,
    p_through_date DATE
)
RETURNS BIGINT
READS SQL DATA
SQL SECURITY DEFINER
BEGIN
    -- FR-5.1, FR-18: usaha turnover through a date. Not a tax figure.
    DECLARE v_total BIGINT;

    SELECT COALESCE(SUM(amount_idr), 0) INTO v_total
      FROM vw_transactions
     WHERE user_id = p_user_id
       AND category = 'usaha'
       AND tx_date >= MAKEDATE(p_tax_year, 1)
       AND tx_date <= p_through_date;

    RETURN v_total;
END$$

DELIMITER ;
