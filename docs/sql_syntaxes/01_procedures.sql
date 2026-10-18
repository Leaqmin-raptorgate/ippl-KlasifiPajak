-- KlasifiPajak SQL syntax reference: stored procedures.
--
-- Tier rules served here: API -> procedure -> view/function -> base table.
-- Every procedure starts with an EXIT HANDLER that rolls back and re-signals,
-- then owns its transaction with START TRANSACTION and COMMIT.
-- Reads go through vw_* views and fn_* functions. Writes go through the
-- updatable vw_* view for that table. No procedure names a base table.
-- The first parameter is always user_id (invariant 8).
--
-- Base tables must carry server defaults for the columns omitted below
-- (paid_flag, version, money). The ORM supplies them in the current slice.
--
-- Production objects belong one per file under backend/alembic/versions
-- (AGENTS.md). This file is the readable reference.

DELIMITER $$

DROP PROCEDURE IF EXISTS sp_register_user$$
CREATE PROCEDURE sp_register_user(
    IN p_user_id VARCHAR(64),
    IN p_email VARCHAR(320),
    IN p_email_norm VARCHAR(320),
    IN p_username VARCHAR(64),
    IN p_username_norm VARCHAR(64),
    IN p_password_hash VARCHAR(255),
    OUT p_created_at DATETIME(6)
)
SQL SECURITY DEFINER
BEGIN
    -- FR-37 to FR-42: create one account, no session.
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    INSERT INTO vw_users (
        id, email, email_norm, username, username_norm,
        password_hash, paid_flag
    )
    VALUES (
        p_user_id, p_email, p_email_norm, p_username, p_username_norm,
        p_password_hash, FALSE
    );

    SELECT created_at INTO p_created_at
      FROM vw_users
     WHERE id = p_user_id;

    COMMIT;
END$$

DROP PROCEDURE IF EXISTS sp_open_session$$
CREATE PROCEDURE sp_open_session(
    IN p_user_id VARCHAR(64),
    IN p_session_id VARCHAR(64),
    IN p_device_label VARCHAR(128),
    IN p_expires_at_utc DATETIME(6)
)
SQL SECURITY DEFINER
BEGIN
    -- FR-40 to FR-42: insert one session, then keep only the newest five.
    DECLARE v_now DATETIME(6);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SET v_now = UTC_TIMESTAMP(6);

    START TRANSACTION;

    INSERT INTO vw_sessions (
        id, user_id, device_label,
        expires_at_utc, revoked_at
    )
    VALUES (
        p_session_id, p_user_id, p_device_label,
        p_expires_at_utc, NULL
    );

    -- Keep the five newest live sessions. A temporary table avoids MySQL
    -- error 1093 when the same view is read and written in one statement.
    DROP TEMPORARY TABLE IF EXISTS tmp_keep_sessions;
    CREATE TEMPORARY TABLE tmp_keep_sessions (
        id VARCHAR(64) NOT NULL PRIMARY KEY
    );

    INSERT INTO tmp_keep_sessions (id)
    SELECT id
      FROM vw_sessions
     WHERE user_id = p_user_id
       AND revoked_at IS NULL
       AND expires_at_utc > v_now
     ORDER BY last_seen_at DESC
     LIMIT 5;

    UPDATE vw_sessions
       SET revoked_at = v_now
     WHERE user_id = p_user_id
       AND revoked_at IS NULL
       AND expires_at_utc > v_now
       AND id NOT IN (SELECT id FROM tmp_keep_sessions);

    DROP TEMPORARY TABLE tmp_keep_sessions;

    COMMIT;
END$$

DROP PROCEDURE IF EXISTS sp_revoke_session$$
CREATE PROCEDURE sp_revoke_session(
    IN p_user_id VARCHAR(64),
    IN p_session_id VARCHAR(64),
    OUT p_revoked BOOLEAN
)
SQL SECURITY DEFINER
BEGIN
    -- FR-40 to FR-42: revoke one session owned by the caller.
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    UPDATE vw_sessions
       SET revoked_at = UTC_TIMESTAMP(6)
     WHERE id = p_session_id
       AND user_id = p_user_id
       AND revoked_at IS NULL;

    SET p_revoked = ROW_COUNT() > 0;

    COMMIT;
END$$

