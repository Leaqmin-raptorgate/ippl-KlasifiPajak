# KlasifiPajak API Specification

**Version:** 1.2.2
**Status:** Normative contract
**Aligned with:** KlasifiPajak SRS v2.6 and SDD v1.1 (18 Oktober 2026)
**Author:** 11241050 - Muhammad Aditya Putra

SRS §2.7.f points here. Endpoint paths, JSON fields, error codes, and session rules in this file are the contract. The SRS states product behavior and does not lock a framework name.

---

## 1. Surfaces

| `APP_ENV`     | Bagian A on `127.0.0.1:8000` | `/api/v1/test-support/*`    | `/api/v1/*` | CORS origin                   |
| ------------- | ---------------------------- | --------------------------- | ----------- | ----------------------------- |
| `development` | Mounted                      | Not mounted (`404`)         | Mounted     | `http://localhost:5173`       |
| `test`        | Mounted                      | Mounted on `127.0.0.1` only | Mounted     | `http://localhost:5173`       |
| `production`  | Not mounted (`404`)          | Not mounted (`404`)         | Mounted     | `https://app.klasifipajak.id` |

- **Application base URL:** `https://api.klasifipajak.id/api/v1` in production, `http://127.0.0.1:8000/api/v1` locally. `api.klasifipajak.id` and `app.klasifipajak.id` are the same site.
- **Engine base URL:** `http://127.0.0.1:8000` with no `/api/v1` prefix (`/health`, `/ruleset`, `/snapshot`). Bagian A never accepts traffic from a public interface.
- **TLS:** Production `/api/v1/*` requires HTTPS. Plain HTTP is limited to localhost.
- **CORS:** `Access-Control-Allow-Origin` is the exact origin from the table, never `*`. Responses include `Access-Control-Allow-Credentials: true`. Browser clients send credentials. `Vary: Origin` is set.

---

## 2. Shared rules

### 2.1 Types

- Money fields (`*_idr`) are JSON integers. No floats, decimals, or subunits.
- `confidence` on a classification is a JSON number from 0 to 1. It is not an input to tax arithmetic.
- Timestamps are UTC `YYYY-MM-DDTHH:mm:ssZ`.
- Tax dates are Jakarta calendar dates `YYYY-MM-DD`. A tax month is `YYYY-MM` evaluated at `Asia/Jakarta` 00:00 WIB.
- Display of instants to the user uses `Asia/Jakarta` (WIB, UTC+7).
- Supported tax year for this ruleset is 2026. A transaction date is valid only when `2026-01-01 <= tx_date <= 2026-12-31`.

### 2.2 Academic ruleset

`ruleset_id` `pp20-2026-academic-1` carries `effective_date` `2026-09-26` as its promulgation stamp and applies to every valid 2026 `tx_date`, including dates before 26 September 2026.

`GET /ruleset` may include `rate_str` `"0.005"` as display text. Arithmetic uses `rate_numerator` and `rate_denominator` only.

`rounding_rule` is `floor` or `round_half_up`. This academic file ships `floor`.

```
tax_idr = floor(porsi_kena_idr * rate_numerator / rate_denominator)
```

`round_half_up` for a non-negative amount is:

```
tax_idr = floor((porsi_kena_idr * rate_numerator + rate_denominator / 2) / rate_denominator)
```

With `1/200`, both rules yield tax `0` when `porsi_kena_idr` is `1` (`TC-ARITH-500001`). `TC-ARITH-500` has `porsi_kena_idr` `0` and tax `0`.

### 2.3 Band, cap, and withholding

The Rp 500.000.000 band is consumed only by the user's `usaha` transactions, sorted by `(tx_date, id)` ascending, with `tx_date <= as_of_date`. Spouse omzet does not enter the band (`spouse_in_band` is `false`). The transaction that crosses the band splits into `porsi_bebas_idr` and `porsi_kena_idr`. Same-day rows sort by id ascending. Ids are prefixed Crockford ULIDs, so that order is creation order. Swapping two same-day rows changes which row is marked as the split. It does not change the month totals. Later `usaha` transactions in that tax year are fully taxable. `pekerjaan_bebas`, `already_final`, and `non_object` do not consume the band and do not enter `tax_idr`.

```
prior_combined = user_prior(usaha + pekerjaan_bebas + already_final)
               + (spouse_aggregation_active ? spouse_prior(those three) : 0)

current_combined = user transactions through as_of in those three categories
                 + (spouse_aggregation_active ? spouse_current(those three) : 0)
```

`non_object` is in neither sum. Spouse profile totals are not also stored as rows in `transactions`.

Cap comparison is strict. Combined gross `>` `4_800_000_000` fails. Equality stays eligible.

- `prior_combined > 4_800_000_000` sets `scheme_eligibility_status` to `scheme_ineligible` for the whole current year. Every month has `tax_0_5_pct_idr` `0` and annotation `Fasilitas PPh Final 0,5% tidak berlaku (peredaran bruto tahun lalu melebihi Rp 4,8 miliar).`
- `current_combined > 4_800_000_000` sets only `next_year_ineligible` to `true`. The current-year 0,5% rate stays.

