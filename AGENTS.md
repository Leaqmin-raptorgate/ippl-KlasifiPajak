# AGENTS.md

Instructions for coding agents working on KlasifiPajak. Read this before
changing code. `docs/STYLE.md` is the style authority; this file is the
project's rules.

## What this project is

A web app for Indonesian UMKM owners and freelancers. It classifies each income
transaction on its own, then computes PPh Final under PP 20/2026 with a
deterministic engine.

Output is a workpaper. It is not a filed return, and the app is not authorized
DJP software.

## Source of truth

`SPEC/` is the requirement source and lives **outside this repository**. Do not
commit anything from `SPEC/`, including lecturer briefs and course material.

The only SRS present in `SPEC/` is `KlasifiPajak_SRS.docx`, Document ID
`KP-SRS-001`, **version 1.0**, dated 26 Sep 2026. Its ids are `FR-1.1`–`FR-9.2`,
`NFR-Q1`–`NFR-C2`, and `UC-01`–`UC-08`.

A **v2.3 is planned and does not exist yet**. Planning notes reference ids like
`FR-17`, `FR-23a`, `UC-19a`, `UC-20`, `NFR-12` which are **not** in any committed
document. Do not cite those ids as if they were requirements. Until v2.3 lands,
cite v1.0 ids, or mark the requirement `TODO(SRS)` with its provenance.

`SPEC/KlasifiPajak/` also contains a complete set of diagrams for an unrelated
hotel reservation system. That is a reusable template from another course, not
requirements for this project. Do not read use cases, actors, or ids from it.

## Never invent requirements

Do not invent a requirement, threshold, tax figure, or expected test value.

- Golden test values come only from the developer, sourced from the PP 20/2026
  elucidation. Until supplied, write the test with the inputs and a clear
  `TODO(ELUCIDATION)`, not an invented expected number.
- If a requirement is ambiguous or a decision is open, leave a `TODO` and raise
  it. Do not decide silently.

## Invariants

These do not change without the developer saying so.

1. **Classify first, calculate second.** No tax figure is produced before its
   transaction has a category.
2. **Categories are exactly four:** `usaha`, `pekerjaan_bebas`, `already_final`,
   `non_object`.
3. **The engine never calls a language model.** `app/engine/` must not import
   FastAPI, SQLAlchemy, or any HTTP client.
4. **AI is used in exactly two places:** a fallback classifier for ambiguous
   transactions, and a read-only chat assistant that explains already-computed
   data and never calculates a number.
5. **Money is `int` rupiah.** Never a float. Confidence is `Decimal`.
6. **Rounding for tax is floor division**, covered by a test.
7. **Store UTC.** Derive month keys with `zoneinfo` `Asia/Jakarta`. Never use a
   naive `now()`.
8. **Every query is scoped by `user_id`.** Accounts are isolated.
9. **Rates, bands, caps and KAP/KJS strings live in the ruleset config**, not in
   code. A regulation change is a new `ruleset_id`.
10. **Every figure carries `ruleset_id` and a date**, plus the workpaper
    disclaimer wherever an amount is shown.
11. **Snapshots are deterministic.** Same inputs, same figures, same hash. Mark
    stale on any input change, then recompute.
12. **A model failure must never break the tax path.** On validation error,
    timeout, or exhausted quota, fall through to the clarifying question.

## Layering

Full detail in `backend/README.md`. In short:

| Layer | May do |
|---|---|
| `app/engine/` | Pure maths. No framework, no ORM, no HTTP |
| `app/classify/` | Rules, BM25, model client interface + fake |
| `app/services/` | One function per use case. Owns the transaction boundary |
| `app/api/` | Validate, call one service, return |

## Style

- 4 spaces per level. No tabs. Enforced by `.editorconfig`.
- `snake_case` for functions, modules and variables. `PascalCase` for types.
- Plain and readable. No clever abstractions, no metaprogramming.
- Docstrings on every public module, class and function. Say what it is
  responsible for, plus the `FR`/`UC`/`NFR` id when one applies.
- Code is a deliverable. A reviewer must be able to read it.
- **You wrote it, so you own it.** Read generated code before keeping it. Start
  small rather than building a large surface at once.

## Working agreements

- Run `pytest` before claiming a change works.
- Every figure shown on a screen must already have a test.
- Update `docs/agile/backlog.md` in the same change as the code it describes.
- Secrets never enter the repo. `.env` is gitignored. No real gateway keys.
- Sandbox environments only. Do not run anything against production keys.
- Do not push unless asked.

## Commands

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Docker runs the same suite:

```bash
docker compose run --rm test
```

## Open decisions

Do not resolve these yourself. They are recorded in `docs/agile/roadmap.md`.

- Entity-type field for PP 20/2026 eligibility. Verify against Pasal 56 and 57.
- Snapshot storage: overwrite, or versioned rows with an `is_current` flag.
- Paid-tier quota caps. SRS v1.0 says unlimited; planning says plafon 200.
- Quota reset period. SRS v1.0 says calendar month; a weekly reset was raised.
- Free trial period. Not in SRS v1.0.
- Whether to adopt a typed decision model behind the classifier interface.
- Test coverage target.
