## Summary

M50 Tax lane: transaction edit/delete/override/reclassify, FR-16a audit trail, FR-22/23a D-11 snapshot versioning (usang → new berlaku at version+1), FR-47 monthly jejak, and real quota counters with free 10/15 vs paid 200. Frontend capability flags for `manualOverride`, `deleteTransaction`, `reclassifyAll`, and `auditTrail` are flipped on.

Specs targeted: **ERD r3**, **API v1.3.1** (§5.16 provisional_category, §5.17 `version` + 409 `VERSION_CONFLICT`, §5.20 provisional omzet fields, §5.22 mark_usang / only-usang recalculate).

WORKPAPER disclaimer retained (exact D-07 / API §3.3 string) on dashboard and month-snapshot responses. Integer money and once-per-month floor/ruleset stamp/`input_hash` preserved on snapshot writes (B-08).

## Scope ownership

| Concern | Owner in this PR |
| --- | --- |
| Dashboard `status == 'berlaku'` read filter | Tax (this PR) — `dashboard.py` |
| Snapshot writers: mark prior `berlaku` → `usang`, insert `version + 1` | Tax (this PR) — sole writer; race-safe |
| Schema + Alembic for `month_snapshots.version` UK and `quota_counters` | Storage (PR #1); Tax keeps a model shim until #1 merges, then rebase |


## Optimistic concurrency (PUT lost-update fix)

API §5.12 TOCTOU closed: mutating paths take **profile `FOR UPDATE` first**, then
`SELECT … FOR UPDATE` on the transaction row, then (for versioned writes) a
conditional `UPDATE … WHERE version=:expected` (`rowcount==0` → 409
`VERSION_CONFLICT`). Applied to PUT, clarification (when `version` sent),
override, reclassify, and delete.

Lock order (all writers): **profile → transaction → snapshots**.
`_stale_and_rebuild` and snapshot-touching profile updates call `lock_profile`
before `mark_usang` (closes the prior snapshots-before-profile deadlock window).

## Dedicated test database

Local suite for this head uses a **Tax-owned** MySQL 8 container (not shared
`:3307`, not the reviewer's `:3310`):

| | |
| --- | --- |
| Container | `klasifi-mysql-tax-m50` (`mysql:8.0`) |
| Host publish | `127.0.0.1:3312→3306` (host map flaky from this box — use container IP) |
| Container IP | `172.17.0.4:3306` |
| Database | `klasifipajak_tax_m50` |
| User / pass | `taxm50` / `taxm50` |
| `DATABASE_URL` | `mysql+pymysql://taxm50:taxm50@172.17.0.4:3306/klasifipajak_tax_m50` |

## Snapshot writer (D-11 / §5.22) and race safety

**This PR owns the writer.** Call sites only invoke `snapshots_store.rebuild` / `mark_usang` / `get_berlaku`.

Reviewer blockers addressed in this head:

1. **Profile `FOR UPDATE` first** in `rebuild` (before any snapshot / `MAX(version)` read).
2. **Exhausted UK `IntegrityError` → `409 VERSION_CONFLICT`** with session `rollback()` — no partial berlaku write.
3. **§5.22 / FR-23a**: write paths do **not** blanket-`mark_usang` before rebuild — `rebuild` hash-compares the live berlaku and no-ops (description-only PUT). Hash mismatch → prior berlaku usang + `version+1`. `POST …/recalculate` stays `only_usang=True`.
4. **Quotas**: GET `/quotas` commits only when a new zero-row counter is created; first-of-month insert uses savepoint + locking re-select on `IntegrityError` (RR-safe).
5. **PUT rebuild range**: earliest affected month → Jakarta `as_of` month (API §2.4; §5.12 “through December” = end of visible band). Past years → Dec; future years → none. Future-dated txs are stored but excluded from snapshots/dashboard.

Race safety: profile row lock + snapshot lock; prior `berlaku` → `usang`; insert `version+1` inside savepoints; locking `MAX(version)`; bounded UK retries.

## Rebase onto Storage PR #1 (hold until #1 merges)

Expected conflicts / resolution:

1. **`backend/app/services/snapshots_store.py`** — take **Tax** entire file (Jakarta as_of + D-11 usang/version+1 + locks/retry + §5.22). Discard Storage’s version=1 overwrite compat path.
2. **`backend/app/models/__init__.py`** — take **Storage** schema (Alembic-aligned); drop Tax-only shim comments Storage supersedes.
3. **`backend/app/services/dashboard.py`** — keep Tax’s `berlaku` filter.
4. **Frontend capability flags** — union Tax’s six flags in `frontend/src/lib/capabilities.ts` (`manualOverride`, `deleteTransaction`, `reclassifyAll`, `auditTrail`, and any Storage-added flags set `true`).
5. **Pick up from #1:** null-safe UK / `utf8mb4_bin` on `*_norm` (DDL/migration). Keep `httpx2>=2.0`. Re-run the suite after rebase.

**CI note:** Starlette TestClient now requires `httpx2`. This PR adds `httpx2>=2.0` to `requirements.txt` (same pin as Storage PR #1) so both `pytest (coverage gate)` and `docker test image` load `conftest` without waiting for #1 to merge. No Alembic / workflow / threshold changes.

## What changed

- **CRUD / override / reclassify**: `PUT`/`DELETE /transactions/{id}`, `POST .../override`, `POST /transactions/reclassify` with optimistic concurrency on `version`.
- **Audit trail (FR-16a)**: `GET /transactions/{id}/audit-trail` from `classification_events` (append-only; no public update/delete).
- **Snapshots (D-11 / FR-22/23a/47)**: `mark_usang` + race-safe `rebuild()`; dashboard `berlaku`-only; FR-47 month jejak; recalculate only usang.
- **Quotas (FR-39 / API §5.26)**: free AI 10 / assistant 15; paid 200/200 via `quota_counters` (read + boundary status).
- **Provisional**: clarification `version` → 409 `VERSION_CONFLICT` (§5.17); provisional omzet on dashboard (§5.20).

## Tests (TC ids)

`backend/tests/test_tax_crud_trace_quota.py` — every listed TC id has a real assertion (no docstring-only tags).

| Test | Covers |
| --- | --- |
| `test_tc_4_3_41_edit_amount_rebuilds_and_bumps_version` | TC-4.3-41 FR-08 (+ usang prior row) |
| `test_tc_4_3_42_put_moves_month_rebuilds_earlier_through_december` | TC-4.3-42 §5.12 Mar→Dec |
| `test_tc_4_3_43_put_stale_version_conflict` | TC-4.3-43 / §5.12 409 + no partial write |
| `test_tc_4_3_44_put_other_account_is_404` | TC-4.3-44 PUT IDOR |
| `test_tc_4_3_45_description_only_keeps_classification` | TC-4.3-45 |
| `test_tc_4_3_46_rejects_non_positive_amount` | TC-4.3-46 |
| `test_tc_4_3_47_failed_rebuild_after_edit_leaves_usang` | TC-4.3-47 FR-23a fail → usang |
| `test_tc_4_3_48_delete_cascades_events_and_rebuilds` | TC-4.3-48 FR-09 |
| `test_tc_4_3_49_delete_other_account_is_404` | TC-4.3-49 |
| `test_tc_4_3_50_delete_sole_month_tx_zeroes_snapshot` | TC-4.3-50 |
| `test_tc_4_3_52_delete_without_session_is_401` | TC-4.3-52 |
| `test_api_5_17_clarification_version_conflict` | API §5.17 409 |
| `test_override_and_audit_trail_fr16a` | FR-16a / §5.18–5.19 |
| `test_tc_pr4_aud_01_audit_trail_append_only` | TC-PR4-AUD-01 append-only |
| `test_reclassify_rules_layer` | API §5.9 |
| `test_tc_4_5_54_58_mark_usang_then_recalculate` | TC-4.5-54 / TC-4.5-58 |
| `test_tc_4_5_55_triggers_mark_usang` | TC-4.5-55 triggers |
| `test_tc_4_5_56_failed_recalc_leaves_usang` | TC-4.5-56 mid-rebuild fault |
| `test_tc_4_5_59_and_d11_usang_money_immutable` | TC-4.5-59 + D-11 money freeze |
| `test_tc_4_5_noop_recalc_does_not_bump` | §5.22 hash / nothing-usang no-op |
| `test_tc_4_5_60_exactly_one_berlaku_after_n_recalcs` | TC-4.5-60 |
| `test_tc_4_5_61_concurrent_rebuilds_one_berlaku` | TC-4.5-61 |
| `test_tc_4_5_62_integrity_error_version_retry` | TC-4.5-62 |
| `test_tc_4_5_63_exhausted_retries_return_409` | TC-4.5-63 409 no partial |
| `test_tc_4_6_24_free_quota_counters` | TC-4.6-24 free 10/15 |
| `test_tc_4_6_25_paid_quota_limits` | TC-4.6-25 paid 200 |
| `test_tc_4_6_26_quota_boundaries_free_and_paid` | TC-4.6-26 used=limit−1 / =limit |
| `test_tc_4_6_27_quotas_are_session_scoped` | TC-4.6-27 |
| `test_tc_4_6_28_month_key_follows_asia_jakarta` | TC-4.6-28 |
| `test_tc_4_6_29_fr47_month_jejak` | TC-4.6-29 FR-47 |
| `test_tc_4_6_30_missing_month_snapshot_is_404` | TC-4.6-30 |
| `test_tc_4_6_31_snapshot_requires_session` | TC-4.6-31 |
| `test_tc_4_6_32_input_hash_is_v1_prefixed` | TC-4.6-32 |
| `test_tc_hard_31_exact_workpaper_disclaimer` | TC-HARD-31 exact WORKPAPER string |
| `test_hb12_cap_eq_stays_eligible_dashboard` | HB-12 / TC-4.5-27 EQ |
| `test_tc_4_5_28_hb12_plus_one_ineligible` | TC-4.5-28 / HB-12 +1 `4_800_000_001` |
| `test_tc_4_3_64_parallel_puts_same_version_one_winner` | TC-4.3-64 N≥8 parallel PUTs → 1×2xx + (N−1)×409; version +1 |
| `test_tc_4_5_64_concurrent_put_and_recalculate_no_deadlock` | TC-4.5-64 PUT∥recalculate; no deadlock; one berlaku |
| `test_tc_argon_asof_future_tx_excluded_from_snapshots_and_dashboard` | Argon #2 / §2.4 future tx excluded |
| `test_tc_argon_month_path_foo_is_422` | Argon #5 month path validation |
| `test_tc_argon_quota_ensure_counter_race` | Argon #6 concurrent first GET /quotas |

**Dropped tags (no assert in this PR — out of Tax M50 write scope):** TC-4.3-51 (OCR image_id delete / Storage FR-06), TC-4.5-57 (lock not held during OCR/model).

**Suite**: 117 passed (MySQL 8 @ `klasifipajak_tax_m50` / `klasifi-mysql-tax-m50`). **Ruff**: clean. **Coverage**: 88.99% (CI gate `--cov-fail-under=80`).

## Argon external review (findings 1–6) — verified + fixed locally

| # | Sev | Verdict | Fix |
| --- | --- | --- | --- |
| 1 | BLOCKER | **Verified** — `routes_app.subscription_override` ran `db.scalar(select(User))` (AGENTS.md layering / REVIEW.md). Sole ORM-in-route; audit found no other. | Lookup moved into `subscription_service.set_subscription_override(db, user_id=…)`. |
| 2 | HIGH | **Verified** — `as_of=date(tax_year,12,31)` + PUT `end_month=12` vs API §2.4/§5.11. | Freezable `today_jakarta`; `as_of_for_tax_year` / `snapshot_end_month`; rebuild filters `tx_date<=as_of`. |
| 3 | HIGH | **Verified** — `_usaha_total(exclude_id=…)` on existing rows made override before=0. | Exclude only on create; existing include prior usaha; filter tax_year + as_of. Override/reclassify: before=`12_500_000`, after=`0`. |
| 4 | MEDIUM | **Verified** — blanket `mark_usang` before rebuild made hash no-op unreachable. | Write path skips pre-mark; rebuild compares hash. TC-4.3-45 asserts version/hash unchanged. |
| 5 | MEDIUM | **Verified** — `int(month)` on `'foo'` → 500. Spec §5.21 404 for missing; invalid → **422 `INVALID_DATE_RANGE`**. | `_parse_month_key` + TC. |
| 6 | MEDIUM | **Verified** — `_ensure_counter` TOCTOU on first GET `/quotas`. | Savepoint + locking re-select; commit-only-if-created. Concurrency TC. |

**PR #1 status**: still **OPEN** (`feat/sto-alembic-snapshot-version` @ `50e8f69`) — **no rebase onto main / no force-push**.

## Deferred

- **API §2.7 / FR-39 quota reserve** (`UPDATE … used = used + 1 WHERE used < limit`) is **deferred to FR-39 AI work** — this PR exposes read counters + exhausted boundaries only; no conditional increment path.
- **Receipt DELETE cleanup** and **GET usang history** remain follow-ups.
- **CI `httpx2`**: fixed in-lane via `requirements.txt` (`httpx2>=2.0`); Storage #1 still carries the same pin for its own merge.

## Out of scope / process

- Do **not** rebase onto Storage PR #1 until it merges (Lead).
- No merge, auto-merge, reviewers, or PR comments from the authoring agent.

## Push status

Argon (1)–(6) committed locally on `feat/tax-crud-trace-quota` — **not pushed** (awaiting user go-ahead). PR #1 remains open — no rebase onto main / no force-push.