`prior_year_resolution_source` is one of `manual_profile`, `first_year_taxpayer`, `unverifiable`. This release accepts only tax year 2026, so no 2025 snapshot exists and a prior-year snapshot is not a source.

1. `is_new_taxpayer_current_year` true forces `first_year_taxpayer`, treats prior combined as `0`, and yields `scheme_eligible` even if prior-year numbers were sent.
2. Otherwise, six prior-year integers supplied by the client yield `manual_profile`.
3. Missing prior-year data with the new-taxpayer flag false yields `unverifiable`. The engine does not guess the cap. `scheme_eligibility_status` is `unverifiable` and `tax_0_5_pct_idr` is `0` with annotation that the prior-year gross is not on file.

Excess withholding stays on that month. `overwithheld_excess_idr` does not reduce tax in a later month.

Withholding:

```
withheld <= tax → sisa_bayar_idr = tax - withheld, overwithheld_excess_idr = 0, overwithheld_status = nihil
withheld > tax  → sisa_bayar_idr = 0, overwithheld_excess_idr = withheld - tax, overwithheld_status = belum_diperhitungkan
```

`withheld_tax_amount_idr` is `>= 0`. The engine does not assume a marketplace withholding rate.

### 2.4 Months array

On Bagian B, `as_of_date` is today in `Asia/Jakarta`. `months` and stored snapshots run from `YYYY-01` through that month. A transaction with `tx_date` later than today is stored and excluded until that date arrives. No November snapshot exists while today is still in October. On Bagian A, `as_of_date` is the value in the request. In both surfaces, transactions with `tx_date > as_of_date` are excluded. A month with no included transactions still has an object: money fields are `0`, `overwithheld_status` is `nihil`, `scheme_eligibility_status` copies the year status, and `input_hash` is the real digest of that month with an empty `transactions` list.

