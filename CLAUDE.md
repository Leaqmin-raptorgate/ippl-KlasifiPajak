# CLAUDE.md

The project rules live in [AGENTS.md](AGENTS.md). Read that file.

This file exists only as a pointer, so the two cannot drift apart.

Quick reference:

- Requirements come from `SPEC/`, which lives beside this repository. The SRS of
  record is **v2.6** (18 Okt 2026), with ERD v1.2.2 and API v1.2.2 on disk. See
  `AGENTS.md` for provenance.
- Never invent a requirement, threshold, tax figure, or expected test value.
  Leave a `TODO` instead.
- The tax engine is pure Python and never calls a language model.
- Money is `int` rupiah. Never a float.
- 4 spaces, plain code, docstrings with `FR`/`UC`/`NFR` ids.
- `pytest` must pass before a change is called done.
