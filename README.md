# KlasifiPajak

Indonesian UMKM / freelancer tax calculator. Each transaction is classified
first. A deterministic engine then computes Final PPh. A language model never
produces a tax amount.

Workpaper disclaimer (locked by D-07; matches `backend/app/services/snapshot.py`
and API §3.3):

`DOKUMEN KERJA (WORKPAPER) — BUKAN SPT RESMI DAN BUKAN PRODUK DJP/CORETAX.`

Not a filed return. Not authorized DJP software.

## Spec versions (source of truth)

| Artefact | Version                                 | Where                                                                                                                                       |
| -------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| SRS      | **v2.7**                                | Outside this repository (`SPEC/`); course SRS is never pushed here                                                                          |
| API      | **v1.3.3**                              | Mirrored at [`docs/api/KlasifiPajak_API_Specification.md`](docs/api/KlasifiPajak_API_Specification.md)                                      |
| ERD      | **r3** (D-11 `month_snapshots.version`) | Outside this repository (`SPEC/`); r3 was `76fcdbc4af30`; later revisions are proposed r4 changes; run `alembic heads` for the current head |

Prior API text in this repo was v1.2.2; treat the mirror above as normative.

## Setup

Python 3.12+ and Node.js 20+. Node is development tooling only (commitlint,
Husky hooks, Prettier) — never runtime.

```bash
cp .env.example .env   # then set JWT_SECRET and DB passwords
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

npm ci   # ALWAYS npm ci, never npm install (lockfile-locked)
```

### Environment that matters

| Variable               | Role                                                                                                                          |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `APP_ENV`              | `development` / `test` / `production`. Controls Bagian A mount, test-support mount, and JWT secret fail-closed in production. |
| `DATABASE_URL`         | Runtime **DML** user (`klasifipajak_app`). Used by the API process.                                                           |
| `MIGRATE_DATABASE_URL` | **DDL** user (`klasifipajak_migrate`). Used only by Alembic / the compose `migrate` service.                                  |
| `JWT_SECRET`           | Session signing secret (≥ 32 bytes in production).                                                                            |
| `TRUSTED_PROXY_IPS`    | Comma-separated peer IPs/CIDRs allowed to supply `X-Forwarded-For`. Empty = trust none.                                       |
| `TRUSTED_PROXY_COUNT`  | How many rightmost XFF hops to peel when the peer is trusted (default `0`).                                                   |
| `AI_*`                 | OpenAI-compatible client settings for receipt OCR, fallback classification, and assistant Q&A. Empty = fail closed to rules.  |
| `MIDTRANS_*`           | Midtrans Snap server/client keys and production flag for subscription checkout and notification verification.                 |

### Docker Compose (MySQL + migrate + API + frontend)

Compose boots MySQL, runs a **one-shot `migrate` service** (`alembic upgrade head`
as `klasifipajak_migrate`), then starts the API as `klasifipajak_app` and the
Vite frontend. The API depends on migrate completing successfully. Schema is
**not** created via `create_all` at runtime.

```bash
docker compose up mysql migrate api frontend
# or simply:
docker compose up frontend            # pulls mysql + migrate + api via depends_on
```

- API: http://127.0.0.1:8000
- Frontend: http://127.0.0.1:5173 (Vite proxies `/api` to the `api` service)

Against a virtualenv (MySQL already migrated):

