# Code review

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14 RFC 2119 RFC 8174 when, and only when, they appear in all capitals, as shown here.

A review reports findings. It does not fix them.

## Severity

| Severity  | Meaning                                                                    |
| --------- | -------------------------------------------------------------------------- |
| `blocker` | A MUST rule is broken. The change is not shippable as it stands.           |
| `high`    | A correctness, security, or isolation problem. Must be fixed before merge. |
| `medium`  | A real defect that would confuse or mislead a reader. Fix it.              |
| `low`     | A style or clarity issue with no behavioural consequence. Fix or defer.    |
| `nit`     | Cosmetic. A matter of taste.                                               |

## Nit cap

A review carries at most **three nit findings**. More than that means the code
is not review-ready: fix the nits first, then ask for review. Nits are
never blockers.

## Review checklist

- Does it violate an invariant in `AGENTS.md`?
- Does a tax figure have a sourced test, or a `TODO` where it does not?
- Does the layering hold? `app/engine/` imports no framework; `app/api/` runs no
  query; a service owns its transaction.
- Is every query scoped by `user_id`?
- Does every error carry a code?
- Are docs and code in the same change?
- Is the commit atomic?
