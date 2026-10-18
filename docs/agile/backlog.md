# Product backlog

The tracker of record is Plane, project IPPL. This file is the readable summary,
not a second source of truth. If the two disagree, Plane wins and this file is
the thing that needs fixing.

Plane holds 116 items: 24 top-level stories and 92 sub-tasks. Every story names
its SRS requirement ids, or is labelled `needs-decision` when the requirement
does not exist yet.

Requirement provenance matters here. The SRS of record is **v2.6**, dated 18 Okt
2026, with `FR-01` to `FR-47`, `FR-23a`, `FR-PAY-01` to `FR-PAY-09`, `NFR-01` to
`NFR-14` and `UC-01` to `UC-26`. It is on disk at
`SPEC/KlasifiPajak/KlasifiPajak_SRS.md`, beside ERD v1.2.2 and API v1.2.2.

Ids such as `FR-17`, `FR-23a`, `UC-20`, `NFR-12` and `NFR-13` are defined in
v2.6. Do not treat them as invented.

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
| SRS, SDD       | Documentation, existing                         |

## Labels

`engine`, `classify`, `storage`, `payments`, `ui`, `tests`, `docker`,
`needs-decision`, `spec-v2`, plus the original `docs` and `planning`.

`needs-decision` is not decoration. Anything carrying it is waiting on the
developer, not on work.

## Engine — eligibility rules (SRS v2.6, SDD v1.3)

Done in code: `backend/tests/test_golden.py`, `backend/app/engine/compute.py`,
`backend/app/engine/types.py`, `backend/app/engine/ruleset/load.py`.

- [x] `rounding_rule` is a ruleset parameter, `floor` or `round_half_up`,
      default `floor`. TC-ARITH-500001 expects tax Rp 0 under both, so the
      figure is locked without waiting for the elucidation text.
- [x] Prior-year gross revenue for eligibility is the sum of usaha,
      `pekerjaan_bebas`, and `already_final`, gross. Three profile fields.
- [x] FR-20: crossing the Rp 4,8 miliar cap in the current year keeps the
      current year's rate and only sets `next_year_at_risk`. Test:
      `test_crossing_the_cap_in_the_current_year_keeps_the_rate`.
- [x] TC-GOLDEN-CAP-FIRST-YEAR, -CURRENT-YEAR, -PRIOR-YEAR,
      -COMPOSITION-FAIL, -COMPOSITION-PASS, -SPOUSE. All six in the test file.
- [x] FR-21 / UC-13b: `spouse_in_band` and `spouse_in_cap` are ruleset
      parameters defaulting to `false` / `true` per PMK 164/2023 Lampiran B.
      Spouse omzet joins the cap check only, never the free band.
      `TODO(PASAL-58)` is **closed** by v2.6.
- [x] FR-23 / UC-13c: `sisa_bayar_idr` and `overwithheld_excess_idr` on `Line`
      and `MonthSummary`, both non-negative. Excess is surfaced as _belum
      diperhitungkan_, never carried forward. `TODO(LEBIH-POTONG)` is
      **provisionally closed** by v2.6 §4.5 item 1.
- [x] FR-22 / UC-11a / NFR-02: canonical `input_hash` prefixed `v1:`, hashed
      per month, payload carrying `rate_str`, both spouse switches and the
      prior-year resolution source. `TODO(PENYELARASAN)` is **closed**.
- [x] FR-03: prior-year fields distinguish _not filled in_ from a genuine
      zero, as v2.6 requires. This is what makes TC-GOLDEN-CAP-FIRST-YEAR
      (new taxpayer, no prior data) a real case rather than an accident of
      `int = 0` defaults.
- [x] FR-21 `agregasi_pasal_58` is a boolean distinct from FR-03 marital
      status. Both are on `Profile`.
- [ ] Still open: L3-B Bagian A columns (FR-31) and live KAP/KJS values.

## Payments — Midtrans Snap sandbox (SDD 1.3)

- [ ] Webhook notification fields, SHA512 signature check with
      `hmac.compare_digest`, and status normalisation. Contract is in
      `SPEC/KlasifiPajak/KlasifiPajak_SDD.md` section 4.8.
- [x] FR-PAY-01 to FR-PAY-08 Must, FR-PAY-09 Should (SRS 4.9).

## Sprint 1 — docs and stack

- [x] Record the stack that already exists plus open decisions (IPPL-2)
- [x] Polish the SRS (IPPL-3)
- [x] Draft the SDD once the SRS feels complete
- [x] **BLOCKER** supply the PP 20/2026 elucidation golden values for `TC-GOLDEN-*`
- [x] **BLOCKER** write SRS v2.6 covering payments, OCR, and the missing ids