### 2.5 Errors

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Pesan Bahasa Indonesia yang menyebut apa yang salah dan apa yang harus dilakukan."
  }
}
```

`field_errors` is present only for field validation, as an object of field name to Indonesian text. Unknown ids owned by another account return `404`, not `403`.

### 2.6 Session and paid gate

- Cookie `kp_session`: `HttpOnly; SameSite=Lax; Path=/; Max-Age=43200`. `Secure` is set in production and omitted on plain HTTP localhost. `Max-Age` is the absolute lifetime from login.
- `POST /auth/login` returns the JWT string in the body only when the request header `X-Client-Type` is `non-browser`. Browser clients use the cookie. A script on `app.klasifipajak.id` can set that header; the web client must not.
- JWT `alg` is pinned to `HS256`. `none` and any other algorithm are rejected. Required claims are `sub`, `jti`, `iat`, and `exp`. `jti` is a UUID v4.
- `exp` is the absolute end: `iat + 12 hours` UTC. It does not move when the user stays active. Idle limit is 30 minutes from `sessions.last_seen_at`.
- Login inserts a new `sessions` row and a new `jti`. It does not extend or replace older sessions. An account may have at most 5 active sessions. The sixth login sets `revoked_at` on the row with the oldest `last_seen_at`.
- Every protected request decodes the JWT with `HS256` only, then loads `sessions` by `jti`. The call is rejected when the row is missing, `revoked_at` is set, `now_utc > expires_at_utc`, or `now_utc - last_seen_at` exceeds 30 minutes. A passing request writes `last_seen_at` only when the stored value is older than one minute.
- `401` `session_expired` means idle or absolute expiry. `401` `session_revoked` means this `jti` was revoked. Both responses clear `kp_session`. A bad signature or a missing `jti` is a generic `401` and does not use those codes.
- Logout revokes only the current `jti`. If that write fails, the response is `500` and the session stays valid.
- Password reset and account deletion set `revoked_at` on every session of that user.
- Paid gate: `paid_flag == true` AND `valid_until_utc IS NOT NULL` AND `now_utc <= valid_until_utc`. An empty `valid_until` is not paid.

### 2.7 Other enums

- `category`: `usaha`, `pekerjaan_bebas`, `already_final`, `non_object`.
- `source_channel`: `marketplace`, `corporate_client`, `retail`, `other`.
- `nib_status`: `has_nib`, `no_nib`, `unknown`.
- `marital_status`: `yes`, `no`, `unknown`.
- `entity_type`: `orang_pribadi` only.
- `nib_last_4`: exactly four digits `^[0-9]{4}$` when `nib_status` is `has_nib`. The stored value is those four digits. The display mask is nine asterisks plus those digits (`*********0123`). A longer NIB is rejected and is not stored.
- Duplicate invoice key, when `invoice_no_norm` is not null: `(user_id, client_name_norm, invoice_no_norm, amount_idr, tx_date)`. The same invoice number with a different amount or date is a second row. Empty invoice numbers are `NULL` and are not part of the key.
- Database: MySQL 8. Instants are `DATETIME(6)` in UTC, written by the application. Norm columns use `utf8mb4_bin`.
- Normalization of `client_name_norm` and `invoice_no_norm` runs in application code: `NFKC`, collapse whitespace, `casefold`. `PT` and `CV` stay. The database stores the result and does not casefold it.
- Email and username: trim for display. Uniqueness is `email_norm` and `username_norm` after trim and casefold, collation `utf8mb4_bin`. `User@Example.com` and `user@example.com` are one account.

AI classification quota does not reject `POST /transactions`. When the free limit (10) or the paid ceiling (200) is spent, the row is stored and classification goes to clarification with no model call. A model call first runs `UPDATE quota_counters SET ai_used = ai_used + 1 WHERE user_id = :u AND month_key = :m AND ai_used < :limit`. Zero rows means the quota is exhausted. The unit is refunded when the call produces no answer. Classifying the same transaction again does not reserve a second unit. Assistant limits are 15 (free) and 200 (paid) successful answers per `Asia/Jakarta` calendar month, reserved the same way.

---

## 3. Bagian A — engine on `127.0.0.1`

No session and no database. Mounted only for `development` and `test`.

### 3.1 `GET /health`

`200`:

```json
{ "status": "ok" }
```

### 3.2 `GET /ruleset`

`200`:

```json
{
  "ruleset_id": "pp20-2026-academic-1",
  "tax_year": 2026,
  "effective_date": "2026-09-26",
  "rate_numerator": 1,
  "rate_denominator": 200,
  "rate_str": "0.005",
  "free_band_idr": 500000000,
  "gross_cap_idr": 4800000000,
  "rounding_rule": "floor",
  "spouse_in_band": false,
  "spouse_in_cap": true,
  "kap_kjs": "411128-423"
}
```

`rate_str` is display-only.

### 3.3 `POST /snapshot`

Normative example. Spouse current-year usaha is `400000000`, which is different from spouse prior-year usaha `750000000`, so the two combined totals cannot be swapped without a failing test.

`prior_combined` = `1200000000 + 750000000` = `1950000000` (`scheme_eligible`).
`current_combined` = `1200000000 + 400000000` = `1600000000` (`next_year_ineligible` false).
Band split of the user's `1200000000` usaha: bebas `500000000`, kena `700000000`, tax `3500000`.

Request:

```json
{
  "tax_year": 2026,
  "as_of_date": "2026-01-31",
  "profile": {
    "entity_type": "orang_pribadi",
    "marital_status": "yes",
    "spouse_aggregation_active": true,
    "is_new_taxpayer_current_year": false,
    "spouse_current_year_usaha_omzet_idr": 400000000,
    "spouse_current_year_pekerjaan_bebas_omzet_idr": 0,
    "spouse_current_year_already_final_omzet_idr": 0,
    "prior_year_gross_user": {
      "usaha_idr": 1200000000,
      "pekerjaan_bebas_idr": 0,
      "already_final_idr": 0
    },
    "prior_year_gross_spouse": {
      "usaha_idr": 750000000,
      "pekerjaan_bebas_idr": 0,
      "already_final_idr": 0
    }
  },
  "transactions": [
    {
      "id": "tx-001",
      "tx_date": "2026-01-15",
      "amount_idr": 1200000000,
      "category": "usaha",
      "withheld_tax_amount_idr": 0
    }
  ]
}
```

`200`:

```json
{
  "tax_year": 2026,
  "as_of_date": "2026-01-31",
  "ruleset_id": "pp20-2026-academic-1",
  "effective_date": "2026-09-26",
  "rounding_rule": "floor",
  "scheme_eligibility_status": "scheme_eligible",
  "prior_year_resolution_source": "manual_profile",
  "prior_year_combined_gross_idr": 1950000000,
  "current_year_combined_gross_idr": 1600000000,
  "next_year_ineligible": false,
  "spouse_aggregation_active": true,
  "remaining_free_band_idr": 0,
  "months": [
    {
      "month": "2026-01",
      "input_hash": "v1:1d31077627dffd7d9e13276931a34e482a36f60fe1984f120f8dac28253d0090",
      "scheme_eligibility_status": "scheme_eligible",
      "usaha_omzet_idr": 1200000000,
      "porsi_bebas_idr": 500000000,
      "porsi_kena_idr": 700000000,
      "tax_0_5_pct_idr": 3500000,
      "withheld_tax_idr": 0,
      "sisa_bayar_idr": 3500000,
      "overwithheld_excess_idr": 0,
      "overwithheld_status": "nihil",
      "pekerjaan_bebas_omzet_idr": 0,
      "already_final_omzet_idr": 0,
      "non_object_omzet_idr": 0
    }
  ],
  "disclaimer": "DOKUMEN KERJA (WORKPAPER) — BUKAN SPT RESMI DAN BUKAN PRODUK DJP/CORETAX."
}
```

`as_of_date` is 31 January, so `months` has one element. That `input_hash` is the only normative digest in this document. See section 4.

`422` when `amount_idr` is not a strict integer or is `<= 0`, `withheld_tax_amount_idr` is `< 0`, `category` is outside the four values, `entity_type` is not `orang_pribadi`, a date is not a Jakarta calendar date, `tx_date` is outside 2026 or after `as_of_date`, or `nib` / money fields violate section 2. Messages are Indonesian field errors.

`500` when the ruleset file is missing a required key (`spouse_in_band`, `spouse_in_cap`, `free_band_idr`, `gross_cap_idr`, `rate_numerator`, `rate_denominator`, `rounding_rule`). The body is a generic Indonesian message with no stack trace.

---

## 4. Canonical `input_hash` (`v1:`)

Each month hashes its own inputs. Serialize one JSON object with recursively sorted keys, UTF-8, no whitespace, integers as integers, booleans as `true`/`false`, and dates as `YYYY-MM-DD`. Do not include `computed_at` or `rate_str`.

Object keys:

- `month`
- `profile_context`: `is_new_taxpayer_current_year`, `prior_year_gross_spouse`, `prior_year_gross_user`, `prior_year_resolution_source`, `spouse_aggregation_active`, `spouse_current_year_already_final_omzet_idr`, `spouse_current_year_pekerjaan_bebas_omzet_idr`, `spouse_current_year_usaha_omzet_idr`
- Each prior-year object has sorted keys `already_final_idr`, `pekerjaan_bebas_idr`, `usaha_idr`
- `ruleset`: `effective_date`, `free_band_idr`, `gross_cap_idr`, `rate_denominator`, `rate_numerator`, `rounding_rule`, `ruleset_id`, `spouse_in_band`, `spouse_in_cap`
- `tax_year`
- `transactions` sorted by `(tx_date, id)`, each with sorted keys `amount_idr`, `category`, `id`, `tx_date`, `withheld_tax_amount_idr`

SHA-256 those bytes. The field value is `v1:` plus 64 lowercase hex characters.

Normative input for January 2026 of the section 3.3 example:

```
{"month":"2026-01","profile_context":{"is_new_taxpayer_current_year":false,"prior_year_gross_spouse":{"already_final_idr":0,"pekerjaan_bebas_idr":0,"usaha_idr":750000000},"prior_year_gross_user":{"already_final_idr":0,"pekerjaan_bebas_idr":0,"usaha_idr":1200000000},"prior_year_resolution_source":"manual_profile","spouse_aggregation_active":true,"spouse_current_year_already_final_omzet_idr":0,"spouse_current_year_pekerjaan_bebas_omzet_idr":0,"spouse_current_year_usaha_omzet_idr":400000000},"ruleset":{"effective_date":"2026-09-26","free_band_idr":500000000,"gross_cap_idr":4800000000,"rate_denominator":200,"rate_numerator":1,"rounding_rule":"floor","ruleset_id":"pp20-2026-academic-1","spouse_in_band":false,"spouse_in_cap":true},"tax_year":2026,"transactions":[{"amount_idr":1200000000,"category":"usaha","id":"tx-001","tx_date":"2026-01-15","withheld_tax_amount_idr":0}]}
```

Normative digest: `v1:1d31077627dffd7d9e13276931a34e482a36f60fe1984f120f8dac28253d0090`

---

## 5. Bagian B — `/api/v1/*`

Protected routes require the session cookie or `Authorization: Bearer`. Paths below are relative to `/api/v1`.

Illustrative JSON in this section is not a hash vector. Where `input_hash` appears here, the 64 zeros are a placeholder.

### 5.1 `POST /auth/register`

Public. `email` and `username` are required. Both are trimmed. Uniqueness uses the casefolded form, so `User@Example.com` matches `user@example.com`. Password length is at least 10 characters, with no composition rules. No session is created.

```json
{
  "email": "user@example.com",
  "username": "adityaputra",
  "password": "PasswordMinimal10"
}
```

`201`:

```json
{
  "user_id": "usr_01J9X1A2B3",
  "email": "user@example.com",
  "username": "adityaputra",
  "created_at": "2026-10-18T10:00:00Z"
}
```

- `409` `IDENTIFIER_ALREADY_EXISTS`: "Surel atau nama pengguna sudah terdaftar."
- `422` `PASSWORD_TOO_SHORT`: "Kata sandi harus memiliki panjang minimal 10 karakter."

### 5.2 `POST /auth/login`

```json
{
  "identifier": "user@example.com",
  "password": "PasswordMinimal10"
}
```

`200` sets `kp_session`. Body:

```json
{
  "user_id": "usr_01J9X1A2B3",
  "expires_at": "2026-10-18T22:00:00Z"
}
```

Add `"token"` only for `X-Client-Type: non-browser`.

`401` `INVALID_CREDENTIALS`: "Identitas atau kata sandi tidak valid." The same message is used for an unknown identifier and a wrong password.

`429` `RATE_LIMITED`: "Terlalu banyak percobaan. Coba lagi dalam 15 menit." This applies to login and to `POST /auth/password-reset/request`. The limit is 5 requests for one normalized identifier, and 20 requests from one client IP, in any 15-minute window. The reset route checks the limit before it returns the generic message.

### 5.3 `POST /auth/logout`

`200` clears `kp_session` and revokes only this `jti`:

```json
{ "revoked": true }
```

`500` `REVOCATION_FAILED`: "Gagal membatalkan sesi pada basis data. Silakan coba lagi."

### 5.3.1 `GET /auth/me`

Session cookie. `200`:

```json
{
  "user_id": "usr_01J9X1A2B3",
  "email": "user@example.com",
  "username": "adityaputra"
}
```

`401` means there is no usable session. The browser calls this on load. There is no refresh endpoint.

### 5.3.2 `GET /auth/sessions`

Session cookie. `200` lists only this user's sessions. `current` is true for the `jti` of this request. JavaScript does not receive the raw `jti` as a value it must store. `device_label` is the browser family and OS.

```json
{
  "items": [
    {
      "id": "4f3c2a10-7b21-4d0e-9a55-1c0b6e8d4a21",
      "device_label": "Chrome di Windows",
      "created_at": "2026-10-18T10:00:00Z",
      "last_seen_at": "2026-10-18T10:20:00Z",
      "current": true
    }
  ]
}
```

### 5.3.3 `DELETE /auth/sessions/{id}`

Revokes one session of the caller by setting `revoked_at`. `200` is `{ "revoked": true }`. An id that is not one of this user's sessions is `404` `SESSION_NOT_FOUND`: "Sesi tidak ditemukan."

### 5.3.4 `DELETE /auth/sessions`

Revokes every session of the caller except the current `jti`. `200` is `{ "revoked_count": 2 }`. The current cookie stays valid.

### 5.4 `POST /auth/password-reset/request`

```json
{ "email": "user@example.com" }
```

`200` always, including when the email is unknown:

```json
{
  "message": "Jika surel terdaftar pada sistem, petunjuk atur ulang kata sandi telah dikirimkan."
}
```

The token is high-entropy, expires in 30 minutes, and is stored as SHA-256. The plaintext is not stored.

### 5.5 `POST /auth/password-reset/confirm`

```json
{
  "token": "rst_token_plaintext_abc",
  "new_password": "NewPasswordMinimal10"
}
```

The server compares the hash in constant time, consumes the token in the same transaction as the password update, and sets `revoked_at` on every session for that user, including the one that requested the reset. A second use returns `400`. The next request on any of those devices returns `401` `session_revoked`.

`200`:

```json
{
  "message": "Kata sandi berhasil diperbarui. Seluruh sesi aktif telah dibatalkan."
}
```

- `400` `TOKEN_INVALID_OR_EXPIRED`: "Token atur ulang kata sandi tidak sah atau telah kedaluwarsa."
- `422` `PASSWORD_TOO_SHORT`: "Kata sandi baru harus memiliki panjang minimal 10 karakter."

### 5.6 `DELETE /account`

```json
{ "confirmation": "HAPUS AKUN SAYA" }
```

The confirmation string is exact. Order of writes: set `user_id` and other personal fields to null on `subscription_orders` and `payment_events`, then delete `sessions`, `month_snapshots`, `classification_events`, `receipt_images`, `transactions`, `profiles`, quota rows, and `users`.

`200`:

```json
{
  "deleted": true,
  "message": "Seluruh data profil, transaksi, citra, dan cuplikan pajak Anda telah dihapus secara permanen."
}
```

`422` `CONFIRMATION_TEXT_MISMATCH`: "Teks konfirmasi penghapusan akun tidak sesuai."

### 5.7 `GET /profiles/{tax_year}`

`200` returns the profile, `version`, masked NIB, the six prior-year integers, the three spouse current-year integers, `is_new_taxpayer_current_year`, and `audit_trail` entries of `changed_at`, `field`, `old_value`, `new_value`.

`404` `PROFILE_NOT_FOUND`: "Profil untuk tahun pajak yang dipilih belum dibuat."

### 5.8 `PUT /profiles/{tax_year}`

Accepts the same business fields as the GET body, plus `version`, with `nib_last_4` instead of `nib_masked`. Rejects `entity_type` other than `orang_pribadi` and a `nib_last_4` that is not four digits. The update matches `version` and then increments it.

`200` returns the saved profile, including the new `version`. Changing spouse aggregation, prior-year totals, spouse current-year totals, or the new-taxpayer flag marks year snapshots stale and recalculates them inside the user-row lock. A name-only change records an audit row and leaves snapshot hashes unchanged.

`409` `VERSION_CONFLICT`: "Data ini sudah diubah di perangkat lain. Muat ulang, lalu simpan lagi."

- `422` `INVALID_NIB_FORMAT`: "Kolom nib_last_4 harus berupa tepat 4 digit angka."
- `422` `ENTITY_TYPE_NOT_SUPPORTED`: "KlasifiPajak v1 hanya mendukung wajib pajak orang_pribadi."

### 5.9 `POST /transactions/reclassify`

```json
{ "transaction_ids": ["tx_01J9X3A9B2", "tx_01J9X3A9B3"] }
```

The call is atomic. One unknown id fails the whole request with no writes.

`200`:

```json
{
  "reclassified_count": 2,
  "results": [
    {
      "id": "tx_01J9X3A9B2",
      "old_category": "usaha",
      "new_category": "usaha",
      "source": "rule"
    },
    {
      "id": "tx_01J9X3A9B3",
      "old_category": "pekerjaan_bebas",
      "new_category": "usaha",
      "source": "rule"
    }
  ]
}
```

`404` `TRANSACTION_NOT_FOUND`: "Satu atau lebih transaksi tidak ditemukan pada akun Anda."

### 5.10 `GET /transactions`

Query: `page` (default 1), `per_page` (default 20, max 100), `tax_year`, `month` (`YYYY-MM`), `client_name` (partial), `invoice_no` (exact on the normalized value).

`200` returns `items` and `pagination` (`current_page`, `per_page`, `total_items`, `total_pages`). Each item includes `id`, `version`, `tx_date`, `client_name`, `invoice_no`, `amount_idr`, `withheld_tax_amount_idr`, `source_channel`, `category`, and `source`. There is no transaction status column.

### 5.11 `POST /transactions`

```json
{
  "amount_idr": 12500000,
  "tx_date": "2026-10-15",
  "client_name": "PT Sumber Makmur",
  "description": "Penjualan sembako",
  "invoice_no": "INV-2026-104",
  "withheld_tax_amount_idr": 62500,
  "source_channel": "corporate_client"
}
```

Requires a profile for that tax year with `nib_status` set. Runs normalization, the duplicate key, and classification. Spending the AI quota still returns `201` and sets the classification path to clarification.

`201` includes `id`, the stored fields, and `classification` (`category`, `source`, `confidence`, `rule_id`, `requires_clarification`). A `tx_date` through 31 December 2026 is accepted even when it is after today in Jakarta. It stays out of snapshots until that date is today or earlier.

- `409` `DUPLICATE_INVOICE_TRANSACTION`: "Nomor faktur ini sudah tercatat untuk klien, nominal, dan tanggal yang sama."
- `422` `NIB_STATUS_NOT_CONFIGURED`: "Status NIB untuk tahun pajak berjalan harus diisi sebelum mencatat transaksi pertama."
- `422` `INVALID_DATE_RANGE`: "Tanggal transaksi di luar tahun pajak 2026."
- `422` `INVALID_SOURCE_CHANNEL`: "Saluran sumber tidak dikenal."

### 5.12 `PUT /transactions/{id}`

Same body shape as create, plus `version`. Recalculation starts at the earlier of the old `tx_date` month and the new `tx_date` month, and continues through December, inside the user-row lock. Moving a row from October to March therefore rebuilds March through December, because the free band is consumed in order. The update matches `version` and then increments it.

`409` `VERSION_CONFLICT`: "Data ini sudah diubah di perangkat lain. Muat ulang, lalu simpan lagi."

`200` returns the updated transaction.

- `404` `TRANSACTION_NOT_FOUND` for an id this account does not own.
- `409` `DUPLICATE_INVOICE_TRANSACTION`.

### 5.13 `DELETE /transactions/{id}`

`200`:

```json
{ "deleted": true, "id": "tx_01J9X3A9B2" }
```

`404` `TRANSACTION_NOT_FOUND` when the id is missing or belongs to another account. Related classification rows are deleted and snapshots from that month are recalculated.

### 5.14 `POST /transactions/ocr-upload`

Paid gate. `multipart/form-data` field `file`, JPEG or PNG, at most 8 MB. Does not create a transaction. An image that is never confirmed is deleted, row and bytes, 7 days after upload. A confirmed image stays until its transaction or the account is deleted. A lapsed paid account keeps confirmed images and cannot upload another.

`200`:

```json
{
  "image_id": "img_01J9X5M8P1",
  "candidate_fields": {
    "amount_idr": 450000,
    "tx_date": "2026-10-18",
    "client_name": "Toko Bahan Pokok",
    "invoice_no": "STRUK-8812"
  }
}
```

- `403` `PAID_SUBSCRIPTION_REQUIRED`: "Fitur unggah struk OCR hanya tersedia bagi pengguna berbayar aktif."
- `422` `IMAGE_EXCEEDS_SIZE_LIMIT`: "Ukuran berkas melebihi batas maksimum 8 MB."
- `422` `IMAGE_TYPE_NOT_SUPPORTED`: "Berkas harus berupa JPEG atau PNG."

### 5.15 `POST /transactions/ocr-confirm`

Paid gate. Body contains `image_id` and the confirmed fields (`confirmed_amount_idr`, `confirmed_tx_date`, `confirmed_client_name`, `confirmed_description`, `confirmed_invoice_no`, `withheld_tax_amount_idr`, `source_channel`). The stored row uses the confirmed values and follows the same date, duplicate, NIB, and classification rules as `POST /transactions`.

`201` returns the captured transaction and `image_id`.

### 5.16 `GET /transactions/{id}/clarification`

`200`:

```json
{
  "transaction_id": "tx_01J9X8K1M0",
  "question": "Untuk transaksi dari PT Kreatif Nusantara sebesar Rp 8.000.000 pada 2026-10-16, apakah penerimaan ini berasal dari kegiatan usaha toko/dagang atau honorarium pekerjaan bebas?",
  "options": [
    { "value": "usaha", "label": "Penjualan dagang / usaha UMKM (Objek 0,5%)" },
    {
      "value": "pekerjaan_bebas",
      "label": "Jasa profesional / pekerjaan bebas (Bukan objek 0,5%)"
    },
    { "value": "already_final", "label": "Penghasilan sudah dikenai PPh final tersendiri" },
    { "value": "non_object", "label": "Bukan objek pajak (transfer modal / pengembalian)" }
  ]
}
```

`404` when the id is not owned by the caller.

### 5.17 `POST /transactions/{id}/clarification`

```json
{ "category": "usaha" }
```

`200` returns `id`, `category`, `source` `user_clarification`, `version`, and `updated_at`, then recalculates snapshots. The write increments `version`.

`422` `INVALID_CATEGORY_ENUM`: "Pilihan kategori harus salah satu dari: usaha, pekerjaan_bebas, already_final, non_object."

### 5.18 `POST /transactions/{id}/override`

```json
{
  "new_category": "pekerjaan_bebas",
  "note": "Revisi kategori: honor narasumber pelatihan"
}
```

`note` is optional. No model call. `source` is `user_override`. `200` returns the updated category, source, and `version`. The write increments `version`. `404` if the id is not owned.

### 5.19 `GET /transactions/{id}/audit-trail`

`200` events include `timestamp`, `source`, `rule_id` or citation text, `assigned_category` or `old_category` and `new_category`, `note`, `ytd_usaha_omzet_before_idr`, `ytd_usaha_omzet_after_idr`, `ruleset_id`, and `effective_date`.

### 5.20 `GET /tax/dashboard`

Query `tax_year`. `200` includes `metadata` (`ruleset_id`, `effective_date`, `rounding_rule`, `disclaimer`), `thresholds`, and `monthly_summaries`.

Thresholds include:

- `pita_500_juta`: `limit_idr`, `ytd_usaha_omzet_idr`, `remaining_free_band_idr`, `split_month`, `annotation`
- `eligibility_prior_year_cap_4_8m`: `limit_idr`, `combined_prior_year_gross_idr`, `resolution_source`, `status`
- `monitoring_current_year_cap_4_8m`: `limit_idr`, `ytd_usaha_omzet_idr`, `ytd_pekerjaan_bebas_omzet_idr`, `ytd_already_final_omzet_idr`, `spouse_current_year_usaha_omzet_idr`, `spouse_current_year_pekerjaan_bebas_omzet_idr`, `spouse_current_year_already_final_omzet_idr`, `ytd_combined_gross_idr`, `next_year_ineligible`
- `pasal_58`: `spouse_aggregation_active`, `badge_label`

`ytd_combined_gross_idr` equals the section 2.3 current-year formula. An illustration with usaha YTD `520000000`, pekerjaan bebas YTD `25000000`, already-final YTD `0`, and spouse current usaha `150000000` has combined `695000000`.

Each month includes `scheme_eligibility_status`, money fields, `overwithheld_status`, and `input_hash`. When the year is `scheme_ineligible`, `tax_0_5_pct_idr` is `0` and the month carries the facility annotation from section 2.3.

The `input_hash` in any dashboard example other than section 4 is not a test vector.

### 5.21 `GET /tax/snapshots/{tax_year}/{month}`

`200` returns one month: `status` `berlaku` or `usang`, `ruleset_id`, `effective_date`, `rounding_rule`, `scheme_eligibility_status`, `input_hash`, the money fields, `pekerjaan_bebas_omzet_idr`, `already_final_omzet_idr`, `non_object_omzet_idr`, and `overwithheld_status`.

`404` `SNAPSHOT_NOT_FOUND`: "Cuplikan bulan yang diminta tidak ada."

### 5.22 `POST /tax/snapshots/{tax_year}/recalculate`

`200`:

```json
{
  "recalculated_tax_year": 2026,
  "recalculated_months_count": 10,
  "status": "berlaku"
}
```

Only months marked `usang` are recomputed.

### 5.23 `GET /recap/{tax_year}`

`200` returns L3-B Bagian A totals for usaha (`total_usaha_omzet_idr`, `total_porsi_bebas_idr`, `total_porsi_kena_idr`, `total_tax_0_5_pct_idr`, `total_withheld_tax_idr`, `total_sisa_bayar_idr`), `total_pekerjaan_bebas_omzet_idr`, `kap_kjs`, `scheme_eligibility_status`, `next_year_ineligible`, and the workpaper disclaimer. There is no Pasal 17 amount.

### 5.24 `POST /recap/{tax_year}/pdf`

Paid gate. `200` streams `application/pdf` with `Content-Disposition: attachment; filename="Workpaper_PPh_Final_2026.pdf"`. The file is not stored as a download archive. The words `WORKPAPER` / `DOKUMEN KERJA` and the not-an-SPT statement are at least 10 pt.

`403` `PAID_SUBSCRIPTION_REQUIRED`: "Fitur unduh berkas workpaper PDF hanya tersedia bagi pengguna berbayar aktif."

### 5.25 `POST /assistant/query`

```json
{
  "question": "Berapa sisa bayar pajak saya untuk bulan Oktober 2026?"
}
```

Read-only tools. No conversation archive. Refusal of general tax-avoidance advice uses a consultant template and invents no figures.

`200`:

```json
{
  "answer": "Sisa bayar pajak PPh Final 0,5% Anda untuk masa Oktober 2026 adalah Rp 37.500.",
  "citations": ["Cuplikan Masa Pajak 2026-10"],
  "quota_remaining": 14
}
```

- `429` `FREE_CHAT_QUOTA_EXHAUSTED`: "Batas kuota asisten gratis Anda untuk bulan ini telah tercapai (15 jawaban). Silakan berlangganan untuk menambah kuota."
- `429` `PAID_CHAT_CEILING_EXHAUSTED`: "Plafon wajar asisten akun berbayar Anda untuk bulan ini telah tercapai (200 jawaban)."

### 5.26 `GET /quotas`

`200`:

```json
{
  "month_key": "2026-10",
  "timezone": "Asia/Jakarta",
  "reset_timestamp_utc": "2026-10-31T17:00:00Z",
  "ai_classification": { "used": 4, "limit": 10, "status": "active" },
  "assistant_chat": { "used": 1, "limit": 15, "status": "active" }
}
```

`reset_timestamp_utc` `2026-10-31T17:00:00Z` is 1 November 2026 00:00 WIB. WIB does not observe daylight-saving time, so the offset stays +7. Paid accounts report `limit` `200` on both counters. `status` is `active` or `exhausted`.

### 5.27 `GET /subscriptions/status`

`200` includes `subscription_tier` (`gratis`, `pending`, `berbayar`, `kedaluwarsa`), `paid_flag`, `valid_until_utc`, `valid_until_local` in WIB, and `available_plans`.

The only plan in this release is `monthly_25k`, duration `30` days, price `25000`. A UTC instant `2026-11-18T10:00:00Z` displays as `2026-11-18 17:00:00 WIB`.

### 5.28 `POST /subscriptions/orders`

```json
{ "plan_id": "monthly_25k" }
```

At most one `pending` row exists per user and plan. The call locks that row. If it is inside 24 hours, the response is `200` and reuses it. If it is older, the same transaction marks it `expire` and inserts a new row, which returns `201`. A concurrent insert that loses the unique pending slot retries the read. Expiry is `now_utc + 24 hours`. `payment_url` is an opaque gateway URL. This contract does not name a vendor.

```json
{
  "order_id": "ord_20261018_01",
  "amount_idr": 25000,
  "status": "pending",
  "payment_url": "https://gateway.example.com/pay/ord_20261018_01",
  "expires_at_utc": "2026-10-19T10:00:00Z"
}
```

### 5.29 `GET /subscriptions/orders`

`200` returns the caller's orders: `order_id`, `plan_id`, `amount_idr`, `status`, `created_at`. No payment-instrument data.

### 5.30 `POST /webhooks/payment`

Header `X-Webhook-Signature` is lowercase hex HMAC-SHA256. The signed bytes are UTF-8:

```
order_id || 0x0A || status || 0x0A || amount_str
```

`amount_str` is the decimal digits of `gross_amount_idr` with no separators and no decimal point. The newline is the single byte `0x0A`, not the two characters `\` and `n`.

Example secret `example-webhook-secret`, canonical text `ord_20261018_01`, newline, `settlement`, newline, `25000`.

Signature: `595fe79b13dd2969fcc8497196333e356b23d811b638be78412c221f51625d1d`

Body:

```json
{
  "order_id": "ord_20261018_01",
  "status": "settlement",
  "gross_amount_idr": 25000,
  "transaction_time": "2026-10-18T10:30:00Z"
}
```

Transitions:

- `pending` may become `settlement`, `expire`, or `fail`.
- `settlement` may also follow `expire` or `fail`. A late payment still activates.
- `expire` and `fail` do not follow `settlement`, and they do not replace each other. The first of those two statuses stays.
- A later `pending` does not change `orders.status` and does not clear `paid_flag`.
- `orders.status` does not move backward. An ignored notification still returns `200`.
- The same `(order_id, status)` returns `200` with `idempotent_duplicate` true and does not add days again.
- A valid new `settlement` sets `valid_until = max(now_utc, current_valid_until_utc) + 30 days`.
- `gross_amount_idr` must equal the order amount.

`200`:

```json
{ "acknowledged": true, "idempotent_duplicate": false }
```

- `401` `INVALID_WEBHOOK_SIGNATURE`: "Tanda tangan webhook pembayaran tidak sah."
- `400` `ORDER_AMOUNT_MISMATCH`: "Nominal pembayaran pada notifikasi tidak cocok dengan pesanan."

### 5.31 `POST /test-support/subscription-override`

Bound to `127.0.0.1` and `APP_ENV=test` only. Any other environment or interface returns `404` with an empty body. No extra login. Body: `user_id`, `paid_flag`, `valid_until`. `200` echoes `updated`, `paid_flag`, and `valid_until`.

### 5.32 `POST /test-support/password-reset-token`

Same bind and `404` rule as 5.31. Body: `email`. `200` returns `reset_token` and `expires_at_utc` without sending mail. The token is stored as SHA-256 and is single-use through 5.5.
