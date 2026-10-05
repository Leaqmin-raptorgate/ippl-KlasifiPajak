# Security Policy

## Supported Versions

This project is a pre-1.0 university course project under active development.
Only the latest commit on `main` is supported with security fixes; there are no
maintained release branches.

| Version         | Supported |
| --------------- | --------- |
| `main` (latest) | ✅        |
| Anything else   | ❌        |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Instead, report it privately using GitHub's private vulnerability reporting
feature:

<https://github.com/Leaqmin-raptorgate/ippl-KlasifiPajak/security/advisories/new>

When reporting, please include:

- The affected component (e.g. a specific API route, the payment webhook
  handler, account isolation).
- The version or commit SHA you tested against.
- Steps to reproduce, and any proof-of-concept if available.
- The potential impact as you understand it.

This is a student project without a dedicated security team, so response times
are best-effort. We will acknowledge reports as soon as we're able and keep you
updated as we investigate and fix the issue.

## Scope

**In scope:**

- Account isolation — any way to read or modify another user's transactions,
  classifications, profiles, or subscription state (every query must be scoped
  by `user_id`).
- The payment gateway integration — webhook signature verification, tampered
  `gross_amount`, order status escalation, and whether any PAN, CVV, or bank
  account data can reach storage or logs.
- PII handling — NIB, email, names, and uploaded images appearing in logs,
  URLs, error messages, or responses where they should not.
- Injection and input handling in the API layer and any raw SQL.
- Secrets — any gateway key or model API key that could leak into the repo,
  logs, or client-visible responses.

**Out of scope:**

- Vulnerabilities in third-party dependencies — please report those directly to
  the upstream project.
- Incorrect tax figures — that is a correctness bug, not a security
  vulnerability; please open a regular bug report instead.
