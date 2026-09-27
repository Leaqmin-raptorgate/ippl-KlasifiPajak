# ippl-KlasifiPajak

Indonesian UMKM / freelancer tax calculator. Each transaction is classified first. A deterministic engine then computes Final PPh. A language model never produces a tax amount.

This slice is the tax engine and its golden tests. No web UI yet.

Not a filed return. Not authorized DJP software.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

## Layout

- `src/klasifipajak/ruleset/` — rates, exemption band, eligibility cap
- `src/klasifipajak/engine/` — calculation only
- `tests/` — `TC-GOLDEN-*` and engine checks
- `docs/STYLE.md` — how code in this repo is written

## Docs

Stable project docs live in [docs/](docs/). The course SRS stays outside this repository.
