# Product backlog

The tracker of record is Plane, project IPPL. This file is the readable summary,
not a second source of truth. If the two disagree, Plane wins and this file is
the thing that needs fixing.

Plane holds 116 items: 24 top-level stories and 92 sub-tasks. Every story names
its SRS requirement ids, or is labelled `needs-decision` when the requirement
does not exist yet.

Requirement provenance: the SRS of record is **v2.7**, with `FR-01` to
`FR-47`, `FR-23a`, `FR-PAY-01` to `FR-PAY-09`, `NFR-01` to `NFR-15` (and
related), and `UC-01` to `UC-26`. It lives outside this repository under
`SPEC/`, beside **ERD r3** and **API v1.3.3**. The API contract is mirrored at
`docs/api/KlasifiPajak_API_Specification.md`.

Ids such as `FR-17`, `FR-23a`, `UC-20`, `NFR-12` and `NFR-13` are defined in
the SRS. Do not treat them as invented.

## M50 milestone (PRs #1-#4) : merged 2026-11-03

Parallel hardening / feature slice on `main` @ `3d5ced0` (merge of PR #3).

| PR  | Branch / theme                                                                                                         | Status     |
| --- | ---------------------------------------------------------------------------------------------------------------------- | ---------- |
| #1  | Storage: Alembic ERD r3, compose `migrate` one-shot, app vs migrate MySQL users, HEALTHCHECK / non-root image          | **merged** |
| #2  | Testing: CI gates (ruff, prettier, frontend `vue-tsc` build, fail-closed pip-audit, gitleaks, coverage, docker test)   | **merged** |
| #3  | Security: argon2id, password reset, sessions, account delete, rate limits, XFF/`TRUSTED_PROXY_IPS`, log redaction      | **merged** |
| #4  | Tax: CRUD/override/reclassify/audit-trail, versioned `month_snapshots`, `as_of` = today WIB, quotas/subscription reads | **merged** |
| #6  | UI: UX defects, transaction edit sheet, dashboard freshness, onboarding, responsive fixes                              | **merged** |
| #7  | Testing: Vitest test runner, transaction edit and field errors unit test coverage                                      | **merged** |
| #8  | UI: review follow-ups, 409 conflict reload, 422 field errors, unmount guards, single-source legal basis                | **merged** |
| #9  | Security: reject `.env.example` JWT placeholder and CHANGE_ME outside dev/test (HB-01)                                 | **merged** |

Follow-ups that are **not** merge blockers are tracked as B-11 outside this
repo's Lead backlog (quota reserve SQL, receipt byte cleanup after OCR,
snapshot history reads, CI SHA-pin, §5.31 mount-time gate, rate-limit TTL, …).

## Modules

| Module         | Covers                                          |
| -------------- | ----------------------------------------------- |
| Engine         | FR-17 to FR-23a, NFR-03                         |
| Classification | FR-10 to FR-16, FR-44, NFR-01, NFR-Q1 to NFR-Q3 |
| Profile        | FR-01 to FR-04, FR-45, FR-46                    |
| Transactions   | FR-05 to FR-09, FR-26, FR-26a                   |
| Storage        | FR-23a, FR-25, FR-39, FR-47                     |
| Payments       | FR-PAY-01 to FR-PAY-09, FR-34, FR-35            |
| Account        | FR-37, FR-41, FR-42, FR-43                      |
| Assistant      | FR-27 to FR-30a, NFR-10                         |
| Export         | FR-31 to FR-33                                  |
| UI             | Vue 3 frontend                                  |
| Quality        | Tests, Docker, CI, NFR-14                       |
| SRS, SDD       | Documentation                                   |

## Labels

`engine`, `classify`, `storage`, `payments`, `ui`, `tests`, `docker`,
`needs-decision`, `spec-v2`, plus the original `docs` and `planning`.

`needs-decision` is not decoration. Anything carrying it is waiting on the
developer, not on work.

