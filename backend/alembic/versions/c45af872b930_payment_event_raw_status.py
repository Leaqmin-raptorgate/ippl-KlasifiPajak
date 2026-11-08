"""Record raw gateway statuses independently of normalized transitions.

Revision ID: c45af872b930
Revises: b19e6a25c70a
"""

import sqlalchemy as sa

from alembic import op

revision = "c45af872b930"
down_revision = "b19e6a25c70a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_events", sa.Column("raw_status", sa.String(255), nullable=False, server_default="")
    )
    op.execute("UPDATE payment_events SET raw_status = status")
    op.alter_column(
        "payment_events",
        "raw_status",
        existing_type=sa.String(255),
        server_default=None,
        existing_nullable=False,
    )
    op.drop_constraint("uq_payment_events_order_status", "payment_events", type_="unique")
    op.create_unique_constraint(
        "uq_payment_events_order_raw_status", "payment_events", ["order_id", "raw_status", "status"]
    )


def downgrade() -> None:
    # Refuse downgrade if distinct raw events share a normalized status: doing
    # so would otherwise discard recorded payment history.
    op.drop_constraint("uq_payment_events_order_raw_status", "payment_events", type_="unique")
    op.create_unique_constraint(
        "uq_payment_events_order_status", "payment_events", ["order_id", "status"]
    )
    op.drop_column("payment_events", "raw_status")