DROP PROCEDURE IF EXISTS sp_save_profile$$
CREATE PROCEDURE sp_save_profile(
    IN p_user_id VARCHAR(64),
    IN p_profile_id VARCHAR(64),
    IN p_tax_year INT,
    IN p_version INT,
    IN p_name VARCHAR(255),
    IN p_entity_type VARCHAR(32),
    IN p_nib_status VARCHAR(16),
    IN p_nib_last_4 VARCHAR(4),
    IN p_kbli_code VARCHAR(16),
    IN p_business_description VARCHAR(255),
    IN p_marital_status VARCHAR(8),
    IN p_spouse_aggregation_active BOOLEAN,
    IN p_is_new_taxpayer_current_year BOOLEAN,
    IN p_spouse_current_usaha_idr BIGINT,
    IN p_spouse_current_pekerjaan_bebas_idr BIGINT,
    IN p_spouse_current_already_final_idr BIGINT,
    IN p_prior_user_usaha_idr BIGINT,
    IN p_prior_user_pekerjaan_bebas_idr BIGINT,
    IN p_prior_user_already_final_idr BIGINT,
    IN p_prior_spouse_usaha_idr BIGINT,
    IN p_prior_spouse_pekerjaan_bebas_idr BIGINT,
    IN p_prior_spouse_already_final_idr BIGINT,
    OUT p_new_version INT
)
SQL SECURITY DEFINER
BEGIN
    -- FR-1.1, FR-1.2: create or version a profile and audit the fields that
    -- can move a tax figure, plus a name change.
    -- On create, pass p_version = 1 and expect 1 back. On update, pass the
    -- version last read and expect that version plus one.
    DECLARE v_exists INT;
    DECLARE v_id VARCHAR(64);
    DECLARE v_current INT;
    DECLARE v_name VARCHAR(255);
    DECLARE v_spouse_aggregation_active BOOLEAN;
    DECLARE v_is_new_taxpayer_current_year BOOLEAN;
    DECLARE v_spouse_current_usaha_idr BIGINT;
    DECLARE v_spouse_current_pekerjaan_bebas_idr BIGINT;
    DECLARE v_spouse_current_already_final_idr BIGINT;
    DECLARE v_prior_user_usaha_idr BIGINT;
    DECLARE v_prior_user_pekerjaan_bebas_idr BIGINT;
    DECLARE v_prior_user_already_final_idr BIGINT;
    DECLARE v_prior_spouse_usaha_idr BIGINT;
    DECLARE v_prior_spouse_pekerjaan_bebas_idr BIGINT;
    DECLARE v_prior_spouse_already_final_idr BIGINT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    -- Validation happens here, before the write reaches any trigger.
    IF p_entity_type <> 'orang_pribadi' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'ENTITY_TYPE_NOT_SUPPORTED';
    END IF;

    IF p_nib_last_4 IS NOT NULL
       AND p_nib_last_4 NOT REGEXP '^[0-9]{4}$' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'INVALID_NIB_FORMAT';
    END IF;

    START TRANSACTION;

    SELECT COUNT(*) INTO v_exists
      FROM vw_profiles
     WHERE user_id = p_user_id
       AND tax_year = p_tax_year;

    IF v_exists = 0 THEN
        INSERT INTO vw_profiles (
            id, user_id, tax_year, name, entity_type, nib_status,
            nib_last_4, kbli_code, business_description, marital_status,
            spouse_aggregation_active, is_new_taxpayer_current_year, version,
            spouse_current_usaha_idr, spouse_current_pekerjaan_bebas_idr,
            spouse_current_already_final_idr,
            prior_user_usaha_idr, prior_user_pekerjaan_bebas_idr,
            prior_user_already_final_idr,
            prior_spouse_usaha_idr, prior_spouse_pekerjaan_bebas_idr,
            prior_spouse_already_final_idr
        )
        VALUES (
            p_profile_id, p_user_id, p_tax_year, p_name, p_entity_type,
            p_nib_status, p_nib_last_4, p_kbli_code, p_business_description,
            p_marital_status, p_spouse_aggregation_active,
            p_is_new_taxpayer_current_year, 1,
            p_spouse_current_usaha_idr, p_spouse_current_pekerjaan_bebas_idr,
            p_spouse_current_already_final_idr,
            p_prior_user_usaha_idr, p_prior_user_pekerjaan_bebas_idr,
            p_prior_user_already_final_idr,
            p_prior_spouse_usaha_idr, p_prior_spouse_pekerjaan_bebas_idr,
            p_prior_spouse_already_final_idr
        );

        SET p_new_version = 1;

        COMMIT;
    ELSE
        SELECT id, version, name, spouse_aggregation_active,
               is_new_taxpayer_current_year,
               spouse_current_usaha_idr,
               spouse_current_pekerjaan_bebas_idr,
               spouse_current_already_final_idr,
               prior_user_usaha_idr,
               prior_user_pekerjaan_bebas_idr,
               prior_user_already_final_idr,
               prior_spouse_usaha_idr,
               prior_spouse_pekerjaan_bebas_idr,
               prior_spouse_already_final_idr
          INTO v_id, v_current, v_name, v_spouse_aggregation_active,
               v_is_new_taxpayer_current_year,
               v_spouse_current_usaha_idr,
               v_spouse_current_pekerjaan_bebas_idr,
               v_spouse_current_already_final_idr,
               v_prior_user_usaha_idr,
               v_prior_user_pekerjaan_bebas_idr,
               v_prior_user_already_final_idr,
               v_prior_spouse_usaha_idr,
               v_prior_spouse_pekerjaan_bebas_idr,
               v_prior_spouse_already_final_idr
          FROM vw_profiles
         WHERE user_id = p_user_id
           AND tax_year = p_tax_year;

        IF v_current <> p_version THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'VERSION_CONFLICT';
        END IF;

        UPDATE vw_profiles
           SET name = p_name,
               entity_type = p_entity_type,
               nib_status = p_nib_status,
               nib_last_4 = p_nib_last_4,
               kbli_code = p_kbli_code,
               business_description = p_business_description,
               marital_status = p_marital_status,
               spouse_aggregation_active = p_spouse_aggregation_active,
               is_new_taxpayer_current_year = p_is_new_taxpayer_current_year,
               spouse_current_usaha_idr = p_spouse_current_usaha_idr,
               spouse_current_pekerjaan_bebas_idr = p_spouse_current_pekerjaan_bebas_idr,
               spouse_current_already_final_idr = p_spouse_current_already_final_idr,
               prior_user_usaha_idr = p_prior_user_usaha_idr,
               prior_user_pekerjaan_bebas_idr = p_prior_user_pekerjaan_bebas_idr,
               prior_user_already_final_idr = p_prior_user_already_final_idr,
               prior_spouse_usaha_idr = p_prior_spouse_usaha_idr,
               prior_spouse_pekerjaan_bebas_idr = p_prior_spouse_pekerjaan_bebas_idr,
               prior_spouse_already_final_idr = p_prior_spouse_already_final_idr,
               version = v_current + 1
         WHERE id = v_id
           AND user_id = p_user_id
           AND version = p_version;

        IF v_name <> p_name THEN
            INSERT INTO vw_profile_changes (
                id, profile_id, field, old_value, new_value
            )
            VALUES (
                CONCAT('chg_', UUID()), v_id,
                'name', v_name, p_name
            );
        END IF;

        IF v_spouse_aggregation_active <> p_spouse_aggregation_active THEN
            INSERT INTO vw_profile_changes (
                id, profile_id, field, old_value, new_value
            )
            VALUES (
                CONCAT('chg_', UUID()), v_id,
                'spouse_aggregation_active',
                CAST(v_spouse_aggregation_active AS CHAR),
                CAST(p_spouse_aggregation_active AS CHAR)
            );
        END IF;

        IF v_is_new_taxpayer_current_year <> p_is_new_taxpayer_current_year THEN
            INSERT INTO vw_profile_changes (
                id, profile_id, field, old_value, new_value
            )
            VALUES (
                CONCAT('chg_', UUID()), v_id,
                'is_new_taxpayer_current_year',
                CAST(v_is_new_taxpayer_current_year AS CHAR),
                CAST(p_is_new_taxpayer_current_year AS CHAR)
            );
        END IF;

        IF v_spouse_current_usaha_idr <> p_spouse_current_usaha_idr THEN
            INSERT INTO vw_profile_changes (
                id, profile_id, field, old_value, new_value
            )
            VALUES (
                CONCAT('chg_', UUID()), v_id,
                'spouse_current_usaha_idr',
                CAST(v_spouse_current_usaha_idr AS CHAR),
                CAST(p_spouse_current_usaha_idr AS CHAR)
            );
        END IF;

        IF v_spouse_current_pekerjaan_bebas_idr
           <> p_spouse_current_pekerjaan_bebas_idr THEN
            INSERT INTO vw_profile_changes (
                id, profile_id, field, old_value, new_value
            )
            VALUES (
                CONCAT('chg_', UUID()), v_id,
                'spouse_current_pekerjaan_bebas_idr',
                CAST(v_spouse_current_pekerjaan_bebas_idr AS CHAR),
                CAST(p_spouse_current_pekerjaan_bebas_idr AS CHAR)
            );
        END IF;

        IF v_spouse_current_already_final_idr
           <> p_spouse_current_already_final_idr THEN
            INSERT INTO vw_profile_changes (
                id, profile_id, field, old_value, new_value
            )
            VALUES (
                CONCAT('chg_', UUID()), v_id,
                'spouse_current_already_final_idr',
                CAST(v_spouse_current_already_final_idr AS CHAR),
                CAST(p_spouse_current_already_final_idr AS CHAR)
            );
        END IF;

        IF v_prior_user_usaha_idr <> p_prior_user_usaha_idr THEN
            INSERT INTO vw_profile_changes (
                id, profile_id, field, old_value, new_value
            )
            VALUES (
                CONCAT('chg_', UUID()), v_id,
                'prior_user_usaha_idr',
                CAST(v_prior_user_usaha_idr AS CHAR),
                CAST(p_prior_user_usaha_idr AS CHAR)
            );
        END IF;

        IF v_prior_user_pekerjaan_bebas_idr
           <> p_prior_user_pekerjaan_bebas_idr THEN
            INSERT INTO vw_profile_changes (
                id, profile_id, field, old_value, new_value
            )
            VALUES (
                CONCAT('chg_', UUID()), v_id,
                'prior_user_pekerjaan_bebas_idr',
                CAST(v_prior_user_pekerjaan_bebas_idr AS CHAR),
                CAST(p_prior_user_pekerjaan_bebas_idr AS CHAR)
            );
        END IF;

        IF v_prior_user_already_final_idr
           <> p_prior_user_already_final_idr THEN
            INSERT INTO vw_profile_changes (
                id, profile_id, field, old_value, new_value
            )
            VALUES (
                CONCAT('chg_', UUID()), v_id,
                'prior_user_already_final_idr',
                CAST(v_prior_user_already_final_idr AS CHAR),
                CAST(p_prior_user_already_final_idr AS CHAR)
            );
        END IF;

        IF v_prior_spouse_usaha_idr <> p_prior_spouse_usaha_idr THEN
            INSERT INTO vw_profile_changes (
                id, profile_id, field, old_value, new_value
            )
            VALUES (
                CONCAT('chg_', UUID()), v_id,
                'prior_spouse_usaha_idr',
                CAST(v_prior_spouse_usaha_idr AS CHAR),
                CAST(p_prior_spouse_usaha_idr AS CHAR)
            );
        END IF;

        IF v_prior_spouse_pekerjaan_bebas_idr
           <> p_prior_spouse_pekerjaan_bebas_idr THEN
            INSERT INTO vw_profile_changes (
                id, profile_id, field, old_value, new_value
            )
            VALUES (
                CONCAT('chg_', UUID()), v_id,
                'prior_spouse_pekerjaan_bebas_idr',
                CAST(v_prior_spouse_pekerjaan_bebas_idr AS CHAR),
                CAST(p_prior_spouse_pekerjaan_bebas_idr AS CHAR)
            );
        END IF;

        IF v_prior_spouse_already_final_idr
           <> p_prior_spouse_already_final_idr THEN
            INSERT INTO vw_profile_changes (
                id, profile_id, field, old_value, new_value
            )
            VALUES (
                CONCAT('chg_', UUID()), v_id,
                'prior_spouse_already_final_idr',
                CAST(v_prior_spouse_already_final_idr AS CHAR),
                CAST(p_prior_spouse_already_final_idr AS CHAR)
            );
        END IF;

        SET p_new_version = v_current + 1;

        COMMIT;
    END IF;
