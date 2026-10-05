## What changed

<!-- One logical change. Describe it briefly. -->

## Why

<!-- Motivation. Link the requirement id (FR-…, UC-…, NFR-…) when behaviour is affected. -->

## How to test

<!-- Commands the reviewer can run, e.g. `npm run test:coverage`. -->

## Checklist

- [ ] Atomic: one logical change, nothing unrelated bundled in
- [ ] `npm run lint` and `npm run format:check` pass (or `npm run lint:fix && npm run format`)
- [ ] `npm run test` passes
- [ ] New behaviour is covered by a test; figures are explainable (no invented numbers)
- [ ] Docs updated in this same change (README / AGENTS.md / docs/agile/backlog.md)
- [ ] No secrets, no `.env`, no real gateway or model keys
- [ ] Commit messages follow Conventional Commits

Closes #
