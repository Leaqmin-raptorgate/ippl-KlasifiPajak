The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14 RFC 2119 RFC 8174 when, and only when, they appear in all capitals, as shown here.

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

## Workflow

Before a change is called done, `npm run lint` MUST report no issues and
`npm run test` MUST pass.

Edited `.py` files MUST be formatted before committing. The Husky pre-commit
hook (`.husky/pre-commit`) runs `lint` then `format:check`; it verifies, it does
not fix. Commit messages are validated by commitlint.

Agents MUST NOT edit generated or environment files: `node_modules/`, `.venv/`,
`__pycache__/`, `package-lock.json`, `.coverage`, `.ruff_cache/`,
`.pytest_cache/`. Add dependencies through `npm install` / `pip install`
instead.

## Test-driven development

Tests for a use case MUST be written or updated before implementing it. A test
that encodes a tax figure MUST cite its source (an `FR`/`UC` id or a
`TC-GOLDEN-*` case).

The author of the implementation MUST NOT modify the tests to make them pass.
If a test looks wrong, stop and report the conflict instead.

Golden cases live in `backend/tests/test_golden.py`; engine purity is enforced
by `backend/tests/test_engine.py`.

## Source of truth

`SPEC/` is the requirement source and lives **outside this repository**. Do not
commit anything from `SPEC/`, including lecturer briefs and course material.

The newest SRS is **version 2.6**, dated 18 Okt 2026, prepared by 11241050 -
Muhammad Aditya Putra. It supersedes v1.0 and v2.5. Its ids include `FR-01`
through `FR-47`, `FR-23a`, `FR-PAY-01` through `FR-PAY-09`, `NFR-01`
through `NFR-14`, and `UC-01` through `UC-26`.

> **Provenance.** SRS v2.6 now lives on disk at
> `SPEC/KlasifiPajak/KlasifiPajak_SRS.md`. The HTTP contract is
> `SPEC/KlasifiPajak/KlasifiPajak_API_Specification.md` v1.2.2 and the schema is
> `SPEC/KlasifiPajak/KlasifiPajak_ERD.md` v1.2.2, both dated 18 Okt 2026. Do not
> add `TODO(SRS-COMMIT)` markers any more; every id cited here has a source of
> record.

Ids such as `FR-17`, `FR-23a`, `UC-19a`, `UC-20`, `NFR-12` and `NFR-13` are
defined in v2.6. Do not treat them as invented.

`effective_date` and `as_of_date` are both real and distinct. **`effective_date`**
is the ruleset's promulgation stamp (`Ruleset.effective_date`, served by
`GET /ruleset`, copied into snapshots and events). **`as_of_date`** is the
calculation cutoff (`Snapshot.as_of_date`, the request field on
`POST /snapshot`, today in `Asia/Jakarta` on Bagian B). This closes OD-1 in
`docs/agile/open-decisions.md`.

`SPEC/KlasifiPajak/` also contains a complete set of diagrams for an unrelated
hotel reservation system (`SD-01_-_Memesan_Kamar.json` and neighbours). That is
a reusable template from another course, not requirements for this project. Do
not read use cases, actors, or ids from it.

## Never invent requirements

Do not invent a requirement, threshold, tax figure, or expected test value.

- Golden test values come only from the developer, sourced from the PP 20/2026
  elucidation or PMK 164/2023 Lampiran B. **SRS v2.6 §4.5 supplies explicit
  inputs and expectations for every `TC-GOLDEN-*` case**, so those figures are
  sourced, not invented. Anything outside that table still needs a
  `TODO(ELUCIDATION)` rather than a guessed number.
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
13. **The database is tiered and the tier is never skipped.** API → stored
    procedure → view / function → table. Full rules in
    [SQL database rules](#sql-database-rules). **Recorded deviation (18 Okt
    2026):** the first storage slice (`app/models/`, `app/services/`) uses
    SQLAlchemy 2.0 with one session per request instead of the procedure tier.
    It is the only accepted deviation and it is temporary; new storage work
    SHOULD move one use case at a time onto the procedure tier rather than
    adding more direct ORM paths.
