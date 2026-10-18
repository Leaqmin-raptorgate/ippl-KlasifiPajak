# Open decisions

Decisions that are **not** ours to make. Do not resolve any of these in code,
tests, or prose. Record the answer here and in `roadmap.md` when it arrives.

## From SRS v2.6

| #    | Question                                                                                                                                                     | State                                                                                                                                                                                                                                      |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| OD-1 | `effective_date` or `as_of_date`? v2.6 §1.4 defines _tanggal berlaku_ in prose and §4.5 calls the same concept _tanggal berlaku_, but never names the field. | **Closed 18 Okt 2026 by API v1.2.2.** Both exist and mean different things: `effective_date` is the ruleset promulgation stamp; `as_of_date` is the calculation cutoff. Implemented as `Ruleset.effective_date` and `Snapshot.as_of_date`. |
| OD-2 | Is SRS v2.6 a committed artefact? It reached the repository through conversation only.                                                                       | **Closed 18 Okt 2026.** `SPEC/KlasifiPajak/KlasifiPajak_SRS.md` now carries v2.6, with the ERD and API v1.2.2 beside it.                                                                                                                   |
| OD-3 | KAP/KJS live value. `pp20_2026.json` carries `ACADEMIC-PLACEHOLDER`.                                                                                         | **Open.** v2.6 §1.3 keeps KAP/KJS as printed text only, with no Coretax API call. A real code needs the developer's source.                                                                                                                |
| OD-4 | Prior-year fields: is _not filled in_ an explicit state, or `0`?                                                                                             | **Partially closed.** FR-03 requires empty to mean `null`, not zero. Implemented as an explicit sentinel — see `types.py` `UNSET`.                                                                                                         |

## Carried over from before v2.6

| #     | Question                                                                                                                                                 | State                                                                                                                                                                          |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| OD-5  | Entity-type field for PP 20/2026 eligibility. Verify against Pasal 56 and 57.                                                                            | **Open.** v2.6 §1.3 excludes non-individual taxpayers from v1 as a _product_ decision, not a legal reading.                                                                    |
| OD-6  | Snapshot storage: overwrite, or versioned rows with an `is_current` flag.                                                                                | **Provisional.** Month rows are keyed `(profile_id, month_key)` and rebuilt in place inside the write transaction. No history flag yet; revisit when the procedure tier lands. |
| OD-7  | Paid-tier quota caps. v2.6 §1.5 and FR-43 give defaults of 200 AI and 200 assistant answers per calendar month.                                          | **Closed as defaults.** Configurable per v2.6. Calibration still open.                                                                                                         |
| OD-8  | Quota reset period.                                                                                                                                      | **Closed by v2.6.** FR-34 and §1.5: calendar month, `Asia/Jakarta`, 00:00 WIB boundary.                                                                                        |
| OD-9  | Free trial period. v2.6 §1.3 removes trials entirely.                                                                                                    | **Closed by v2.6.** Free tier is permanent and quota-limited; no trial.                                                                                                        |
| OD-10 | Whether to adopt a typed decision model behind the classifier interface.                                                                                 | **Open.**                                                                                                                                                                      |
| OD-11 | Test coverage target.                                                                                                                                    | **Partially closed.** NFR-14 sets branch coverage >= 80% on the core tax engine.                                                                                               |
| OD-12 | API contract location. SRS v2.6 §2.7(f) requires endpoints to live in a separate `KlasifiPajak_API_Specification` file, and defines no endpoints itself. | **Closed 18 Okt 2026.** API v1.2.2 is the normative contract and is mirrored at `docs/api/KlasifiPajak_API_Specification.md`.                                                  |

## How to use this file

When a decision arrives: replace the row state, note the date and who decided,
and update `roadmap.md` in the same change. AGENTS.md working agreement: update
`backlog.md` in the same change as the code it describes.
