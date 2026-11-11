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

Rules/keyword path runs on transaction create. BM25 retrieval
(`classify/bm25.py`) and the OpenAI-compatible model client
(`classify/model_client.py`, D-09 / 9router) are built. Pipeline order: rules
first, then model fallback, then one clarifying question.

## `app/services/`

One function per use case. A service owns the transaction boundary: it opens the
session, does the work, commits or rolls back, and returns plain data.

This is the only layer allowed to both read and write. If a route needs a new
query, add a service function rather than reaching into the ORM from the route.

## `app/api/`

Thin routes. Validate input, call one service, return. No queries, no
calculations, no business rules. Auth hardening (PR #3) and tax CRUD (PR #4)
live in `routes_app.py`; §5.32 test-support mounts only when `APP_ENV=test`.

## `app/models/` and `app/schemas/`

`models` is SQLAlchemy 2.0 table definitions aligned with **ERD r3** (including
`month_snapshots.version` and auth tables). `schemas` is Pydantic request and
response shapes.

Every query is scoped by `user_id`. Account isolation is a requirement, not a
convention.

Schema changes go through **Alembic** (`backend/alembic/`), applied by the
compose `migrate` service as `klasifipajak_migrate`. The API process uses the
DML-only `klasifipajak_app` user and must not call `create_all` for schema.

## `app/payments/`

Gateway adapter interface plus `MidtransAdapter` (`payments/adapter.py`).
Services depend on the interface, not on a concrete gateway. Live keys are
still placeholders (D-10); use sandbox keys.

## `app/config/`

Environment-derived settings currently read by the API process: `APP_ENV`,
`DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`, `RULESET_PATH`, plus
`TRUSTED_PROXY_IPS` / `TRUSTED_PROXY_COUNT` (read in the auth routes).
`MIGRATE_DATABASE_URL` is used by Alembic (`backend/alembic/env.py`), not by
`Settings`. AI (`AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL_*`, `AI_TIMEOUT_S`) is
read by `Settings` and the OCR, classifier, and assistant clients (D-09).
Midtrans `MIDTRANS_SERVER_KEY` and `MIDTRANS_IS_PRODUCTION` are read by
`services/payments.py` (D-10). `MIDTRANS_CLIENT_KEY` is only in `.env.example`
and is not read. Thresholds and quotas that are product-configurable live here;
tax rates and bands do not.

## Status vs empty placeholders

| Directory                                                  | Status on main (2026-11-03)                           |
| ---------------------------------------------------------- | ----------------------------------------------------- |
| `app/engine/`, `app/engine/ruleset/`                       | Done                                                  |
| `app/models/`, `app/schemas/`, `app/services/`, `app/api/` | Done (M50)                                            |
| `app/config/`                                              | Done                                                  |
| `backend/alembic/`                                         | Done — initial head = ERD r3 / D-11                   |
| `app/classify/`                                            | Rules, BM25 and the model client                      |
| `app/payments/`                                            | `MidtransAdapter`; Status API confirmation still open |
| OCR / receipt bytes / PDF export                           | Built (`routes_receipts.py`, `services/recap.py`)     |
| `frontend/`                                                | Vue 3 app with OCR, assistant and workpaper screens   |

Workpaper disclaimer (D-07), exact string:

`DOKUMEN KERJA (WORKPAPER) — BUKAN SPT RESMI DAN BUKAN PRODUK DJP/CORETAX.`

## Receipt purge

There is no in-process scheduler. An expired receipt that no transaction links
to is removed when that same user uploads again, and by this command:

```bash
PYTHONPATH=backend python -m app.scripts.purge_receipts
```

The command prints how many rows it deleted. A receipt that a transaction
still references is kept, including after `expires_at_utc`.
