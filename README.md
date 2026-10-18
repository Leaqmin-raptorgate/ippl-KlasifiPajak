# KlasifiPajak

Indonesian UMKM / freelancer tax calculator. Each transaction is classified
first. A deterministic engine then computes Final PPh. A language model never
produces a tax amount.

Not a filed return. Not authorized DJP software.

## Setup

Python 3.12+ and Node.js 20+. Node is development tooling only (commitlint,
Husky hooks, Prettier) — never runtime.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

npm ci   # ALWAYS npm ci, never npm install (lockfile-locked)
```

Run the tests:

```bash
npm run test
```

Docker runs the same tests:

```bash
docker compose run --rm test
```

## API

FastAPI over the deterministic engine, plus an authenticated application
surface backed by MySQL 8. The engine endpoints are unauthenticated and bound to
loopback. See the [API specification](docs/api/KlasifiPajak_API_Specification.md).

```bash
docker compose up api          # http://localhost:8000
# or, against the virtualenv:
PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:app --reload
```

| Endpoint                           | Purpose                                       |
| ---------------------------------- | --------------------------------------------- |
| `GET /health`                      | liveness                                      |
| `GET /ruleset`                     | rates and ceilings, so no client inlines them |
| `POST /snapshot`                   | compute one snapshot from a transaction set   |
| `POST /api/v1/auth/register`       | create an account                             |
| `POST /api/v1/auth/login`          | open a cookie session                         |
| `GET/PUT /api/v1/profiles/{year}`  | read or version the business profile          |
| `GET/POST /api/v1/transactions`    | list or record a classified transaction       |
| `GET /api/v1/tax/dashboard`        | thresholds and monthly summaries              |
| `GET /api/v1/quotas`               | monthly quota limits                          |
| `GET /api/v1/subscriptions/status` | plan state from `paid_flag`                   |

Money crosses the wire as integer rupiah and is rejected as a string or float.

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

- **Lint & format**: ruff (`npm run lint`) and ruff format + Prettier
  (`npm run format:check`).
- **Tests**: the pytest suite with the 80% branch coverage gate on the engine
  (NFR-14), and the same suite inside the Docker test image.

The test jobs only run once the lint job passes. The workflow does not publish
or deploy anything.

## Layout

- `backend/app/engine/` — tax calculation. Pure Python, no framework, no model
- `backend/app/engine/ruleset/` — rate, exemption band, eligibility cap, spouse switches
- `backend/app/api/` — HTTP routes (thin, no SQL)
- `backend/app/schemas/` — Pydantic request and response shapes
- `backend/app/services/` — one function per use case
- `backend/app/classify/` — rules, BM25, model client interface (planned)
- `backend/app/payments/` — gateway adapter (planned)
- `backend/tests/` — engine tests, API tests, and `TC-GOLDEN-*`
- `backend/alembic/` — migrations (planned)
- `frontend/` — Vue 3 + Vite
- `docs/api/` — API specification (unratified)

Layering rules and what lands when: [backend/README.md](backend/README.md).

## Docs

- [AGENTS.md](AGENTS.md) — rules for coding agents. Read before changing code.
- [CONTRIBUTING.md](CONTRIBUTING.md) — workflow, commit conventions, quality gates
- [SECURITY.md](SECURITY.md) — private vulnerability reporting
- [docs/STYLE.md](docs/STYLE.md) — style authority
- [docs/agile/backlog.md](docs/agile/backlog.md) — sprint status
- [docs/agile/roadmap.md](docs/agile/roadmap.md) — sequence, risks, open decisions
- [docs/agile/open-decisions.md](docs/agile/open-decisions.md) — questions that are not ours to answer
- [docs/api/KlasifiPajak_API_Specification.md](docs/api/KlasifiPajak_API_Specification.md) — API contract, unratified

The course SRS stays outside this repository and is never pushed. The SRS of
record is **v2.6** (18 Okt 2026), which is not yet committed to a file — see
the provenance warning in `AGENTS.md`.
