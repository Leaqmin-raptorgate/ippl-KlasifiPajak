"""Allow unanswered prior-year amounts and record spouse tax status.

Revision ID: b19e6a25c70a
Revises: 76fcdbc4af30
"""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

from alembic import op

revision = "b19e6a25c70a"
down_revision = "76fcdbc4af30"
branch_labels = None
depends_on = None

_FIELDS = (
    "prior_user_usaha_idr",
    "prior_user_pekerjaan_bebas_idr",
    "prior_user_already_final_idr",
    "prior_spouse_usaha_idr",
    "prior_spouse_pekerjaan_bebas_idr",
    "prior_spouse_already_final_idr",
)


def upgrade() -> None:
    op.add_column("users", sa.Column("ai_consent_at", DATETIME(fsp=6), nullable=True))
    for name in ("has_selected_article_17", "has_sole_proprietor_company", "receives_salary"):
        op.add_column("profiles", sa.Column(name, sa.Boolean(), nullable=True))
    op.create_table(
        "app_config",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("updated_at_utc", DATETIME(fsp=6), nullable=False),
    )
    op.create_table(
        "config_change_log",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("config_key", sa.String(64), sa.ForeignKey("app_config.key"), nullable=False),
        sa.Column("old_value", sa.String(255)),
        sa.Column("new_value", sa.String(255), nullable=False),
        sa.Column("changed_at_utc", DATETIME(fsp=6), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
    )
    for field in _FIELDS:
        op.alter_column("profiles", field, existing_type=sa.BigInteger(), nullable=True)
    op.add_column("profiles", sa.Column("snapshot_checked_through", sa.Date(), nullable=True))
    op.add_column(
        "profiles",
        sa.Column("spouse_tax_status", sa.String(16), nullable=False, server_default="unknown"),
    )


def downgrade() -> None:
    op.drop_table("config_change_log")
    op.drop_table("app_config")
    for name in ("has_selected_article_17", "has_sole_proprietor_company", "receives_salary"):
        op.drop_column("profiles", name)
    op.drop_column("users", "ai_consent_at")
    op.drop_column("profiles", "spouse_tax_status")
    op.drop_column("profiles", "snapshot_checked_through")
    for field in _FIELDS:
        op.execute(sa.text(f"UPDATE profiles SET {field} = 0 WHERE {field} IS NULL"))
        op.alter_column("profiles", field, existing_type=sa.BigInteger(), nullable=False)
