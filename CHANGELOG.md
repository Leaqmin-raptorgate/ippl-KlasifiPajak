# Changelog

All notable changes to KlasifiPajak are listed here, newest first. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
version numbers follow [Semantic Versioning](https://semver.org/) as described
in [CONTRIBUTING.md](CONTRIBUTING.md#releases-and-versioning).

The project is below 1.0.0, so a minor version may change the API contract or
stored data, and a patch version only fixes. Each release names the contract
documents it was built against: the SRS, the API specification
(`docs/api/KlasifiPajak_API_Specification.md`) and the ERD.

## [Unreleased]

Contract: API v1.3.3.

### Documentation

- Align the API specification, README, backend README, backlog, roadmap and
  open decisions with the landed stack: the OCR, Midtrans, AI and recap
  features exist, the recap and webhook contracts are fully described,
  `PAYLOAD_TOO_LARGE`, `INVALID_ORDER_AMOUNT`, `PAYMENT_GATEWAY_UNAVAILABLE` and
  `VALIDATION_ERROR` are documented, and OD-13 records the open Pasal 58(1)(a)
  question.

## [0.5.0] - 2026-11-07

Contract: SRS v2.7 (FR-20 and FR-22 superseded until SRS v2.8), API v1.3.2, ERD r3.

### Changed

- **Breaking:** a month's `input_hash` is now `v2:` and covers the combined
  gross and usaha omzet of the months before it (`carry_forward`). An
  unchanged hash now means unchanged figures. Stored `v1:` hashes never match,
  so a month is rewritten the next time a write reaches it (FR-22).
- `next_year_ineligible` on a stored month is cumulative through that month.
  The Bagian A top-level field keeps its whole-period meaning (FR-20).
- Every transaction write (create, clarify, edit, delete, override,
  reclassify) checks January through the Jakarta `as_of` month. A row whose
  date arrived since the last write is picked up, and months whose hash is
  unchanged keep their version (FR-08, FR-09, FR-23a).

### Fixed

- Editing, moving or deleting a transaction no longer leaves wrong tax in
  later months (D1). Moving Rp 200 juta from October to March used to understate
  tax by Rp 500.000, and deleting a row overstated it (PR #11).
- A write that waited on the profile lock could rebuild snapshots from a stale
  read view and overwrite a concurrent write's correct figures. The rebuild now
  reads transaction rows with a locking read (PR #11).

### Documentation

- API specification v1.3.2 (unreleased in the SRS), with the `v2:` hash format
  and a new normative digest.

## [0.4.0] - 2026-11-03

Contract: SRS v2.7, API v1.3.1, ERD r3.

### Added

- Frontend unit tests with Vitest, including the transaction-edit cases, and an
  `npm audit` gate in CI (PR #7).
- Per-field 422 errors mapped from `field_errors` onto the forms, a
  409 `VERSION_CONFLICT` reload that shows the API message first, and a guard
  against saving into an unmounted page (PR #8).
- Legal-basis copy in one shared module, quoted from SRS v2.7 (PR #8).

### Changed

- Transaction edit is wired to the API, and several UX and state-handling
  defects are fixed (PR #6).
- Repository docs are synced to SRS v2.7, API v1.3.1 and ERD r3 after the M50
  work (PR #5).

### Fixed

- Production now rejects the `.env.example` JWT placeholder and any secret that
  starts with `CHANGE_ME`. Development and test still accept it (HB-01, PR #9).
- Statutory citations in the legal-basis text corrected, and the backlog
  updated (PR #10).

## [0.3.0] - 2026-11-02

Contract: SRS v2.7, API v1.3.1, ERD r3. Milestone M50.

### Added

- Alembic migrations with an ERD r3 baseline. The schema is created only
  through migrations, never `create_all` at runtime. A one-shot `migrate`
  service runs before the API, with separate migrate and runtime database users
  (PR #1).
- Versioned `month_snapshots` (D-11): a change marks the current `berlaku` row
  `usang` and inserts `version + 1`. Reads show `berlaku` rows only (PR #1,
  PR #4).
- Transaction edit, delete, category override and reclassify-all, with a
  classification audit trail and monthly trace (FR-16a, FR-47). Edits use
  optimistic concurrency and return 409 `VERSION_CONFLICT` on a stale
  `version`. Lock order is profile, transaction, snapshots (PR #4).
- Monthly quota counters: free accounts get 10 AI classifications and 15
  assistant chats, paid accounts 200 of each (PR #4).
- Auth hardening: argon2id passwords with rehash from the legacy format, rate
  limits on login, register and reset, password reset, session list and revoke,
  and account delete with confirmation (HB-02 to HB-06, PR #3).
- Provisional transaction clarification flow and UI capability gating.
- CI gates: frontend build, `pip-audit` that fails closed on high and critical
  findings, and `gitleaks` (PR #2).
- A five-step API demo smoke test: register, profile, transaction, dashboard
  with the workpaper disclaimer, logout (HB-27).

### Changed

- Containers run as a non-root user with a `/health` check (HB-21).
- `transactions` uniqueness is null-safe, text columns are `utf8mb4_bin`, and
  timestamps are `DATETIME(6)` (ERD r3).

### Fixed

- Lost update on transaction edit (API §5.12): a conditional update on
  `version` replaces a read-then-write.
- Snapshot writes are race safe and no longer deadlock against profile writes.

## [0.2.0] - 2026-10-19

### Added

- Authenticated API with sessions, register and login.
- Demo accounts and a SQL reference.
- Profile, transaction and dashboard endpoints on the deterministic Final PPh
  engine, with the 0,5% rate, the Rp 500 juta free band and the Rp 4,8 miliar
  eligibility cap in a versioned ruleset file.
- Keyword classifier that sends an unrecognized row to a clarification question.

## [0.1.0] - 2026-10-05

### Added

- Project scaffold: FastAPI backend, Vue 3 frontend, pure Python tax engine.
- GitHub Actions test workflow with an 80% engine coverage gate, and lint and
  format gates.
- Conventional commits (commitlint), Husky hooks, Ruff and Prettier.
- Contributing guide, security policy and issue templates.

[Unreleased]: https://github.com/Leaqmin-raptorgate/ippl-KlasifiPajak/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/Leaqmin-raptorgate/ippl-KlasifiPajak/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Leaqmin-raptorgate/ippl-KlasifiPajak/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Leaqmin-raptorgate/ippl-KlasifiPajak/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Leaqmin-raptorgate/ippl-KlasifiPajak/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Leaqmin-raptorgate/ippl-KlasifiPajak/releases/tag/v0.1.0