14. **The spouse switches are ruleset data, never code.** `spouse_in_band` and
    `spouse_in_cap` are read from the ruleset (`TC-GOLDEN-PASAL58-PARAM-BAND`
    requires flipping them without a code change). Default per PMK 164/2023
    Lampiran B: `spouse_in_band: false`, `spouse_in_cap: true`.
15. **Marital status and Pasal 58 aggregation are different fields.** FR-03
    records status as `yes` / `no` / `unknown`; FR-21 and UC-13b record
    `agregasi_pasal_58` as its own boolean. Never derive one from the other.
16. **Over-withholding is surfaced, never carried forward.** `sisa_bayar_idr`
    and `overwithheld_excess_idr` are both `>= 0`. Excess is reported as
    _belum diperhitungkan_ with a note to consult a licensed consultant
    (FR-23), never moved between months and never treated as a credit.
17. **`input_hash` is `v1:<sha256_hex>`** over Canonical JSON, per month, and
    excludes `computed_at` and snapshot ids (FR-22, NFR-02).

## Layering

Full detail in `backend/README.md`. In short:

| Layer           | May do                                                   |
| --------------- | -------------------------------------------------------- |
| `app/engine/`   | Pure maths. No framework, no ORM, no HTTP                |
| `app/classify/` | Rules, BM25, model client interface + fake               |
| `app/services/` | One function per use case. Owns the transaction boundary |
| `app/api/`      | Validate, call one service, return                       |

Inside a service, the only SQL that runs is `CALL`. A service no longer builds a
query with the ORM; it calls the procedure that owns the use case. The Python
layering in `backend/README.md` is unchanged — this only replaces what the
service's session executes.

## SQL database rules

MySQL. A base table is the **only** thing that stores data, and it is the only
thing nothing else is allowed to name directly.

The call direction is fixed, and every arrow points one way:

```
API endpoint ──CALL──▶ stored procedure ──┬──▶ stored view  ──┐
                                          ├──▶ stored function ─┼──▶ base table
                                          └──▶ updatable view ──┘        │
                                                         ▲               │
                                         trigger (BEFORE INSERT/UPDATE sets NEW)
```

| Tier             | MUST                                                                             | MUST NOT                                               |
| ---------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------ |
| API endpoint     | call one stored procedure                                                        | `SELECT`, or any query against a table or a view       |
| Stored procedure | call stored views and stored functions, and write through updatable views        | name a base table in any statement                     |
| Stored function  | return exactly one value                                                         | write, or be called from inside a view or a trigger    |
| View             | project a read, and be updatable where a procedure needs to write through it     | hold logic, aggregate into a figure, or call a trigger |
| Trigger          | execute mechanical work for its own row, such as stamping a UTC column via `NEW` | validate, reject, compute, `SELECT`, or write again    |
| Base table       | store rows, enforce constraints                                                  | be named by any tier above                             |

Seven rules follow from that table.

1. **A procedure calls a function.** Not the reverse. A function is a leaf that
   answers one question and hands back a value.
2. **A procedure calls a view.** Every read inside a procedure is a view or a
   function, never a base table.
3. **An API endpoint points at a procedure, never at a `SELECT`.** No route and
   no service function runs a query. The endpoint is `CALL`, then return.
4. **Inside a procedure there is no direct table call.** Reads go through views
   and functions; writes go through the updatable view for that table.
5. **A trigger only executes mechanical work for its own row.** Setting a UTC
   column through `NEW` is the model: one assignment, no branches. It may never
   check, validate, reject, derive, or issue a second statement against the
   table that fired it. If a row needs validating, rejecting, or deriving, that
   belongs in the procedure, before the write reaches the trigger. A trigger
   that `SELECT`s to validate, or that `UPDATE`s its own table, is a bug.
