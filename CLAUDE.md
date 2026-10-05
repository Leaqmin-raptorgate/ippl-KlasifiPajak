# CLAUDE.md

The project rules live in [AGENTS.md](AGENTS.md). Read that file.

This file exists only as a pointer, so the two cannot drift apart.

Quick reference:

- Requirements come from `SPEC/`, which is **not** in this repository. The only
  SRS present is `KP-SRS-001` v1.0. v2.3 is planned and does not exist yet.
- Never invent a requirement, threshold, tax figure, or expected test value.
  Leave a `TODO` instead.
- The tax engine is pure Python and never calls a language model.
- Money is `int` rupiah. Never a float.
- 4 spaces, plain code, docstrings with `FR`/`UC`/`NFR` ids.
- `pytest` must pass before a change is called done.
