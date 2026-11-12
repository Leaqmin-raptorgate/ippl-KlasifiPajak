# Implementation roadmap

Goal: working demo before December. Optimize for finishing, not for completeness.

Tracking lives in Plane, project IPPL. This file explains the sequence and the
reasoning; Plane holds the items.

## Current state (3 Nov 2026)

Done on `main` (M50 PRs #1–#4 merged; tip `3d5ced0`):

- Tax engine at `backend/app/engine/`, pure Python, no framework, no model.
- Ruleset as data at `backend/app/engine/ruleset/pp20_2026.json`.
- **SRS v2.7 / API v1.3.3 / ERD r3** are the artefacts of record (SRS + ERD
  outside the repo; API mirrored under `docs/api/`).
- Bagian A aligned to the API contract (`/health`, `/ruleset`, `POST /snapshot`).
- Authenticated Bagian B: register/login/logout/me, password reset, sessions,
  account delete (argon2id, rate limits, `TRUSTED_PROXY_IPS`).
- Profiles, transactions CRUD, clarification/override/reclassify, audit trail,
  dashboard with `as_of` = today `Asia/Jakarta`, versioned `month_snapshots`,
  quotas and subscription status reads.
- Alembic initial revision = ERD r3; compose **one-shot `migrate`** service;
  runtime uses `klasifipajak_app`, DDL uses `klasifipajak_migrate`.
- CI: lint/format, frontend `vue-tsc` build, fail-closed pip-audit, gitleaks,
  engine coverage gate, docker test image.

**Rubric features (D-08):** OCR receipt upload (FR-06*), Midtrans orders and
webhook (FR-PAY-*), the AI classifier and assistant (9router / D-09) and the
annual recap PDF (`fpdf2` / D-11) are implemented. Still open: Midtrans Status
API confirmation and live keys.

### Recorded deviations

- Storage uses SQLAlchemy 2.0 ORM for v1 demo (D-07 / HB-19). Stored-procedure
  tier under `docs/sql_syntaxes/` remains a Should, not a Must.
- Runtime schema comes from Alembic, not `Base.metadata.create_all`.
- The classifier runs the keyword/rules table first and falls back to the
  model (D-09) only when no rule is decisive.
- Disclaimer string locked (D-07):
  `DOKUMEN KERJA (WORKPAPER) — BUKAN SPT RESMI DAN BUKAN PRODUK DJP/CORETAX.`

### Blockers closed earlier

- Golden values from SRS §4.5 / PP 20/2026 elucidation.
- Payments / OCR / Pasal 17 / quota defaults defined in SRS; `effective_date`
  vs `as_of_date` resolved in the API.
- Snapshot versioning resolved by **D-11** (OD-6 closed).

### Residual risk

- The rubric four (OCR, Midtrans, AI, PDF) are implemented. What remains is
  Midtrans Status API confirmation, the demo script, report numbers and the
  re-measured classifier scores.
- Live Midtrans keys are a user task before demo freeze (Fri 27 Nov 2026
  18:00 Asia/Makassar) per D-10.
- Coverage gate measures **engine only** (NFR-14); whole-app coverage is
  informational.

## Parallel tracks

| Track           | Where                               | Runs                 |
| --------------- | ----------------------------------- | -------------------- |
| Docs sync       | `docs/agile/*`, API mirror          | after each milestone |
| Build           | `backend/app/`, `frontend/`         | ongoing              |
| Rubric features | OCR, AI, PDF, Midtrans (all landed) | done                 |
| Coursework      | FP, MBD, Keprof, IMK, PCD           | continuously         |

## Why payments is sequenced carefully

Payments is a lecturer requirement (D-08), so it is in scope. API v1.3.3 §5.30
defines the webhook contract, rewritten for real Midtrans. Status API
confirmation is still open.
D-10 allows building against placeholders first; live sandbox keys come before
demo freeze. Never run against production keys.

## Sprint order and why

1. **Docs and stack.** Provenance and CI first.
2. **Classification without a model.** Proves most rows classify in code.
3. **Storage and dashboard.** UI totals must equal engine snapshots.
4. **Auth hardening + versioned snapshots (M50).** Landed as PRs #1–#4.
5. **OCR + AI (shared 9router/Gemini).** Unlock receipt and fallback paths.
6. **Recap PDF, then Midtrans.** PDF is local; payments need keys + webhook.

## Rules that protect December

- The tax engine never calls a model. If a sprint tempts you to move a number
  out of `app/engine/`, refuse.
- Rates, bands, caps and KAP/KJS live in the ruleset JSON.
- Money is integer rupiah. Tax rounding is floor division by default.
- Store UTC, derive month keys with `zoneinfo` Asia/Jakarta.
- No live model calls in tests. Use the fake client.
- Sandbox gateway only. Never run anything against production keys.
- If a sprint slips, cut Should-or-lighter items (D-08 trims). Never cut the
  golden tests, the engine purity test, or the snapshot-equals-display test.
- Do not invent requirements to close an open decision.

## Risks

| Risk                           | Response                                                               |
| ------------------------------ | ---------------------------------------------------------------------- |
| SRS keeps changing             | Engine invariants are frozen. Only wording changes land.               |
| Coursework spikes mid-November | Rubric features are separable; pause costs one story.                  |
| Model cost or outage           | Heuristic path must work with the model down.                          |
| Midtrans keys late             | D-10 placeholders + test-support `paid_flag`; live keys before freeze. |
| Claiming OCR/AI/PDF done early | Mark only what has tests on `main`; see backlog.                       |

## Open decisions

See [open-decisions.md](open-decisions.md). Still open for a developer answer:
OD-3 (live KAP/KJS), OD-5 (entity-type beyond `orang_pribadi`), OD-10 (typed
decision model). OD-6 is closed by D-11.
