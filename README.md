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

Docker runs the same tests. No web server yet.

```bash
docker compose run --rm test
```

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
- `backend/app/engine/ruleset/` — rate, exemption band, eligibility cap, KAP/KJS
- `backend/app/classify/` — rules, BM25, model client interface (planned)
- `backend/app/services/` — one function per use case (planned)
- `backend/app/api/` — thin routes (planned)
- `backend/app/payments/` — gateway adapter (planned)
- `backend/tests/` — engine tests and `TC-GOLDEN-*`
- `backend/alembic/` — migrations (planned)
- `frontend/` — Vue 3 + Vite (planned)
- `nginx/` — serves the built frontend (planned)

Layering rules and what lands when: [backend/README.md](backend/README.md).

## Docs

- [AGENTS.md](AGENTS.md) — rules for coding agents. Read before changing code.
- [CONTRIBUTING.md](CONTRIBUTING.md) — workflow, commit conventions, quality gates
- [SECURITY.md](SECURITY.md) — private vulnerability reporting
- [docs/STYLE.md](docs/STYLE.md) — style authority
- [docs/agile/backlog.md](docs/agile/backlog.md) — sprint status
- [docs/agile/roadmap.md](docs/agile/roadmap.md) — sequence, risks, open decisions

The course SRS stays outside this repository and is never pushed.