```bash
PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Tests

```bash
npm run test                          # host pytest
npm run test:coverage                 # 80% branch gate on backend/app/engine (NFR-14)
docker compose run --rm test          # same suite inside the Docker test image
npm --prefix frontend run test:unit   # Vitest (happy-dom); no backend required
```

## API surface (what exists on main today)

FastAPI over the deterministic engine, plus an authenticated application
surface backed by MySQL 8. Engine endpoints are unauthenticated and bound to
loopback. See the [API specification](docs/api/KlasifiPajak_API_Specification.md)
(v1.3.3).

| Endpoint                                                   | Purpose                                                 |
| ---------------------------------------------------------- | ------------------------------------------------------- |
| `GET /health`                                              | liveness                                                |
| `GET /ruleset`                                             | rates and ceilings                                      |
| `POST /snapshot`                                           | compute one snapshot from a transaction set             |
| `POST /api/v1/auth/register`                               | create an account (argon2id)                            |
| `POST /api/v1/auth/login`                                  | open a cookie session                                   |
| `POST /api/v1/auth/logout`                                 | revoke this session                                     |
| `GET /api/v1/auth/me`                                      | current user                                            |
| `POST /api/v1/auth/password-reset/request`                 | request reset (generic response)                        |
| `POST /api/v1/auth/password-reset/confirm`                 | confirm reset with token                                |
| `GET /api/v1/auth/sessions`                                | list sessions                                           |
| `DELETE /api/v1/auth/sessions/{id}`                        | revoke one session                                      |
| `DELETE /api/v1/auth/sessions`                             | revoke other sessions                                   |
| `DELETE /api/v1/account`                                   | delete account                                          |
| `GET/PUT /api/v1/profiles/{year}`                          | read or version the business profile                    |
| `GET/POST /api/v1/transactions`                            | list or record a classified transaction                 |
| `GET/PUT/DELETE /api/v1/transactions/{id}`                 | read, edit, delete                                      |
| `POST .../override`, `.../clarification`, `.../reclassify` | category flows (rules-only today)                       |
| `GET /api/v1/tax/dashboard`                                | thresholds and monthly summaries (`as_of` = today WIB)  |
| `GET/POST /api/v1/tax/snapshots/...`                       | month snapshot read / year recalculate (versioned rows) |
| `GET /api/v1/quotas`                                       | monthly quota counters                                  |
| `GET /api/v1/subscriptions/status`                         | plan state from `paid_flag`                             |

Money crosses the wire as integer rupiah and is rejected as a string or float.

### Still open

OCR receipt upload, the Midtrans adapter and webhook, the AI classifier and assistant, and the annual recap PDF are implemented. What is still open:

- **Midtrans Status API confirmation** — settlement trusts the signed notice (signature, amount, `status_code` `"200"`); the Status API is not called. Required before real payments.
- **Live Midtrans keys** — use sandbox keys only (D-10).
- **OD-13** — whether interest, dividends and lottery prizes count toward the Rp 4,8 miliar test is not signed off ([open decisions](docs/agile/open-decisions.md)).

## Available Scripts

| Task                                  | Command                 |
| ------------------------------------- | ----------------------- |
| Run tests                             | `npm run test`          |
| Run tests with coverage gate (NFR-14) | `npm run test:coverage` |
| Run ruff lint                         | `npm run lint`          |
| Fix ruff lint issues                  | `npm run lint:fix`      |
| Fix Python + doc formatting           | `npm run format`        |
| Check formatting (ruff + Prettier)    | `npm run format:check`  |
| Validate a commit message             | `npm run commitlint`    |

The `.husky/pre-commit` hook runs `lint` and `format:check`; commit messages
are validated by commitlint. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Continuous Integration

Every push and pull request targeting `main` runs the
[CI workflow](.github/workflows/ci.yml) via GitHub Actions:

- **Lint & format**: ruff and ruff format + Prettier.
- **Frontend typecheck & build**: `npm --prefix frontend ci && npm --prefix frontend run build` (includes `vue-tsc`, D-11).
- **pip-audit (high/critical)**: fail-closed gate over `requirements.txt`.
- **gitleaks**: secret scan with `.gitleaks.toml`.
- **pytest coverage gate**: 80% branch coverage on `backend/app/engine` (NFR-14), with app/migrate MySQL users bootstrapped.
- **Docker test image**: `docker compose run --rm --build test`.

The workflow does not publish or deploy anything.

## Layout

- `backend/app/engine/` — tax calculation. Pure Python, no framework, no model
- `backend/app/engine/ruleset/` — rate, exemption band, eligibility cap, spouse switches
- `backend/app/api/` — HTTP routes (thin, no SQL)
- `backend/app/schemas/` — Pydantic request and response shapes
- `backend/app/services/` — one function per use case
- `backend/app/models/` — SQLAlchemy tables (ERD r3)
- `backend/app/classify/` — keyword/rules path and fallback AI classifier
- `backend/app/payments/` — Midtrans Snap gateway adapter and notification handling
- `backend/alembic/` — migrations (r3 was `76fcdbc4af30`; later revisions are proposed r4 changes; run `alembic heads` for the current head)
- `backend/tests/` — engine tests, API tests, and `TC-GOLDEN-*`
- `frontend/` — Vue 3 + Vite
- `docs/api/`: API specification mirror (v1.3.3)
- `docs/agile/` — backlog, roadmap, open decisions

Layering rules: [backend/README.md](backend/README.md).

## Docs

- [AGENTS.md](AGENTS.md) — rules for coding agents. Read before changing code.
- [CONTRIBUTING.md](CONTRIBUTING.md) — workflow, commit conventions, quality gates
- [SECURITY.md](SECURITY.md) — private vulnerability reporting
- [docs/STYLE.md](docs/STYLE.md) — style authority
- [docs/agile/backlog.md](docs/agile/backlog.md) — sprint / M50 status
- [docs/agile/roadmap.md](docs/agile/roadmap.md) — sequence, risks, open decisions
- [docs/agile/open-decisions.md](docs/agile/open-decisions.md) — OD-* and D-01…D-18
- [docs/api/KlasifiPajak_API_Specification.md](docs/api/KlasifiPajak_API_Specification.md): API contract **v1.3.3**

The course SRS stays outside this repository and is never pushed. The SRS of
record is **v2.7**; API v1.3.3 includes draft SRS v2.8 changes pending integration into the course SRS. The ERD of record is r3.
