# Implementation roadmap

Goal: working demo before December. Optimize for finishing, not for completeness.

Tracking lives in Plane, project IPPL. This file explains the sequence and the
reasoning; Plane holds the items.

## Current state (5 Oct 2026)

Done:

- Tax engine at the specified architecture path, `backend/app/engine/`, pure
  Python, no framework, no model.
- Ruleset as data at `backend/app/engine/ruleset/pp20_2026.json`.
- 18 passing pytest tests, runnable on the host or in Docker.
- Sprint structure in Plane: 5 cycles, 6 modules, 9 labels, 24 stories,
  92 sub-tasks.

Not started: classification, storage, UI, AI, payments.

Two blockers sit in Sprint 1 and both need the developer, not more code:

1. **Golden values.** SRS v1.0 NFR-T1 wants every worked example from the PP
   20/2026 elucidation as a golden test. No elucidation figures have been
   supplied. The eight `TC-GOLDEN-*` cases currently assert numbers derived
   from the SRS appendix, which is not the same thing, so they must become
   `TODO(ELUCIDATION)` stubs. Until then, golden coverage is zero and only
   invariant tests remain.
2. **SRS v2.3.** Planning notes cite `FR-17` to `FR-23a`, `FR-44`, `UC-19a`,
   `UC-20`, `UC-23`, `NFR-04`, `NFR-12`, `NFR-13`. None exist in a committed
   document. v2.3 has to define payments, OCR, the Pasal 17 question, paid
   quota caps, the `input_hash` field list, and the `effective_date` versus
   `as_of_date` naming.

## Parallel tracks

| Track | Where | Runs |
|---|---|---|
| Docs | SRS v2.3, SDD, Plane SRS/SDD modules | Sprint 1 |
| Build | `backend/app/`, `frontend/` | Sprints 2 to 5 |
| Payments | `backend/app/payments/` | after gateway docs |
| Coursework | FP, MBD, Keprof, IMK, PCD | continuously |

Do not start a new IPPL story while a sprint is unfinished.

## Why payments is not in a sprint

Payments is a lecturer requirement, so it is in scope. It is also the largest
single item and the only one with no requirement to code against. Building it
before the gateway documentation is read means guessing field names, which
fails at runtime against a real gateway. The signature rule and the amount
comparison are pure logic and could start earlier, but sequencing them ahead of
the docs risks encoding a wrong assumption into a test that then looks correct.

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

| Risk | Response |
|---|---|
| SRS keeps changing | Engine invariants are frozen. Only wording changes land. |
| Coursework spikes mid-November | Sprints 2 to 4 are independent. A paused sprint costs one story. |
| Elucidation values never arrive | Engine ships with invariant tests only. Say so in the report rather than implying golden coverage. |
| Model cost or outage | Heuristic path must work with the model down. |
| Payments guesswork | Do not code the adapter before the docs are read. |
| Scope creep into chat, OCR, export | Stretch list only, cut first. |

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
