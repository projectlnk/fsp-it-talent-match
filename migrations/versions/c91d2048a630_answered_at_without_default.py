"""Align unanswered timestamps with the nullable ORM field; preserve existing rows."""
from alembic import op
import sqlalchemy as sa

revision = "c91d2048a630"
down_revision = "75c8b36a9021"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("test_answers", "answered_at", server_default=None,
                    existing_type=sa.DateTime(timezone=True), existing_nullable=True)


def downgrade():
    op.alter_column("test_answers", "answered_at", server_default=sa.text("now()"),
                    existing_type=sa.DateTime(timezone=True), existing_nullable=True)
