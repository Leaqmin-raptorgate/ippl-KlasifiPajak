-- KlasifiPajak SQL syntax reference: views.
--
-- One view per base table. Each is a one-table projection: no joins, no
-- aggregates, no logic, and no call to a function or trigger. That keeps every
-- view updatable, which is how a procedure writes without naming a base table.
-- Column order matches the base table so INSERT and UPDATE through the view are
-- unambiguous.

CREATE OR REPLACE VIEW vw_users AS
SELECT id,
       email,
       email_norm,
       username,
       username_norm,
       password_hash,
       paid_flag,
       valid_until_utc,
       created_at
  FROM users;

CREATE OR REPLACE VIEW vw_sessions AS
SELECT id,
       user_id,
       device_label,
       issued_at_utc,
       expires_at_utc,
       last_seen_at,
       revoked_at
  FROM sessions;

CREATE OR REPLACE VIEW vw_profiles AS
SELECT id,
       user_id,
       tax_year,
       name,
       entity_type,
       nib_status,
       nib_last_4,
       kbli_code,
       business_description,
       marital_status,
       spouse_aggregation_active,
       is_new_taxpayer_current_year,
       version,
       spouse_current_usaha_idr,
       spouse_current_pekerjaan_bebas_idr,
       spouse_current_already_final_idr,
       prior_user_usaha_idr,
       prior_user_pekerjaan_bebas_idr,
       prior_user_already_final_idr,
       prior_spouse_usaha_idr,
       prior_spouse_pekerjaan_bebas_idr,
       prior_spouse_already_final_idr
  FROM profiles;

CREATE OR REPLACE VIEW vw_profile_changes AS
SELECT id,
       profile_id,
       changed_at,
       field,
       old_value,
       new_value
  FROM profile_changes;

CREATE OR REPLACE VIEW vw_transactions AS
SELECT id,
       user_id,
       image_id,
       tx_date,
       amount_idr,
       withheld_tax_amount_idr,
       client_name,
       client_name_norm,
       description,
       invoice_no,
       invoice_no_norm,
       source_channel,
       category,
       source,
       confidence,
       rule_id,
       requires_clarification,
       version
  FROM transactions;

CREATE OR REPLACE VIEW vw_classification_events AS
SELECT id,
       transaction_id,
       recorded_at,
       source,
       rule_id,
       citation,
       old_category,
       new_category,
       note,
       ytd_usaha_before_idr,
       ytd_usaha_after_idr,
       ruleset_id,
       effective_date
  FROM classification_events;

CREATE OR REPLACE VIEW vw_month_snapshots AS
SELECT id,
       profile_id,
       month_key,
       status,
       ruleset_id,
       effective_date,
       rounding_rule,
       scheme_eligibility_status,
       next_year_ineligible,
       prior_year_resolution_source,
       input_hash,
       usaha_omzet_idr,
       porsi_bebas_idr,
       porsi_kena_idr,
       tax_0_5_pct_idr,
       withheld_tax_idr,
       sisa_bayar_idr,
       overwithheld_excess_idr,
       overwithheld_status,
       pekerjaan_bebas_omzet_idr,
       already_final_omzet_idr,
       non_object_omzet_idr,
       annotation
  FROM month_snapshots;