6. **A stored function returns a value.** Use one for a lookup, a derived
   amount, or a rule that both a view and a procedure need. A function that
   returns nothing is a procedure.
7. **The stored procedures are where the syntaxes execute.** Every `CALL`,
   every `INSERT` / `UPDATE` / `DELETE`, every `SELECT ... INTO`, every
   transaction control statement sits inside a procedure body. Nothing above the
   procedure tier executes SQL syntax of its own.

### Syntax

```sql
DELIMITER $$

-- 6. a function returns exactly one value
CREATE FUNCTION fn_next_taxable_amount(p_ruleset_id CHAR(36), p_category VARCHAR(32))
RETURNS BIGINT
READS SQL DATA
BEGIN
    DECLARE v_amount BIGINT;

    -- 1. a function reads through a view, never a base table
    SELECT COALESCE(SUM(r.taxable_amount), 0)
      INTO v_amount
      FROM vw_taxable_income AS r
     WHERE r.ruleset_id = p_ruleset_id
       AND r.category = p_category;

    RETURN v_amount;
END$$

-- 2, 4, 7. a procedure calls functions and views, and executes the syntaxes
CREATE PROCEDURE sp_record_transaction(
    IN p_user_id CHAR(36),
    IN p_category VARCHAR(32),
    IN p_amount BIGINT,
    IN p_ruleset_id CHAR(36)
)
BEGIN
    DECLARE v_taxable BIGINT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    -- 2. read via a view and a function
    SELECT fn_next_taxable_amount(p_ruleset_id, p_category) INTO v_taxable;

    -- 4. write through the updatable view, never the base table
    INSERT INTO vw_transaction_ledger (user_id, category, amount, ruleset_id)
    VALUES (p_user_id, p_category, p_amount, p_ruleset_id);

    COMMIT;
END$$

-- 5. a trigger only executes the stamp for its own row, and never checks
CREATE TRIGGER trg_transaction_ledger_stamp
BEFORE INSERT ON transactions
FOR EACH ROW
BEGIN
    -- ok: one mechanical assignment to the incoming row
    SET NEW.stamped_at = UTC_TIMESTAMP(6);

    -- forbidden: SELECT, validation, or a second UPDATE against transactions
END$$
```

Naming is fixed so a reviewer can tell the tier from the name alone.

| Object    | Prefix | Example                        |
| --------- | ------ | ------------------------------ |
| Procedure | `sp_`  | `sp_record_transaction`        |
| Function  | `fn_`  | `fn_next_taxable_amount`       |
| View      | `vw_`  | `vw_transaction_ledger`        |
| Trigger   | `trg_` | `trg_transaction_ledger_stamp` |

- One file per object under `backend/alembic/versions/`, named after the object,
  so a reviewer can read one tier without reading the rest.
