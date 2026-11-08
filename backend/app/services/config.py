"""Operational configuration with an audit trail (FR-44, FR-50)."""

from sqlalchemy.orm import Session

from app.models import AppConfig, ConfigChangeLog
from app.security import new_id, now_utc

DEFAULTS = {"cap_warning_percent": "80", "T_rule": "0.80", "T_ai": "0.70"}


def get_config(db: Session, key: str) -> str:
    """Return a configured value, falling back to the documented default."""
    row = db.get(AppConfig, key)
    return row.value if row else DEFAULTS[key]


def set_config(db: Session, key: str, value: str, actor: str) -> None:
    """Persist a configuration change and its actor in one transaction."""
    if key not in DEFAULTS or not actor:
        raise ValueError("Unknown configuration key or missing actor")
    number = float(value)
    if not (0 <= number <= (100 if key == "cap_warning_percent" else 1)):
        raise ValueError("Configuration value out of range")
    if key == "cap_warning_percent" and not number.is_integer():
        raise ValueError("Warning percentage must be an integer")
    row = db.get(AppConfig, key, with_for_update=True)
    old = row.value if row else DEFAULTS[key]
    if old == value:
        return
    now = now_utc()
    if row is None:
        row = AppConfig(key=key, value=value, updated_at_utc=now)
        db.add(row)
        db.flush()
    else:
        row.value = value
        row.updated_at_utc = now
    db.add(
        ConfigChangeLog(
            id=new_id("cfg_"),
            config_key=key,
            old_value=old,
            new_value=value,
            changed_at_utc=now,
            actor=actor,
        )
    )
    db.commit()
