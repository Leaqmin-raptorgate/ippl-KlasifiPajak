# Layering rules

Read this before adding a file. The boundary that matters most is the first one.

## `app/engine/` — pure Python

Owns the tax maths: rate application, exemption band, eligibility caps, Pasal 58
thresholds, snapshot hashing.

Must not import FastAPI, SQLAlchemy, or any HTTP client. Tests for this package
run offline. `backend/tests/test_engine.py` scans the source to enforce it.

A language model never runs here, and no code outside this package may compute
a tax figure.

## `app/ruleset/` is inside `app/engine/ruleset/`

Rates, bands, caps and KAP/KJS strings are data, not literals, so a regulation
change becomes a new `ruleset_id` instead of a code edit. Kept next to the engine
so a figure and the data that produced it are read together.

## `app/classify/`

Rules layer, in-memory BM25 over `regulation_chunks`, and the model client
interface with a fake implementation for tests.

The pipeline order is fixed: rules first, then model fallback, then one
clarifying question to the user.

## `app/services/`

One function per use case. A service owns the transaction boundary: it opens the
session, does the work, commits or rolls back, and returns plain data.

This is the only layer allowed to both read and write. If a route needs a new
query, add a service function rather than reaching into the ORM from the route.

## `app/api/`

Thin routes. Validate input, call one service, return. No queries, no
calculations, no business rules.

## `app/models/` and `app/schemas/`

`models` is SQLAlchemy 2.0 table definitions and migrations source of truth.
`schemas` is Pydantic request and response shapes.

Every query is scoped by `user_id`. Account isolation is a requirement, not a
convention.

## `app/payments/`

Gateway adapter interface plus the implementations. Services depend on the
interface, never on a concrete gateway.

## `app/config/`

Environment-derived settings. Thresholds and quotas live here because they are
configurable; tax rates and bands do not, because they belong to the ruleset.

## Not yet built

These directories are placeholders with a stated purpose, not empty ceremony.
Nothing in them is required for the engine to work.

| Directory                     | Lands when                                         |
| ----------------------------- | -------------------------------------------------- |
| `app/classify/`               | Sprint 2, keyword table and accuracy report        |
| `app/models/`, `app/schemas/` | Sprint 3, storage                                  |
| `app/services/`, `app/api/`   | Sprint 3, first real endpoint                      |
| `app/payments/`               | Payment work, once the gateway interface is agreed |
| `app/config/`                 | Sprint 2, threshold and quota settings             |
| `backend/alembic/`            | Sprint 3, first migration                          |
| `backend/tests/data/`         | Sprint 2, labeled classification set               |
| `frontend/`                   | After the backend serves real numbers              |
| `nginx/`                      | Deploy time. Only service with a published port    |
