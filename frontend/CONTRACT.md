# Frontend build contract

Shared conventions every page in `src/pages/` must follow. The primitives already
encode the Apple-flavoured behaviour, so pages compose them rather than
re-implementing interaction.

## Stack

Vue 3.5 `<script setup>` + TypeScript, Vite, Pinia, vue-router. No UI framework and
no CSS framework — all styling is scoped `<style>` reading the tokens in
`src/styles/tokens.css`. Plain CSS, not `<style module>`, not Tailwind.

## Non-negotiables

1. **All UI copy is Indonesian.** Numbers use the `src/lib/format.ts` helpers
   (`rupiah`, `rupiahPlain`, `rupiahShort`, `tanggal`, `persen`, ...). Never
   hand-write a thousands separator, a date, or a currency symbol.
2. **`page` container.** Every page's root is `<div class="page">` with
   `max-width: var(--canvas-max); margin-inline: auto; display: flex;
flex-direction: column; gap: var(--s-6);`. Copy the block from
   `DasborPage.vue`.
3. **Every page that shows an amount renders `<WorkpaperNote />`.** A figure with
   no ruleset id and no date on it is not a workpaper figure.
4. **Space only from tokens** — `--s-1` … `--s-20`, `--r-xs` … `--r-full`,
   `--t-*` for type, `--ease-*` / `--t-*` for motion. No raw px values for
   spacing, no hardcoded hex, no `#fff` in a component.
5. **Responsive by default.** Three breakpoints: `<768` phone, `768–1279` tablet,
   `≥1280` desktop. The shell already handles navigation; pages must never add
   their own nav. Use `flex`/`grid` + `min-width: 0` and explicit breakpoints.
   Never a horizontal page scrollbar.
6. **No decorative blobs, glows, gradient meshes, `animate-ping`, or fake product
   mockups inside the app.** One accent, hairline borders, tonal depth. Those
   were the tell of the generated designs and they are gone.
7. **`AppIcon` for every glyph.** Its `name` accepts any string from
   `src/components/ui/icons.ts`. Never an emoji, never a Material Symbols font.
8. **Reduced motion, contrast and transparency are already handled globally** in
   `styles/motion.css` and `styles/tokens.css`. Do not re-implement; do add
   `:focus-visible` behaviour through the existing outline.
9. **Files are code, and a reviewer must read them.** Add a one-line doc comment
   saying what the page is responsible for. No comments explaining how CSS works.
10. **Type safety is enforced.** `npx vue-tsc --build --force` must pass.

## Available primitives

`@/components/ui/`

| Component      | Props                                                                                                    |
| -------------- | -------------------------------------------------------------------------------------------------------- |
| `AppButton`    | `variant: primary soft outline ghost danger`, `size: sm md lg`, `to`, `href`, `icon`, `iconEnd`, `block` |
| `AppCard`      | `title`, `subtitle`, `inset`, `flush`, `as`; slots `actions`                                             |
| `AppField`     | `label`, `hint`, `error`, `optional`, `forId` + default slot                                             |
| `AppInput`     | `modelValue` (v-model), `id`, `invalid`, `mono`; slots `pre`, `post`                                     |
| `AppSelect`    | `modelValue`, `options: {value,label}[]`, `id`, `invalid`                                                |
| `AppPill`      | `tone: usaha bebas final non ask neutral accent`, `label`, `icon`, `size`, `attention`                   |
| `AppMeter`     | `value`, `max`, `label`, `caption`, `warnAt`; default slot is the footnote                               |
| `AppSegmented` | `modelValue`, `options: {value,label,count?}[]`, `ariaLabel`                                             |
| `AppSheet`     | `open` (v-model), `title`, `subtitle`, `wide`; emits `close`; slots `footer`                             |
| `AppIcon`      | `name`, `size` (number), `strokeWidth`, `filled`                                                         |

`@/components/app/`

| Component           | Purpose                                                            |
| ------------------- | ------------------------------------------------------------------ |
| `WorkpaperNote`     | The ruleset / date / not-an-SPT stamp. Use on every amount screen. |
| `StatCard`          | One labelled figure. `tone: default accent warn ask`               |
| `SourceTag`         | `sumber: rule ai user_clarification user_override`                 |
| `TransactionLedger` | `rows: Baris[]`, emits `open(id)` — already responsive             |

Stores hold the last `/api/v1` response. Labels live in `src/lib/domain.ts`
(`KATEGORI_LABEL`, `SOURCE_CHANNEL_LABEL`, `SUMBER_LABEL`). `useSessionStore`
is the cookie session. `usePajakStore` is the dashboard. Do not sum rows into
a tax figure.

Router names: `/` landing (bare), `/masuk` (bare), `/dasbor`, `/transaksi`,
`/transaksi/baru`, `/transaksi/:id`, `/asisten`, `/kuota`, `/profil`.

## Domain rules that must not drift

- Exactly four categories: `usaha`, `pekerjaan_bebas`, `already_final`,
  `non_object`. Plus the unresolved state "perlu klarifikasi", which is not a
  category — it is a row waiting on an answer.
- Classification source is one of `rule`, `ai`, `user_clarification`,
  `user_override`, and is always shown next to the category.
- The Rp 500.000.000 annual exemption applies to **usaha turnover only**.
  Pekerjaan bebas does not consume it. Do not imply otherwise anywhere.
- The reference regulation is **PP 20/2026**. Older Stitch mocks said
  "PP 55/2022"; that is stale and must not appear.
- A signed-in amount comes from `GET /tax/dashboard` or `GET /recap/{tax_year}`.
  `PUBLIC_RULESET` is only the academic identity for pages with no session.
- Channel values are `marketplace`, `corporate_client`, `retail`, `other`.
- All money is integer rupiah. Never a float, never a decimal point.
- Do not present a figure as a filing or an obligation. There is no transaction
  quota. Quotas are AI classification and assistant answers.

## Responsive checks before you finish

- 390 × 844 — nothing overflows, no horizontal scroll, tap targets ≥ 40px.
- 834 × 1112 — two-up grids where sensible, no squashed single column.
- 1440 × 900 — content capped and centred, sidebar visible.
