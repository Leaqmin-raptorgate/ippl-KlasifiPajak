# Contributing to KlasifiPajak

This document covers the workflow, conventions, and quality gates you'll need to
know before opening a pull request.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Branching](#branching)
- [Commit Conventions](#commit-conventions)
- [Code Style & Quality Gates](#code-style--quality-gates)
- [Architecture Notes](#architecture-notes)
- [Keeping Docs in Sync](#keeping-docs-in-sync)
- [Pull Requests](#pull-requests)
- [Reporting Bugs & Requesting Features](#reporting-bugs--requesting-features)

## Getting Started

Python 3.12+ and Node.js 20+ are required. Node is used only for development
tooling (commitlint, Husky hooks, Prettier) — not at runtime.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

npm ci   # ALWAYS npm ci, never npm install — lockfile-locked versions
```

`requirements-dev.txt` pulls in `requirements.txt` plus the lint tooling
(ruff), so one install covers test and lint.

## Development Workflow

- `npm run test` — run the pytest suite (18 engine tests today).
- `npm run test:coverage` — same suite with the 80% branch coverage gate.
- `docker compose run --rm test` — run the suite inside the Docker test image.
- There is no web server yet; `frontend/` and `nginx/` are placeholders.

## Branching

Branch off `main` using `<type>/<short-kebab-description>` (e.g.
`feat/classify-rules`, `fix/tax-rounding`), where `<type>` matches one of the
commit types below.

## Commit Conventions

All commits and pull requests MUST be **atomic** — one logical change per
commit/PR, nothing unrelated bundled in.

Commit messages MUST follow [Conventional Commits](https://www.conventionalcommits.org/),
enforced by commitlint (`.husky/commit-msg`, `commitlint.config.js`):

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

- A blank line is REQUIRED before the body (if present) and before the
  footer(s) (if present).
- `<type>` MUST be one of: `build`, `chore`, `ci`, `docs`, `feat`, `fix`,
  `perf`, `refactor`, `revert`, `style`, `test`.
- The `body-max-line-length` rule is disabled, so wrap body text however reads
  best.

## Code Style & Quality Gates

| Task                                  | Command                 |
| ------------------------------------- | ----------------------- |
| Run ruff lint                         | `npm run lint`          |
| Fix ruff lint issues                  | `npm run lint:fix`      |
| Fix Python formatting (ruff format)   | `npm run format`        |
| Check formatting (ruff + Prettier)    | `npm run format:check`  |
| Run tests                             | `npm run test`          |
| Run tests with coverage gate (NFR-14) | `npm run test:coverage` |

The `.husky/pre-commit` hook runs, in order: `lint`, `format:check`. **Both
MUST pass to commit.** Before committing, it's easiest to just run:

```bash
npm run lint:fix
npm run format
```

These same checks — plus the pytest suite with the 80% branch coverage gate
(NFR-14) and the Docker test image — are enforced in CI
(`.github/workflows/ci.yml`) on every push and pull request to `main`. Lint and
format run first; tests only run once they pass. Bypassing the pre-commit hook
(e.g. with `--no-verify`) only skips the local check; the PR will still fail CI
if the gates don't pass.

Python style is 4-space indent, `snake_case`, and docstrings on every public
module, class, and function that cite the `FR`/`UC`/`NFR` id they implement.
Full rules: [AGENTS.md](AGENTS.md) and [docs/STYLE.md](docs/STYLE.md).

## Architecture Notes

See [backend/README.md](backend/README.md) and [README.md](README.md) for the
layering. The short version:

- `backend/app/engine/` — pure tax maths. No FastAPI, no SQLAlchemy, no HTTP,
  no model calls. Rates and bands live in the ruleset JSON, not in code.
- `backend/app/classify/` — rules first, then optional model fallback.
- `backend/app/services/` — one function per use case, owns the transaction.
- `backend/app/api/` — validate, call one service, return.
- Money is `int` rupiah. Confidence is `Decimal`. Store UTC, derive month keys
  with `Asia/Jakarta`.
- Every query is scoped by `user_id`.

**Where new code goes:**

- New tax rule or rate → `backend/app/engine/ruleset/` (new `ruleset_id`, never
  edit a published ruleset's numbers in place).
- New engine logic → `backend/app/engine/` with tests in `backend/tests/`,
  including golden cases when figures are known.
- New use case → one function in `backend/app/services/`.
- New route → `backend/app/api/`, thin: validate, call one service, return.

## Keeping Docs in Sync

All documentation (`README.md`, `AGENTS.md`, `docs/agile/*`, and any future
docs) MUST be kept up to date as the code changes. If your change affects a
documented command, architecture, or behavior, update the relevant doc in the
**same** change.

## Pull Requests

- Keep PRs atomic — one logical change, nothing unrelated bundled in.
- Fill in the pull request template.
- Make sure the pre-commit checks pass locally before pushing.
- Link related issues (e.g. `Closes #123`).
- Every tax figure the change produces must be explainable; cite the
  requirement id (`FR-…`, `UC-…`, `NFR-…`) in docstrings.

## Reporting Bugs & Requesting Features

Use the issue templates (Bug Report / Feature Request) when opening a new issue
— they'll prompt you for the details maintainers need to triage.

For security vulnerabilities, **do not** open a public issue — see
[SECURITY.md](SECURITY.md) instead.
