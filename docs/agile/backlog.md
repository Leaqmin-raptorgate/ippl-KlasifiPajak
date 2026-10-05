# Product backlog

The tracker of record is Plane, project IPPL. This file is the readable summary,
not a second source of truth. If the two disagree, Plane wins and this file is
the thing that needs fixing.

Plane holds 116 items: 24 top-level stories and 92 sub-tasks. Every story names
its SRS v1.0 requirement ids, or is labelled `needs-decision` when the
requirement does not exist yet.

Requirement provenance matters here. The only SRS in `SPEC/` is `KP-SRS-001`
version 1.0, with `FR-1.1` to `FR-9.2`, `NFR-Q1` to `NFR-C2` and `UC-01` to
`UC-08`. Ids such as `FR-17`, `UC-20` or `NFR-12` appear in planning notes but
in no committed document, so nothing here cites them as requirements.

## Modules

| Module | Covers |
|---|---|
| Engine | FR-4.1 to FR-4.9 |
| Classification | FR-3.1 to FR-3.8, NFR-Q1 to NFR-Q3 |
| Storage | FR-1.x, FR-2.x, FR-5.x |
| Payments | Gateway, webhooks, renewal. No SRS anchor yet |
| UI | Vue 3 frontend |
| Quality | Tests, Docker, CI |
| SRS, SDD | Documentation, existing |

## Labels

`engine`, `classify`, `storage`, `payments`, `ui`, `tests`, `docker`,
`needs-decision`, `spec-v2`, plus the original `docs` and `planning`.

`needs-decision` is not decoration. Anything carrying it is waiting on the
developer, not on work.

## Sprint 1 — docs and stack

- [ ] Record the stack that already exists plus open decisions (IPPL-2)
- [ ] Polish the SRS (IPPL-3)
- [ ] Draft the SDD once the SRS feels complete
- [ ] **BLOCKER** supply the PP 20/2026 elucidation golden values for `TC-GOLDEN-*`
- [ ] **BLOCKER** write SRS v2.3 covering payments, OCR, and the missing ids

## Sprint 2 — classification without a model

- [ ] FR-3.2 heuristic-first path, zero model calls (IPPL-9)
- [ ] FR-3.3 non-object and already-final keyword table (IPPL-10)
- [ ] NFR-Q1 labeled set of at least 40 transactions (IPPL-11)
- [ ] NFR-Q2, NFR-Q3 report heuristic accuracy

## Sprint 3 — storage and dashboard

- [ ] FR-1.1, FR-1.2 profile capture and non-destructive history (IPPL-13)
- [ ] FR-2.1 manual entry with validation (IPPL-14)
- [ ] FR-2.2 uniqueness key, empty invoice number stored as NULL (IPPL-15)
- [ ] FR-5.1, FR-5.2, FR-5.4 threshold tracker, monthly summary, disclaimer (IPPL-16)

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

## Payments, no sprint yet

Held in backlog until the gateway documentation has been read. No SRS anchor:
v1.0 exclusion EX-02 removes the gateway the lecturer now requires.

- [ ] Read Midtrans Snap docs, capture a real sandbox payload
- [ ] Signature verification over raw `gross_amount`
- [ ] Reject a tampered `gross_amount`
- [ ] `GatewayAdapter` plus `FakeGatewayAdapter`
- [ ] Webhook idempotency, monotonic status, renewal arithmetic

## Quality gates

- [x] GitHub Actions CI on push and PR to `main`: pytest with a branch
  coverage gate of 80% on `backend/app/engine` (NFR-14), plus the same suite
  inside the Docker test image (`.github/workflows/ci.yml`)
- [ ] Lint job (`ruff`) — blocked on lint setup, not configured yet
- [ ] CD to CasaOS — undecided; needs a self-hosted runner or SSH deploy
  decision first

## Definition of done

See [definition-of-done.md](definition-of-done.md).
