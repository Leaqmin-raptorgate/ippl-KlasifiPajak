-- KlasifiPajak SQL syntax reference: database optimization.
--
-- Indexes match the filters the procedures actually run. Every index leads
-- with user_id where the query is user scoped (invariant 8). Do not index
-- amount_idr alone: it has low selectivity and no query filters on it without
-- user_id.
--
-- Base indexes already exist from the schema: unique email_norm,
-- unique username_norm, unique (user_id, tax_year), unique
-- (profile_id, month_key), and one index per foreign key. The statements below
-- add the composite indexes those single-column indexes cannot serve.

-- Session cap and idle checks: user_id, live rows, expiry, recency.
ALTER TABLE sessions
    ADD INDEX ix_sessions_active
        (user_id, revoked_at, expires_at_utc, last_seen_at);

-- Transaction list and YTD window scans.
ALTER TABLE transactions
    ADD INDEX ix_transactions_user_date
        (user_id, tx_date);
ALTER TABLE transactions
    ADD INDEX ix_transactions_user_category_date
        (user_id, category, tx_date);

-- Duplicate invoice lookup. invoice_no_norm is the selective column after
-- user_id, so it comes before the less selective client and amount columns.
ALTER TABLE transactions
    ADD INDEX ix_transactions_duplicate
        (user_id, invoice_no_norm, client_name_norm, amount_idr, tx_date);

-- Audit and classification history read in time order.
ALTER TABLE profile_changes
    ADD INDEX ix_profile_changes_profile_time
        (profile_id, changed_at);
ALTER TABLE classification_events
    ADD INDEX ix_classification_events_transaction_time
        (transaction_id, recorded_at);

-- Verify a plan before and after. Expect type=ref, the named key, and a small
-- rows estimate. Use EXPLAIN ANALYZE when the server is idle.
EXPLAIN SELECT id
          FROM transactions
         WHERE user_id = 'usr_example'
           AND invoice_no_norm = 'inv-2026-104'
           AND client_name_norm = 'pt sumber makmur'
           AND amount_idr = 12500000
           AND tx_date = '2026-10-15';

EXPLAIN SELECT COALESCE(SUM(amount_idr), 0)
          FROM transactions
         WHERE user_id = 'usr_example'
           AND category = 'usaha'
           AND tx_date >= '2026-01-01'
           AND tx_date <= '2026-10-18';

EXPLAIN SELECT id
          FROM sessions
         WHERE user_id = 'usr_example'
           AND revoked_at IS NULL
           AND expires_at_utc > UTC_TIMESTAMP(6)
         ORDER BY last_seen_at DESC
         LIMIT 5;

-- Refresh statistics after a bulk load or a large index change.
ANALYZE TABLE sessions, transactions, profile_changes, classification_events;

-- Test an index without committing to it. Invisible indexes still cost writes.
-- ALTER TABLE transactions ALTER INDEX ix_transactions_duplicate INVISIBLE;
-- ALTER TABLE transactions ALTER INDEX ix_transactions_duplicate VISIBLE;

-- MySQL 8 builds these online. Prefer a low-traffic window anyway, because a
-- long index build still holds metadata locks at the start and end.