## Sprint 2 — classification without a model

- [x] FR-3.2 heuristic-first path, zero model calls (IPPL-9) — the keyword
      table runs inside transaction create
- [x] FR-3.3 non-object and already-final keyword table (IPPL-10)
- [ ] NFR-Q1 labeled set of at least 40 transactions (IPPL-11)
- [ ] NFR-Q2, NFR-Q3 report heuristic accuracy

## Sprint 3 — storage and dashboard

- [x] FR-1.1, FR-1.2 profile capture and non-destructive history (IPPL-13)
- [x] FR-2.1 manual entry with validation (IPPL-14)
- [x] FR-2.2 uniqueness key, empty invoice number stored as NULL (IPPL-15)
- [x] FR-5.1, FR-5.2, FR-5.4 threshold tracker, monthly summary, disclaimer (IPPL-16)
- [x] SQL syntax reference under `docs/sql_syntaxes/` (procedures, functions,
      views, triggers, access, optimization); not wired into services yet
- [x] `GET /quotas` and `GET /subscriptions/status` read models; idempotent
      demo seed with one gratis and one berbayar account

## Sprint 4 — AI fallback

- [ ] FR-3.4, FR-3.5 request bundle and validated reply (IPPL-17)
- [ ] FR-3.6 one targeted clarifying question (IPPL-18)
- [ ] FR-3.7, FR-3.8 override and stale recompute (IPPL-19)
- [ ] FR-9.1, FR-9.2 quota counters and `paid_flag` (IPPL-20)

## Sprint 5 — trace and demo

- [ ] FR-7.1 per-transaction trace (IPPL-21)
- [ ] FR-6.1 to FR-6.4 read-only assistant (stretch)
- [ ] FR-8.1 to FR-8.3 annual workpaper PDF (stretch)
- [ ] Demo script, README, report numbers

## Frontend design — mockup v1.4.2 (25 Sep 2026)

Static HTML mockups live in `IPPL/mockup/` (outside this repo). Synced to Plane
as one story per screen, plus one `needs-decision` story for gaps. UI strings
are Indonesian.

- [ ] Mockup 1/6 Profil Usaha onboarding — `index.html` (Sprint 3)
- [ ] Mockup 2/6 Tambah Transaksi + bukti upload with OCR preview — `transaksi.html` (Sprint 3)
- [ ] Mockup 3/6 Hasil Klasifikasi — verdict, alasan, one closed question, what-if cards — `klasifikasi.html` (Sprint 4)
- [ ] Mockup 4/6 Dashboard — omzet cap progress, monthly summary, PPh split — `dashboard.html` (Sprint 3)
- [ ] Mockup 5/6 Tanya Asisten — read-only chat with citations — `asisten.html` (Sprint 5, stretch)
- [ ] Mockup 6/6 Rekap Tahunan — workpaper table, CSV + PDF export — `rekap.html` (Sprint 5, stretch)
- [ ] **needs-decision** frontend gaps: Pengaturan screen, onboarding step 2,
      OCR paywall vs v2.6 FR-06, Pasal 17 range on the what-if card, UI tag to
      category mapping, override note, CSV export scope, confirmation-learning
      behaviour, unexplained "Rp 0" (Sprint 1)

## Payments, no sprint yet

Held in backlog. API v1.2.2 §5.30 fixes the contract: HMAC-SHA256 over
`order_id\nstatus\namount_str`, with monotonic order status and 30-day renewal.

- [ ] Read the payment contract in API v1.2.2 §5.30 and capture a sandbox payload
- [ ] Signature verification with `hmac.compare_digest`
- [ ] Reject a tampered `gross_amount_idr`
- [ ] `GatewayAdapter` plus `FakeGatewayAdapter`
- [ ] Webhook idempotency, monotonic status, renewal arithmetic

## Quality gates

- [x] Lint and format: ruff (`npm run lint`) and ruff format + Prettier
      (`npm run format:check`), enforced by the Husky pre-commit hook and in CI
- [x] Conventional Commits enforced by commitlint (`.husky/commit-msg`)
- [x] GitHub Actions CI on push and PR to `main`: lint and format first, then
      pytest with a branch coverage gate of 80% on `backend/app/engine` (NFR-14),
      plus the same suite inside the Docker test image
      (`.github/workflows/ci.yml`)
- [ ] CD to CasaOS — undecided; needs a self-hosted runner or SSH deploy
      decision first

## Definition of done

See [definition-of-done.md](definition-of-done.md).
