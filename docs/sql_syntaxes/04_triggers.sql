-- KlasifiPajak SQL syntax reference: triggers.
--
-- A trigger executes one mechanical assignment for its own incoming row. It
-- has no IF, no handler, no SELECT, no validation, and no second statement
-- against the table that fired it. Validation and derivation happen in the
-- procedure before the write.
--
-- MySQL rejects a second statement against the firing table (error 1442), so
-- the stamp is assigned through NEW on BEFORE INSERT. Procedures omit these
-- timestamp columns and rely on the trigger for them.

DELIMITER $$

DROP TRIGGER IF EXISTS trg_users_stamp$$
CREATE TRIGGER trg_users_stamp
BEFORE INSERT ON users
FOR EACH ROW
BEGIN
    -- FR-37 to FR-42: stamp the creation instant, UTC.
    SET NEW.created_at = UTC_TIMESTAMP(6);
END$$

DROP TRIGGER IF EXISTS trg_sessions_stamp$$
CREATE TRIGGER trg_sessions_stamp
BEFORE INSERT ON sessions
FOR EACH ROW
BEGIN
    -- FR-40 to FR-42: stamp the issue instant, UTC.
    SET NEW.issued_at_utc = UTC_TIMESTAMP(6);
    SET NEW.last_seen_at = NEW.issued_at_utc;
END$$

DROP TRIGGER IF EXISTS trg_profile_changes_stamp$$
CREATE TRIGGER trg_profile_changes_stamp
BEFORE INSERT ON profile_changes
FOR EACH ROW
BEGIN
    -- FR-1.2: stamp the audit instant, UTC.
    SET NEW.changed_at = UTC_TIMESTAMP(6);
END$$

DROP TRIGGER IF EXISTS trg_classification_events_stamp$$
CREATE TRIGGER trg_classification_events_stamp
BEFORE INSERT ON classification_events
FOR EACH ROW
BEGIN
    -- FR-3.2, FR-3.3: stamp the classification instant, UTC.
    SET NEW.recorded_at = UTC_TIMESTAMP(6);
END$$

DELIMITER ;
