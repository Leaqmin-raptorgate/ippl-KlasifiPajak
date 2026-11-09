# Open decisions

Decisions that are **not** ours to make stay in the OD-* table below. Approved
product decisions D-01…D-11 are recorded here for agents working in this repo;
the Lead's full ADR log lives outside the repository.

Spec of record: **SRS v2.7**, **API v1.3.3** (mirrored under `docs/api/`),
**ERD r3**.

## Approved decisions (D-01…D-11)

| ID   | Topic                                                                                                             | Status                                                                                         |
| ---- | ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| D-01 | Receipt photo storage: local disk under `RECEIPT_STORAGE_ROOT`, authenticated GET, EXIF strip                     | **approved** 2026-10-28 — **landed** (local disk, authenticated GET, EXIF strip, FR-06 upload) |
| D-02 | Cross-doc naming / consistency (quota columns, profile maps, MySQL 8, `auth_rate_limits`)                         | **approved** 2026-10-28 — applied in docs                                                      |
| D-03 | PP 20/2026 wording corrections (`already_final` toward cap, golden labels)                                        | **approved** 2026-10-28 — applied in docs                                                      |
| D-04 | Google OIDC: design in docs, **defer build** in v1                                                                | **approved** 2026-10-28                                                                        |
| D-05 | Security fixes (test-support fail-closed, argon2id, webhook order, prompt envelope, rate limits, …)               | **approved** 2026-10-28 — largely landed in PR #3                                              |
| D-06 | Receipt extras from Aerial-Analytics: S1+S4 **Must**, S5 Should, S2 Could                                         | **approved** 2026-11-02 (gated on OCR staying in v1)                                           |
| D-07 | B-08 hardening plan r2                                                                                            | **approved** 2026-11-02                                                                        |
| D-08 | Full v1 per lecturer rubric (OCR, Midtrans, AI, recap PDF — **no feature cut**)                                   | **approved** 2026-11-02                                                                        |
| D-09 | AI via 9router (`AI_BASE_URL` / `AI_API_KEY` / model ids); fail-closed when unset                                 | **approved** 2026-11-02 — **landed** (PR #17)                                                  |
| D-10 | Midtrans keys deferred to placeholders; live keys before demo freeze                                              | **approved** 2026-11-02 — **adapter landed** (PR #16)                                          |
| D-11 | Snapshot `version` UK; OCR via 9router+Gemini Vision; PDF=`fpdf2`; Midtrans `redirect_url`; FE CI gate; M50 lanes | **approved** 2026-11-02 — versioning, FE CI, OCR, PDF, and Snap **landed**                     |

### D-07 disclaimer (exact string)

Must match `backend/app/services/snapshot.py` and API §3.3:

`DOKUMEN KERJA (WORKPAPER) — BUKAN SPT RESMI DAN BUKAN PRODUK DJP/CORETAX.`

Spelling is **WORKPAPER** (work + paper), not WORKOBER.

## From SRS v2.6 / v2.7

| #    | Question                                                             | State                                                                                                             |
| ---- | -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| OD-1 | `effective_date` or `as_of_date`?                                    | **Closed.** Both exist: `effective_date` = ruleset stamp; `as_of_date` = calculation cutoff. API v1.3.3 / engine. |
| OD-2 | Is the SRS a committed artefact?                                     | **Closed.** SRS **v2.7** is the SoT outside this repo; API mirror is v1.3.2; ERD is **r3**.                       |
| OD-3 | KAP/KJS live value. `pp20_2026.json` carries `ACADEMIC-PLACEHOLDER`. | **Open.** Printed text only in v1; no Coretax API call.                                                           |
| OD-4 | Prior-year fields: empty vs `0`?                                     | **Closed in code.** FR-03 / `UNSET` sentinel in `types.py`.                                                       |

## Carried over

| #     | Question                                                    | State                                                                                                                                                                                                                  |
| ----- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OD-5  | Entity-type field for PP 20/2026 eligibility (Pasal 56/57). | **Open.** v1 product scope is `orang_pribadi` only.                                                                                                                                                                    |
| OD-6  | Snapshot storage: overwrite vs versioned rows.              | **Closed by D-11.** `month_snapshots` UK is `(profile_id, month_key, version)`; recalc marks prior `usang`, inserts new `berlaku` with `version+1`. Reads filter `status = berlaku`. Landed in PR #4 + Alembic ERD r3. |
| OD-7  | Paid-tier quota caps.                                       | **Closed as defaults** (200 / 200 per calendar month). Calibration still open.                                                                                                                                         |
| OD-8  | Quota reset period.                                         | **Closed.** Calendar month, `Asia/Jakarta`, 00:00 WIB.                                                                                                                                                                 |
| OD-9  | Free trial period.                                          | **Closed.** No trial; free tier is permanent and quota-limited.                                                                                                                                                        |
| OD-10 | Typed decision model behind the classifier interface.       | **Open.**                                                                                                                                                                                                              |
| OD-11 | Test coverage target.                                       | **Partially closed.** NFR-14: branch coverage ≥ 80% on `backend/app/engine` only.                                                                                                                                      |
| OD-12 | API contract location.                                      | **Closed.** Normative contract mirrored at `docs/api/KlasifiPajak_API_Specification.md` (**v1.3.3**).                                                                                                                  |

## How to use this file

When a decision arrives: replace the row state, note the date and who decided,
and update `roadmap.md` / `backlog.md` in the same change. Do not invent
requirements to close an OD-*.

## Decisions for the proposed SRS v2.8 changes

- D-12: Use the developer-supplied 9router endpoint, with `AI_BASE_URL=https://9router.putrahomelab.com/v1`; model selection and live compatibility await evaluation.
- Data leaves the application for the configured AI host (`AI_BASE_URL`).
- D-13: A failed recalculation rolls back the entire transaction and retains previous figures.
- D-14: Withholding status is `nihil` when equal, `kurang_potong` below, and `belum_diperhitungkan` above tax.
- D-15: Developer confirmed on 8 November 2026: demo freeze is Friday 27 November 2026, 18:00 Asia/Makassar.
- D-16: Record and acknowledge refund and chargeback notifications without changing entitlement.
- D-17: Both classifier and assistant are in scope pending lecturer confirmation; cut the assistant first if necessary.
- D-18: Developer confirmed on 8 November 2026: omitted `source_channel` defaults to `other`. Supplied values must be `marketplace`, `corporate_client`, `retail`, or `other`.
