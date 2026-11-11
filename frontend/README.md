# KlasifiPajak frontend

A demo frontend. Vue 3 + Vite + TypeScript, vue-router, Pinia. No UI framework
and no CSS framework — the whole surface is hand-written CSS reading the tokens
in `src/styles/tokens.css`.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # typecheck, then bundle to dist/
npm run typecheck  # vue-tsc, strict
```

## Running with Docker Compose

`docker compose up frontend` serves Vite on `http://127.0.0.1:5173` and proxies
`/api` to the `api` service (`API_PROXY_TARGET`, default
`http://127.0.0.1:8000` outside Compose).

- **Before the first run**, create the mount point as yourself:
  `mkdir -p frontend/node_modules`. If Docker creates it, it is owned by root
  and a later host `npm ci` fails with EACCES. To recover:
  `docker run --rm -v "$PWD/frontend:/x" alpine rm -rf /x/node_modules`.
- **After `package-lock.json` changes**, refresh the `frontend_node_modules`
  volume with `docker compose run --rm frontend npm ci`. Do not use
  `docker compose down -v` for this: it also deletes the MySQL data volume.
- The container runs as uid 1000 (`node`) on top of the `./frontend` bind
  mount. On hosts where your user is not uid 1000 (rootless Docker, Podman),
  Vite may be unable to write to the mount.
- Use one workflow per checkout: Compose or host `npm`, not both.

## What it is

Nine screens, all Indonesian copy, all responsive at phone / tablet / desktop:

| Route             | Screen                                                  |
| ----------------- | ------------------------------------------------------- |
| `/`               | Landing                                                 |
| `/masuk`          | Sign in and sign up                                     |
| `/dasbor`         | Where the year's exemption stands, what needs an answer |
| `/transaksi`      | The ledger, with search, month and category filters     |
| `/transaksi/baru` | Capture a transaction                                   |
| `/transaksi/:id`  | Evidence, verdict, legal basis, clarification, override |
| `/asisten`        | Read-only explainer over the stored workpaper           |
| `/kuota`          | Allowance, tiers, appearance                            |
| `/profil`         | Business data, preferences, security                    |

Signed-in screens call `/api/v1` with the session cookie. Vite proxies `/api`
to `http://127.0.0.1:8000`, or to `API_PROXY_TARGET` when Compose sets it. The
browser does not call Bagian A (`/ruleset`, `/snapshot`). A missing route fails
closed and does not fall back to sample rows.

## Ground rules this UI holds to

- **Exactly four categories** — `usaha`, `pekerjaan_bebas`, `already_final`,
  `non_object` — plus the unresolved state, which is a row waiting on an answer,
  not a category.
- **The source of a classification is always shown** next to the category:
  `Aturan`, `AI`, `Klarifikasi`, or `Override`.
- **The Rp 500.000.000 annual exemption applies to usaha turnover only.**
  Pekerjaan bebas does not consume it.
- **Rates and thresholds on a signed-in screen come from the dashboard.** A
  regulation change is a new ruleset id, never an edit to a component.
- **Money is integer rupiah.** `src/lib/format.ts` owns every separator, date and
  rate; nothing hand-writes one.
- **Every amount is stamped** with the ruleset id and its effective date, next to
  the "kertas kerja, bukan SPT" line.
- **The reference is PP 20/2026.** Older Stitch mocks in `SPEC/web-stitch` say
  "PP 55/2022"; that is stale and is not used here.

## Layout

One set of destinations, three presentations:

| Width      | Navigation                              |
| ---------- | --------------------------------------- |
| `< 768px`  | Translucent bottom tab bar              |
| `768–1279` | Icon rail with a label under each glyph |
| `≥ 1280px` | Labelled sidebar                        |

## Interaction notes

- Press feedback fires on pointer-down, and the coarse-pointer build is 44px
  tall, because a finger needs more room than a cursor.
- Sheets enter and leave along the same path, so a dismissal reads as a reversal.
- Every transition is interruptible: they start from whatever is on screen now.
- `prefers-reduced-motion`, `prefers-reduced-transparency` and `prefers-contrast`
  are honoured globally in `src/styles/motion.css` and `src/styles/tokens.css`.

`CONTRACT.md` is the build contract for anyone extending this: primitive props,
the domain rules, and the responsive checklist.

## Wiring

`src/lib/api.ts` sends cookies to `/api/v1`. Screens already use the wire field
names. Do not add a local tax sum when an endpoint is missing.