END$$

DROP PROCEDURE IF EXISTS sp_record_transaction$$
CREATE PROCEDURE sp_record_transaction(
    IN p_user_id VARCHAR(64),
    IN p_transaction_id VARCHAR(64),
    IN p_classification_event_id VARCHAR(64),
    IN p_tx_date DATE,
    IN p_amount_idr BIGINT,
    IN p_withheld_tax_amount_idr BIGINT,
    IN p_client_name VARCHAR(255),
    IN p_client_name_norm VARCHAR(255),
    IN p_description VARCHAR(255),
    IN p_invoice_no VARCHAR(64),
    IN p_invoice_no_norm VARCHAR(64),
    IN p_source_channel VARCHAR(32),
    IN p_category VARCHAR(32),
    IN p_source VARCHAR(32),
    IN p_confidence DECIMAL(5,4),
    IN p_rule_id VARCHAR(64),
    IN p_requires_clarification BOOLEAN,
    IN p_ruleset_id VARCHAR(64),
    IN p_effective_date DATE,
    OUT p_version INT
)
SQL SECURITY DEFINER
BEGIN
    -- FR-2.1, FR-2.2, FR-3.2, FR-3.3, FR-10: store one classified row and
    -- its classification event in one transaction.
    DECLARE v_nib_status VARCHAR(16);
    DECLARE v_profile_count INT;
    DECLARE v_duplicate_id VARCHAR(64);
    DECLARE v_ytd_before BIGINT;
    DECLARE v_ytd_after BIGINT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_category NOT IN ('usaha', 'pekerjaan_bebas', 'already_final', 'non_object') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'CATEGORY_NOT_SUPPORTED';
    END IF;

    IF p_amount_idr <= 0 OR p_withheld_tax_amount_idr < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'INVALID_AMOUNT';
    END IF;

    START TRANSACTION;

    SELECT COUNT(*), MAX(nib_status)
      INTO v_profile_count, v_nib_status
      FROM vw_profiles
     WHERE user_id = p_user_id
       AND tax_year = YEAR(p_tx_date);

    IF v_profile_count = 0 OR v_nib_status IS NULL OR v_nib_status = '' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'NIB_STATUS_NOT_CONFIGURED';
    END IF;

    SET v_duplicate_id = fn_duplicate_invoice_id(
        p_user_id, p_client_name_norm, p_invoice_no_norm,
        p_amount_idr, p_tx_date
    );

    IF v_duplicate_id IS NOT NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'DUPLICATE_INVOICE_TRANSACTION';
    END IF;

    SET v_ytd_before = fn_ytd_usaha_omzet(p_user_id, YEAR(p_tx_date), p_tx_date);
    SET v_ytd_after = v_ytd_before
        + IF(p_category = 'usaha', p_amount_idr, 0);

    INSERT INTO vw_transactions (
        id, user_id, image_id, tx_date, amount_idr, withheld_tax_amount_idr,
        client_name, client_name_norm, description, invoice_no,
        invoice_no_norm, source_channel, category, source, confidence,
        rule_id, requires_clarification, version
    )
    VALUES (
        p_transaction_id, p_user_id, NULL, p_tx_date, p_amount_idr,
        p_withheld_tax_amount_idr, p_client_name, p_client_name_norm,
        p_description, p_invoice_no, p_invoice_no_norm, p_source_channel,
        p_category, p_source, p_confidence, p_rule_id,
        p_requires_clarification, 1
    );

    INSERT INTO vw_classification_events (
        id, transaction_id, source, rule_id, citation,
        old_category, new_category, note, ytd_usaha_before_idr,
        ytd_usaha_after_idr, ruleset_id, effective_date
    )
    VALUES (
        p_classification_event_id, p_transaction_id,
        p_source, p_rule_id, '',
        '', p_category,
        IF(p_requires_clarification, 'Menunggu klarifikasi pengguna.', ''),
        v_ytd_before, v_ytd_after, p_ruleset_id, p_effective_date
    );

    SET p_version = 1;

    COMMIT;
