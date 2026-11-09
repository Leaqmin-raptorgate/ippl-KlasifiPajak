"""Delete expired receipt images that no transaction references."""

from __future__ import annotations


def main() -> int:
    """Run one purge and print how many rows were removed."""
    from app.db import SessionLocal
    from app.services.receipts import purge_expired_receipts

    db = SessionLocal()
    try:
        removed = purge_expired_receipts(db)
    finally:
        db.close()
    print(removed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
