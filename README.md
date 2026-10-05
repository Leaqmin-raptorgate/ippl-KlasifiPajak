# KlasifiPajak

Indonesian UMKM / freelancer tax calculator. Each transaction is classified
first. A deterministic engine then computes Final PPh. A language model never
produces a tax amount.

Not a filed return. Not authorized DJP software.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Docker runs the same tests. No web server yet.

```bash
docker compose run --rm test
```

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
- [docs/STYLE.md](docs/STYLE.md) — style authority
- [docs/agile/backlog.md](docs/agile/backlog.md) — sprint status
- [docs/agile/roadmap.md](docs/agile/roadmap.md) — sequence, risks, open decisions

The course SRS stays outside this repository and is never pushed.