END$$

DROP PROCEDURE IF EXISTS sp_upsert_month_snapshot$$
CREATE PROCEDURE sp_upsert_month_snapshot(
    IN p_user_id VARCHAR(64),
    IN p_snapshot_id VARCHAR(64),
    IN p_profile_id VARCHAR(64),
    IN p_month_key VARCHAR(7),
    IN p_status VARCHAR(16),
    IN p_ruleset_id VARCHAR(64),
    IN p_effective_date DATE,
    IN p_rounding_rule VARCHAR(16),
    IN p_scheme_eligibility_status VARCHAR(32),
    IN p_next_year_ineligible BOOLEAN,
    IN p_prior_year_resolution_source VARCHAR(32),
    IN p_input_hash VARCHAR(128),
    IN p_usaha_omzet_idr BIGINT,
    IN p_porsi_bebas_idr BIGINT,
    IN p_porsi_kena_idr BIGINT,
    IN p_tax_0_5_pct_idr BIGINT,
    IN p_withheld_tax_idr BIGINT,
    IN p_sisa_bayar_idr BIGINT,
    IN p_overwithheld_excess_idr BIGINT,
    IN p_overwithheld_status VARCHAR(32),
    IN p_pekerjaan_bebas_omzet_idr BIGINT,
    IN p_already_final_omzet_idr BIGINT,
    IN p_non_object_omzet_idr BIGINT,
    IN p_annotation VARCHAR(255)
)
SQL SECURITY DEFINER
BEGIN
    -- FR-5.1, FR-5.2, FR-5.4, FR-22: write one month computed by the engine.
    -- The engine remains the only calculator. This procedure stores its output.
    DECLARE v_owned INT;
    DECLARE v_exists INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT COUNT(*) INTO v_owned
      FROM vw_profiles
     WHERE id = p_profile_id
       AND user_id = p_user_id;

    IF v_owned = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'PROFILE_NOT_FOUND';
    END IF;

    SELECT COUNT(*) INTO v_exists
      FROM vw_month_snapshots
     WHERE profile_id = p_profile_id
       AND month_key = p_month_key;

    IF v_exists = 0 THEN
        INSERT INTO vw_month_snapshots (
            id, profile_id, month_key, status, ruleset_id, effective_date,
            rounding_rule, scheme_eligibility_status, next_year_ineligible,
            prior_year_resolution_source, input_hash, usaha_omzet_idr,
            porsi_bebas_idr, porsi_kena_idr, tax_0_5_pct_idr,
            withheld_tax_idr, sisa_bayar_idr, overwithheld_excess_idr,
            overwithheld_status, pekerjaan_bebas_omzet_idr,
            already_final_omzet_idr, non_object_omzet_idr, annotation
        )
        VALUES (
            p_snapshot_id, p_profile_id, p_month_key, p_status, p_ruleset_id,
            p_effective_date, p_rounding_rule, p_scheme_eligibility_status,
            p_next_year_ineligible, p_prior_year_resolution_source,
            p_input_hash, p_usaha_omzet_idr, p_porsi_bebas_idr,
            p_porsi_kena_idr, p_tax_0_5_pct_idr, p_withheld_tax_idr,
            p_sisa_bayar_idr, p_overwithheld_excess_idr,
            p_overwithheld_status, p_pekerjaan_bebas_omzet_idr,
            p_already_final_omzet_idr, p_non_object_omzet_idr, p_annotation
        );
    ELSE
        UPDATE vw_month_snapshots
           SET status = p_status,
               ruleset_id = p_ruleset_id,
               effective_date = p_effective_date,
               rounding_rule = p_rounding_rule,
               scheme_eligibility_status = p_scheme_eligibility_status,
               next_year_ineligible = p_next_year_ineligible,
               prior_year_resolution_source = p_prior_year_resolution_source,
               input_hash = p_input_hash,
               usaha_omzet_idr = p_usaha_omzet_idr,
               porsi_bebas_idr = p_porsi_bebas_idr,
               porsi_kena_idr = p_porsi_kena_idr,
               tax_0_5_pct_idr = p_tax_0_5_pct_idr,
               withheld_tax_idr = p_withheld_tax_idr,
               sisa_bayar_idr = p_sisa_bayar_idr,
               overwithheld_excess_idr = p_overwithheld_excess_idr,
               overwithheld_status = p_overwithheld_status,
               pekerjaan_bebas_omzet_idr = p_pekerjaan_bebas_omzet_idr,
               already_final_omzet_idr = p_already_final_omzet_idr,
               non_object_omzet_idr = p_non_object_omzet_idr,
               annotation = p_annotation
         WHERE profile_id = p_profile_id
           AND month_key = p_month_key;
    END IF;

    COMMIT;
END$$

DELIMITER ;