- Every object carries a docstring comment naming the `FR` / `UC` id it serves,
  per [Style](#style).
- A procedure takes `user_id` as its first parameter and filters by it in every
  statement. Invariant 8 applies inside MySQL, not just in Python.
- Adding a tier is a schema decision. If a rule above cannot be met without one,
  stop and raise it rather than reaching around it.

## Source files

Source files (code, tests, OpenAPI documents, manifests, config, etc.) SHOULD
NOT contain transient information, such as roadmap or sprint notes, Plane item
keys (IPPL-xx), or references to documentation files and their section numbers.
That context belongs in commits, PRs, and the docs themselves.

Stable requirement ids (`FR-xx`, `UC-xx`, `NFR-xx`, `TC-GOLDEN-*`) are not
transient: they are the identifiers this repo requires in docstrings and test
names. Cite them.

Docstrings and test names SHOULD describe behavior and contract: inputs,
outputs, side effects, errors, and non-obvious reasons that stay true as long
as the code does. Glossary code names (`Ruleset`, `Snapshot`, `usaha`) are fine.

Rule of thumb: if it would go stale when a Plane item closes or a doc is
renumbered, it doesn't belong in source.

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

## Principles

Agents SHOULD do the simplest thing that satisfies the request. If something
extra seems needed, agents MUST ask first instead of adding it.

The database enforces structural integrity only: NOT NULL, UNIQUE, foreign keys,
simple value ranges, and enum-style CHECKs. Business rules live in application
code.

- Clarity: clarity is better than cleverness.
- Separation: separate policy from mechanism.
- Simplicity: design for simplicity; add complexity only where you must.
- Transparency: design for visibility to make inspection and debugging easier.
- Robustness: robustness is the child of transparency and simplicity.
- Representation: fold knowledge into data, so program logic can be stupid and
  robust.
- Silence: when a program has nothing surprising to say, it should say nothing.
- Repair: repair what you can, but when you must fail, fail noisily and as soon
  as possible.
- Optimization: prototype before polishing. Get it working before you optimize
  it.
- Make common mistakes hard, and make rare mistakes recoverable.

These principles SHOULD guide every design decision. Deviating from one
requires a stated reason.

## Git Conventions

- Atomic commits/PRs — one logical change, nothing unrelated bundled in.
- Branch naming: `<type>/<short-kebab-description>` (e.g. `feat/classify-rules`),
  where `<type>` matches Conventional Commits types.
- Commit message format:
  ```
  <type>[optional scope]: <description>

  [optional body]

  [optional footer(s)]
  ```
  - Blank line REQUIRED before body (if present) and before footer(s) (if present).
  - `<type>` MUST be one of: `build`, `chore`, `ci`, `docs`, `feat`, `fix`,
    `perf`, `refactor`, `revert`, `style`, `test`.
  - `body-max-line-length` is disabled (per `commitlint.config.js`).

## Commands

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # requirements.txt plus ruff

npm ci   # ALWAYS npm ci, never npm install (lockfile-locked)
```

npm scripts (Node is dev tooling only, never runtime):

| Task                        | Command                 |
| --------------------------- | ----------------------- |
| Run tests                   | `npm run test`          |
| Tests with coverage gate    | `npm run test:coverage` |
| Run ruff lint               | `npm run lint`          |
| Fix ruff lint issues        | `npm run lint:fix`      |
| Fix Python + doc formatting | `npm run format`        |
| Check formatting (both)     | `npm run format:check`  |

Docker runs the same suite:

```bash
docker compose run --rm test
```

### Pre-commit gates (all MUST pass)

`.husky/pre-commit` runs in order: `lint`, `format:check`. Quick fix before committing:

```bash
npm run lint:fix && npm run format
```

Commit messages are validated by commitlint (`.husky/commit-msg`, Conventional
Commits). CI (`.github/workflows/ci.yml`) runs the same checks first, then the
pytest suite with the 80% branch coverage gate (NFR-14) and the Docker test
image.

## Project docs

- `docs/SPEC.md` is the requirement source. It is the only place requirements
  live; agents MUST read the relevant section before planning any feature.
  This repo has no `docs/SPEC.md` — the SRS is `SPEC/KlasifiPajak/` outside the
  repository, currently v2.6 (see [Source of truth](#source-of-truth)).
- `docs/ARCHITECTURE.md` describes how the backend is built. This repo has no
  `docs/ARCHITECTURE.md`; the layering is in `backend/README.md` and summarised
  in [Layering](#layering) above.
- `README.md` is for humans. It MUST NOT be treated as a source of requirements.
- `docs/REVIEW.md` is what code review flags and at what severity. See
  [Code review](#code-review) below.
- `docs/sql_syntaxes/` is the readable SQL reference for the procedure,
  function, view, trigger, access, and optimization tiers. Production objects
  still live one per file under `backend/alembic/versions/`.

## Keeping docs accurate

Agents maintain the project docs (`README.md`, `AGENTS.md`, `docs/STYLE.md`,
`docs/agile/*`, `docs/api/*`). Every change to them MUST be decided in Plan mode.
Docs MUST be kept in sync with the code in the same PR, not in a follow-up.

When a task changes what a doc describes, the plan MUST include the exact edits
to that doc. They MUST be applied only after the plan is approved, in the same
change as the code.

If code and a doc disagree during implementation, or a doc is silent on something
needed: agents MUST stop. Agents MUST NOT guess, and MUST NOT edit the doc to
match the code. They MUST return to Plan mode and describe the conflict.

`README.md` is exempt from Plan mode: agents MAY fix or update it directly, but
the change MUST still be in the same PR as the code it describes.

## Code review

When reviewing code, agents MUST follow `docs/REVIEW.md`, including its severity
definitions and nit cap.

A review only reports findings. The reviewer MUST NOT edit code, push, or apply
fixes unless explicitly told to (e.g. `/code-review --fix`).

When explicitly asked to act on review findings, agents MAY decline a Nit, and
MUST NOT add complexity only to satisfy one.

## CI

`.github/workflows/ci.yml` runs on every push and pull request to `main`:

- **Lint & format**: ruff (`npm run lint`) and ruff format + Prettier
  (`npm run format:check`).
- **Tests**: the pytest suite with the 80% branch coverage gate on the engine
  (NFR-14), and the same suite inside the Docker test image.

The test job only runs once the lint job passes. The workflow does not publish
or deploy anything.

## Vocabulary

Code: identifiers MUST be English only, using the glossary in the SRS, in
`snake_case` for attributes and functions, `PascalCase` for classes and types,
and `UPPER_SNAKE_CASE` for enum members. On the wire, JSON fields are
`snake_case` and enum values are the code names (`usaha`, `pekerjaan_bebas`,
`already_final`, `non_object`).

Writing: em-dashes MUST NOT be used in docs written for humans (`README.md`),
code comments, commits, or PRs. Docs written for agents (`AGENTS.md`,
`docs/REVIEW.md`, `docs/STYLE.md`, `docs/api/`) MAY use them.

Markdown docs: domain terms SHOULD use the format Original term (English term),
e.g. Peredaran bruto (gross turnover), when the Indonesian term is the one in
the SRS.

API messages: MUST be English. Every error MUST carry an error code. The
frontend keys its Indonesian text on the code, so a released code MUST NOT be
renamed, removed, or change meaning. The response shape is `{code, field,
message}`; the full code list is not yet ratified.

Commits, PRs and issue references: MUST be in English, and SHOULD cite ids
(`UC-05`, `FR-13`, `IPPL-22`) where relevant.

## Boundaries

The backend owns every business rule and the API contract. The Vue 3 frontend
lives in this repository's `frontend/` directory and only renders what the API
returns. A rule that is not enforced in `backend/` is not enforced anywhere.

The OpenAPI document FastAPI generates from this code is the API contract. A
breaking change (a removed or renamed path, field, enum value or error code, or
a changed type) MUST be raised in Plan mode and released together with an
updated `docs/api/KlasifiPajak_API_Specification.md`.

App internals (screens, widgets, accessibility) MUST NOT be documented in this
repo. What the app needs is stated in `docs/api/KlasifiPajak_API_Specification.md`
and the contract.

## Open decisions

Do not resolve these yourself. They are recorded in `docs/agile/roadmap.md`.

- Entity-type field for PP 20/2026 eligibility. Verify against Pasal 56 and 57.
- Snapshot storage: overwrite, or versioned rows with an `is_current` flag.
- Paid-tier quota caps. SRS v1.0 says unlimited; planning says plafon 200.
- Quota reset period. SRS v1.0 says calendar month; a weekly reset was raised.
- Free trial period. Not in SRS v1.0.
- Whether to adopt a typed decision model behind the classifier interface.
- Test coverage target.