## Engine — eligibility rules (SRS v2.7)

Done in code: `backend/tests/test_golden.py`, `backend/app/engine/compute.py`,
`backend/app/engine/types.py`, `backend/app/engine/ruleset/load.py`.

- [x] `rounding_rule` is a ruleset parameter, `floor` or `round_half_up`,
      default `floor`. TC-ARITH-500001 expects tax Rp 0 under both.
- [x] Prior-year gross revenue for eligibility is the sum of usaha,
      `pekerjaan_bebas`, and `already_final`, gross. Three profile fields.
- [x] FR-20: crossing the Rp 4,8 miliar cap in the current year keeps the
      current year's rate and only sets `next_year_at_risk`.
- [x] TC-GOLDEN-CAP-FIRST-YEAR, -CURRENT-YEAR, -PRIOR-YEAR,
      -COMPOSITION-FAIL, -COMPOSITION-PASS, -SPOUSE.
- [x] FR-21 / UC-13b: `spouse_in_band` / `spouse_in_cap` ruleset defaults.
- [x] FR-23 / UC-13c: `sisa_bayar_idr` and `overwithheld_excess_idr`.
- [x] FR-22 / UC-11a / NFR-02: canonical `input_hash` prefixed `v2:`.
- [x] FR-08 / FR-09 / FR-23a: editing or deleting a transaction recomputes later
      months. A month's hash includes `carry_forward` (earlier months' combined
      gross and usaha omzet), and each stored month carries its own cumulative
      `next_year_ineligible` (FR-20).
- [x] FR-03: prior-year empty vs zero (`UNSET`).
- [x] Versioned month snapshots (D-11 / ERD r3) + dashboard `as_of` = today WIB.
- [x] FR-31 L3-B Bagian A columns a to e, g and h: the annual recap and the PDF
      (`services/recap.py`) carry Bulan, a Bruto, b Akumulasi, c Tidak kena,
      d Kena pajak, e PPh final, g Dipotong and h Selisih, per month and in total.
- [ ] Still open: column f (Disetor sendiri) is printed empty because the app
      does not record self-paid tax, and the KAP/KJS value (`411128-420`) is a
      secondary, unconfirmed source (OD-3).

## Rubric features

These are **required for graded v1** (D-08). Mark a box only when this branch implements it:

- [x] OCR receipt upload (FR-06, FR-06a, FR-06b) — local storage, EXIF strip, confirm flow
- [x] Real Midtrans Snap + webhook (FR-PAY-01…05; FR-PAY-09 Should) — orders and webhook; settlement requires `status_code` `"200"`
- [x] AI classifier **and** assistant (FR-12/13 and FR-27…30) via 9router (D-09)
- [x] Annual recap PDF (FR-31…33); library locked to `fpdf2` (D-11)

## Payments — Midtrans Snap

Orders and the payment webhook are implemented. Settlement requires
`status_code` `"200"` in addition to a valid signature and a matching amount.
Contract is API **v1.3.3** §5.30 (SHA512 over Midtrans body fields and ServerKey;
a later pending, expire, or fail does not reverse settlement; 30-day renewal
from `max(now_utc, valid_until_utc)`). Never use production keys.

- [x] `GatewayAdapter` plus `FakeGatewayAdapter`
- [x] Signature verification with `hmac.compare_digest`
- [x] Reject a tampered `gross_amount` (`ORDER_AMOUNT_MISMATCH`)
- [x] Webhook idempotency; settlement is not reversed; 30-day renewal
- [x] Map Snap `redirect_url` → API `payment_url` (D-11)
- [ ] TODO: Status API confirmation before production

## Sprint 1 — docs and stack

- [x] Record the stack that already exists plus open decisions (IPPL-2)
- [x] Polish the SRS (IPPL-3)
- [x] Draft the SDD once the SRS feels complete
- [x] **BLOCKER** supply the PP 20/2026 elucidation golden values for `TC-GOLDEN-*`
- [x] **BLOCKER** write SRS covering payments, OCR, and the missing ids (now v2.7)

