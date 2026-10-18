/** Wire shapes from API v1.2.2. JSON fields stay snake_case. */

import type { Kategori, SourceChannel, Sumber } from "@/lib/domain";

export interface Me {
  user_id: string;
  email: string;
  username: string;
}

export interface SessionItem {
  id: string;
  device_label: string;
  created_at: string;
  last_seen_at: string;
  current: boolean;
}

export interface AuditEntry {
  changed_at: string;
  field: string;
  old_value: string;
  new_value: string;
}

export interface Profile {
  id: string;
  user_id: string;
  tax_year: number;
  name: string;
  entity_type: string;
  nib_status: "has_nib" | "no_nib" | "unknown" | string;
  nib_masked: string | null;
  kbli_code: string;
  business_description: string;
  marital_status: "yes" | "no" | "unknown" | string;
  spouse_aggregation_active: boolean;
  is_new_taxpayer_current_year: boolean;
  version: number;
  spouse_current_usaha_idr: number;
  spouse_current_pekerjaan_bebas_idr: number;
  spouse_current_already_final_idr: number;
  prior_user_usaha_idr: number;
  prior_user_pekerjaan_bebas_idr: number;
  prior_user_already_final_idr: number;
  prior_spouse_usaha_idr: number;
  prior_spouse_pekerjaan_bebas_idr: number;
  prior_spouse_already_final_idr: number;
  audit_trail: AuditEntry[];
}

export interface ProfileUpdate {
  version: number;
  name: string;
  entity_type: "orang_pribadi";
  nib_status: string;
  nib_last_4: string | null;
  kbli_code: string;
  business_description: string;
  marital_status: string;
  spouse_aggregation_active: boolean;
  is_new_taxpayer_current_year: boolean;
  spouse_current_usaha_idr: number;
  spouse_current_pekerjaan_bebas_idr: number;
  spouse_current_already_final_idr: number;
  prior_user_usaha_idr: number;
  prior_user_pekerjaan_bebas_idr: number;
  prior_user_already_final_idr: number;
  prior_spouse_usaha_idr: number;
  prior_spouse_pekerjaan_bebas_idr: number;
  prior_spouse_already_final_idr: number;
}

export interface Classification {
  category: Kategori;
  source: Sumber;
  confidence: number;
  rule_id: string;
  requires_clarification: boolean;
}

export interface Transaction {
  id: string;
  version: number;
  tx_date: string;
  client_name: string;
  invoice_no: string | null;
  amount_idr: number;
  withheld_tax_amount_idr: number;
  source_channel: SourceChannel;
  category: Kategori;
  source: Sumber;
  description: string;
  classification?: Classification | null;
}

export interface TransactionList {
  items: Transaction[];
  pagination: {
    current_page: number;
    per_page: number;
    total_items: number;
    total_pages: number;
  };
}

export interface TransactionCreate {
  amount_idr: number;
  tx_date: string;
  client_name: string;
  description: string;
  invoice_no?: string;
  withheld_tax_amount_idr: number;
  source_channel: SourceChannel;
}

export interface Clarification {
  transaction_id: string;
  question: string;
  options: { value: Kategori; label: string }[];
}

export interface AuditEvent {
  timestamp: string;
  source: string;
  rule_id?: string;
  citation?: string;
  assigned_category?: string;
  old_category?: string;
  new_category?: string;
  note?: string;
  ytd_usaha_omzet_before_idr?: number;
  ytd_usaha_omzet_after_idr?: number;
  ruleset_id?: string;
  effective_date?: string;
}

export interface Dashboard {
  metadata: {
    ruleset_id: string;
    effective_date: string;
    rounding_rule: string;
    disclaimer: string;
  };
  thresholds: {
    pita_500_juta: {
      limit_idr: number;
      ytd_usaha_omzet_idr: number;
      remaining_free_band_idr: number;
      split_month: string | null;
      annotation: string;
    };
    eligibility_prior_year_cap_4_8m: {
      limit_idr: number;
      combined_prior_year_gross_idr: number;
      resolution_source: string;
      status: string;
    };
    monitoring_current_year_cap_4_8m: {
      limit_idr: number;
      ytd_usaha_omzet_idr: number;
      ytd_pekerjaan_bebas_omzet_idr: number;
      ytd_already_final_omzet_idr: number;
      spouse_current_year_usaha_omzet_idr: number;
      spouse_current_year_pekerjaan_bebas_omzet_idr: number;
      spouse_current_year_already_final_omzet_idr: number;
      ytd_combined_gross_idr: number;
      next_year_ineligible: boolean;
    };
    pasal_58: {
      spouse_aggregation_active: boolean;
      badge_label: string;
    };
  };
  monthly_summaries: MonthSummary[];
}

export interface MonthSummary {
  month: string;
  scheme_eligibility_status: string;
  usaha_omzet_idr: number;
  porsi_bebas_idr: number;
  porsi_kena_idr: number;
  tax_0_5_pct_idr: number;
  withheld_tax_idr: number;
  sisa_bayar_idr: number;
  overwithheld_excess_idr: number;
  overwithheld_status: string;
  pekerjaan_bebas_omzet_idr: number;
  already_final_omzet_idr: number;
  non_object_omzet_idr: number;
  input_hash: string;
  annotation?: string;
}

export interface Recap {
  total_usaha_omzet_idr: number;
  total_porsi_bebas_idr: number;
  total_porsi_kena_idr: number;
  total_tax_0_5_pct_idr: number;
  total_withheld_tax_idr: number;
  total_sisa_bayar_idr: number;
  total_pekerjaan_bebas_omzet_idr: number;
  kap_kjs: string;
  scheme_eligibility_status: string;
  next_year_ineligible: boolean;
  disclaimer?: string;
}

export interface QuotaCounter {
  used: number;
  limit: number;
  status: "active" | "exhausted" | string;
}

export interface Quotas {
  month_key: string;
  timezone: string;
  reset_timestamp_utc: string;
  ai_classification: QuotaCounter;
  assistant_chat: QuotaCounter;
}

export interface SubscriptionStatus {
  subscription_tier: "gratis" | "pending" | "berbayar" | "kedaluwarsa" | string;
  paid_flag: boolean;
  valid_until_utc: string | null;
  valid_until_local: string | null;
  available_plans: { plan_id: string; duration_days?: number; price_idr?: number }[];
}

export interface SubscriptionOrder {
  order_id: string;
  plan_id?: string;
  amount_idr: number;
  status: string;
  payment_url?: string;
  expires_at_utc?: string;
  created_at?: string;
}

export interface AssistantAnswer {
  answer: string;
  citations: string[];
  quota_remaining: number;
}
