"""Keep an unanswered new-taxpayer flag null, and one receipt per transaction.

Rows stored before this revision stay 0, an explicit false. They do not
become unanswered, so they never receive new_taxpayer_unknown guidance.
Downgrade writes a NULL answer back to 0 before the column is NOT NULL again.

Revision ID: d8f0a1c64e27
Revises: c45af872b930
"""

import sqlalchemy as sa

from alembic import op

revision = "d8f0a1c64e27"
down_revision = "c45af872b930"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Refuse before any DDL. MySQL commits each ALTER, so a later failure
    # would leave the new-taxpayer column nullable.
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT image_id FROM transactions "
                "WHERE image_id IS NOT NULL "
                "GROUP BY image_id HAVING COUNT(*) > 1"
            )
        )
        .fetchall()
    )
    if duplicates:
        named = ", ".join(str(row[0]) for row in duplicates)
        raise RuntimeError(f"duplicate transaction image_id values: {named}")
    op.alter_column(
        "profiles",
        "is_new_taxpayer_current_year",
        existing_type=sa.Boolean(),
        nullable=True,
    )
    # The foreign key may be using the old index. Create the unique one first.
    op.create_index("uq_transactions_image_id", "transactions", ["image_id"], unique=True)
    op.drop_index("ix_transactions_image_id", table_name="transactions")


def downgrade() -> None:
    op.create_index("ix_transactions_image_id", "transactions", ["image_id"], unique=False)
    op.drop_index("uq_transactions_image_id", table_name="transactions")
    op.execute(
        sa.text(
            "UPDATE profiles SET is_new_taxpayer_current_year = 0 "
            "WHERE is_new_taxpayer_current_year IS NULL"
        )
    )
    op.alter_column(
        "profiles",
        "is_new_taxpayer_current_year",
        existing_type=sa.Boolean(),
        nullable=False,
    )
