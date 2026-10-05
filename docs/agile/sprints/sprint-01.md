# Sprint 1 — Docs and stack

5 to 11 Oct 2026. Goal: the requirements are honest and the stack is recorded.

Deliberately documentation only, so a coursework spike costs nothing.

## Stories

- Record the stack that already exists plus open decisions (IPPL-2)
- Polish the SRS (IPPL-3)
- Draft the SDD once the SRS feels complete

## Blockers, both needing the developer

- **Golden values.** Supply the expected exempt, taxable and tax figures for the
  eight `TC-GOLDEN-*` cases, read from the PP 20/2026 elucidation. Until then
  those tests must not assert invented numbers.
- **SRS v2.3.** Define payments, OCR, the Pasal 17 question, paid quota caps,
  the `input_hash` field list, and the `effective_date` versus `as_of_date`
  naming.

## Done when

- The SRS reads cleanly for someone who has not seen the project.
- The stack line in the SRS matches what is actually in the repository.
- Every requirement id used in code or docs exists in a committed document.

## Also landed during this sprint

Structure only, no behaviour change:

- Moved `src/klasifipajak` to `backend/app`, tests to `backend/tests`
- Added `AGENTS.md` and `CLAUDE.md`
- 18 tests still pass on the host and in Docker
