"""Support long outages and time-window event queries."""

from alembic import op
import sqlalchemy as sa

revision = "0003_history_queries"
down_revision = "0002_versioned_engine"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "execution_attempts", "duration_ms", schema="durable", type_=sa.BigInteger()
    )
    op.create_index(
        "ix_events_created", "execution_events", ["created_at"], schema="durable"
    )


def downgrade():
    op.drop_index("ix_events_created", table_name="execution_events", schema="durable")
    op.alter_column(
        "execution_attempts", "duration_ms", schema="durable", type_=sa.Integer()
    )
