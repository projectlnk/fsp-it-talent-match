"""Explicit invitation withdrawal, retaining response and chat history."""
from alembic import op
import sqlalchemy as sa

revision = 'f82b_revoke'
down_revision = 'e71a_activity'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE offer_status ADD VALUE IF NOT EXISTS 'REVOKED'")
    op.add_column('offers', sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    # PostgreSQL enum values cannot safely be removed with live revoked rows.
    raise RuntimeError('Restore a pre-migration database backup for downgrade; do not discard withdrawal history')