## Sprint 2 — classification without a model

- [x] Heuristic-first path, zero model calls — keyword table on transaction create
- [x] Non-object and already-final keyword table
- [ ] NFR-Q1 labeled set of at least 40 transactions: the evaluator
      (`backend/scripts/evaluate_classifier.py`) and the dev and held-out
      workbooks exist outside the repo, but the labels are drafted, not checked
      by the developer, and the rules changed after the last measurement.
      Missing: developer-reviewed labels.
- [ ] NFR-Q2, NFR-Q3 report heuristic accuracy: the 2026-11-09 scores in
      `backend/README.md` predate the 2026-11-11 rule changes. Missing: a
      re-measured dev and held-out score (issue #24).

## Sprint 3 — storage and dashboard

- [x] Profile capture and non-destructive history
- [x] Manual entry with validation; uniqueness key; empty invoice → NULL
- [x] Threshold tracker, monthly summary, disclaimer (WORKPAPER string locked)
- [x] SQL syntax reference under `docs/sql_syntaxes/` (not wired into services)
- [x] `GET /quotas` and `GET /subscriptions/status`; Alembic head = ERD r3
- [x] Compose `migrate` one-shot + app/migrate MySQL users (PR #1)

## Sprint 4 — AI fallback

- [x] Request bundle and validated reply (model path): background fallback in
      `services/classification_fallback.py` with `build_classification_messages`
      and `validate_classification`; consent and quota gated, quota refunded
      when no valid reply is stored
- [ ] One targeted clarifying question (model path): missing. The question on
      `GET /transactions/{id}/clarification` is a fixed template, not written
      by the model, and the model reply carries no question
- [x] Override and stale recompute (rules/user path on main)
- [x] Quota counters and `paid_flag` read models (reserve-on-AI still open)

## Sprint 5 — trace and demo

- [x] Per-transaction audit trail endpoint (PR #4)
- [x] FR-6.x read-only assistant (rubric)
- [x] FR-8.x annual workpaper PDF (rubric)
- [ ] Demo script, report numbers

## Frontend design — mockup v1.4.2 (25 Sep 2026)

Static HTML mockups live in `IPPL/mockup/` (outside this repo). UI strings
are Indonesian. The OCR, asisten and workpaper features have backend routes
and are switched on in `frontend/src/lib/capabilities.ts`, except the
subscription purchase UI (`subscriptionPurchase` is `false`, issue #22).

Live routes: `/`, `/masuk`, `/atur-ulang`, `/dasbor`, `/transaksi`,
`/transaksi/baru`, `/transaksi/:id` (Klasifikasi), `/asisten`, `/kuota`,
`/langganan/kembali`, `/profil`. The annual recap has no page of its own: it
is shown on the dashboard (`/dasbor`), with the workpaper PDF button.

- [ ] Mockup screens vs live routes: Profil, Transaksi, Klasifikasi, Dashboard
      and Asisten have routes. Rekap has none by design (dashboard). Missing:
      a screen-by-screen comparison against the mockup, which lives outside
      this repo; track in Plane
- [ ] **needs-decision** residual UI gaps: there is no Pengaturan route, and
      the OCR upload on `/transaksi/baru` tells a free account to see the
      Kuota page while the purchase UI there is off (issue #22). Whether to
      add Pengaturan is undecided

## Quality gates

- [x] Lint and format: ruff + Prettier (Husky + CI)
- [x] Conventional Commits (commitlint)
- [x] GitHub Actions CI on push/PR to `main` (`.github/workflows/ci.yml`):
      lint & format → frontend typecheck/build → pip-audit (high/critical,
      fail-closed) → gitleaks → pytest coverage gate 80% on
      `backend/app/engine` (NFR-14) → Docker test image
- [ ] CD to CasaOS — undecided

## Definition of done

See [definition-of-done.md](definition-of-done.md).
