# Implementation roadmap

Goal: working demo before December. Optimize for finishing, not for completeness.

Tracking lives in Plane, project IPPL. This file explains the sequence and the
reasoning; Plane holds the items.

## Current state (18 Okt 2026)

Done:

- Tax engine at the specified architecture path, `backend/app/engine/`, pure
  Python, no framework, no model.
- Ruleset as data at `backend/app/engine/ruleset/pp20_2026.json`, now carrying
  `tax_year` and `effective_date`.
- **SRS v2.6, ERD v1.2.2, and API v1.2.2 are on disk under
  `SPEC/KlasifiPajak/`.** Both Sprint 1 provenance blockers are closed.
- **Bagian A is aligned to API v1.2.2.** `/health` returns only
  `{"status": "ok"}`, `/ruleset` speaks the contract field names, and
  `POST /snapshot` emits the section 3.3 shape. The January digest equals the
  document's normative vector.
- **First storage slice (12 of 39 endpoints, about 31%).** Register, login,
  logout, `GET /auth/me`, profile GET/PUT, transaction list/create with keyword
  classification, and the dashboard read from stored snapshots.
- MySQL 8 service in `docker-compose.yml`, for the API and the test suite.
  `nginx/` is removed because ingress lives in the deployment container.

Not started: OCR, clarification/override, transaction edit/delete, recap/PDF,
assistant, quotas, payments, frontend wiring.

### Recorded deviations

- Storage uses SQLAlchemy 2.0, not the stored-procedure tier of invariant 13.
  Recorded in `AGENTS.md`; move one use case at a time onto the tier.
- Tables are created with `Base.metadata.create_all` for the slice. The first
  Alembic revision is still pending.
- The classifier is the keyword table only. A miss is stored as provisional
  `usaha` with `requires_clarification`; no model call in this slice.

### Blocker — golden values — **CLOSED**

SRS v2.6 §4.5 supplies an explicit table of inputs and expectations for every
`TC-GOLDEN-*` case, with provenance from the PP 20/2026 elucidation and PMK
164/2023 Lampiran B.

### Blocker — SRS definition gaps — **CLOSED**

v2.6 defines payments (FR-PAY-01 to -09), OCR (FR-06), the Pasal 17 question
(excluded, §1.3), paid quota caps (FR-43), and the exact `input_hash` field list
(FR-22). `effective_date` versus `as_of_date` is resolved by API v1.2.2: the
stamp and the cutoff are different fields.

### Residual risk

The stored-procedure tier is still absent. Every query currently runs through
SQLAlchemy in `app/services/`; that is the deviation to retire before the
database rules can be called satisfied.

## Parallel tracks

| Track      | Where                                | Runs               |
| ---------- | ------------------------------------ | ------------------ |
| Docs       | SRS v2.6, SDD, Plane SRS/SDD modules | Sprint 1           |
| Build      | `backend/app/`, `frontend/`          | Sprints 2 to 5     |
| Payments   | `backend/app/payments/`              | after gateway docs |
| Coursework | FP, MBD, Keprof, IMK, PCD            | continuously       |

Do not start a new IPPL story while a sprint is unfinished.

## Why payments is not in a sprint

Payments is a lecturer requirement, so it is in scope. It is also the largest
single item. API v1.2.2 now fixes the webhook contract (HMAC-SHA256 over
`order_id`, status, and `amount_str`), so the guessing risk is gone; the item is
still sequenced last because it is the biggest surface and the demo does not
depend on it. Never run anything against production keys.

## Sprint order and why

1. **Docs and stack.** Week one is deliberately documentation. Coursework peaks
   in mid-November, and a docs-only sprint costs nothing when it has to be
   interrupted.
2. **Classification without a model.** Proves the core claim of the product:
   most rows are classifiable in code. If this sprint shows weak accuracy, that
   is information worth having before the UI is built.
3. **Storage and dashboard.** First real user-facing surface. Acceptance is
   that displayed totals equal the engine snapshot field by field, which is the
   test that proves the UI is a view rather than a second calculation.
4. **AI fallback.** Added only after rules work. The model is a fallback, and
   building it earlier hides whether the rules are good enough.
5. **Trace and demo.** A reviewer must be able to trace any figure on screen to
   a test. Chat and PDF are stretch and are cut first if time runs short.

## Rules that protect December

- The tax engine never calls a model. If a sprint tempts you to move a number
  out of `app/engine/`, refuse.
- Rates, bands, caps and KAP/KJS live in the ruleset JSON. A regulation change
  is a new `ruleset_id`, not a code edit.
- Money is integer rupiah. Tax rounding is floor division.
- Store UTC, derive month keys with `zoneinfo` Asia/Jakarta.
- No live model calls in tests. Use the fake client.
- Sandbox gateway only. Never run anything against production keys.
- Commit at the end of each sprint with a message that says why.
- If a sprint slips, cut from the stretch list. Never cut the golden tests, the
  engine purity test, or the snapshot-equals-display test.

## Risks

| Risk                               | Response                                                                                           |
| ---------------------------------- | -------------------------------------------------------------------------------------------------- |
| SRS keeps changing                 | Engine invariants are frozen. Only wording changes land.                                           |
| Coursework spikes mid-November     | Sprints 2 to 4 are independent. A paused sprint costs one story.                                   |
| Elucidation values never arrive    | Engine ships with invariant tests only. Say so in the report rather than implying golden coverage. |
| Model cost or outage               | Heuristic path must work with the model down.                                                      |
| Payments guesswork                 | Do not code the adapter before the docs are read.                                                  |
| Scope creep into chat, OCR, export | Stretch list only, cut first.                                                                      |

## Open decisions

Recorded rather than decided. Each has a `needs-decision` item in Plane.

- Entity-type field for PP 20/2026 eligibility. Verify against Pasal 56 and 57.
- Snapshot storage: overwrite, or versioned rows with an `is_current` flag.
- Paid-tier quota caps. SRS v1.0 section 2.7 says unlimited; planning says
  plafon 200 and 200.
- Quota reset period. SRS v1.0 says calendar month; a weekly reset was raised.
- Free trial period. Not in SRS v1.0.
- Whether to adopt a typed decision model behind the classifier interface.
- Test coverage target.
