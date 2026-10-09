"""Explicit candidate consent for employer search; existing profiles stay private."""
from alembic import op
import sqlalchemy as sa

revision = "75c8b36a9021"
down_revision = "8f70f2f704de"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("candidate_profiles", sa.Column("is_searchable", sa.Boolean(), nullable=False, server_default=sa.false()))

def downgrade():
    op.drop_column("candidate_profiles", "is_searchable")
