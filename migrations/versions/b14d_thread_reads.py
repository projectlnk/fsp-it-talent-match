"""Persist independent read cursors for message notifications."""
from alembic import op
import sqlalchemy as sa

revision = 'b14d_reads'
down_revision = 'a93c_photos'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('career_thread_reads',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('employer_id', sa.Integer(), sa.ForeignKey('employer_profiles.id'), primary_key=True),
        sa.Column('candidate_id', sa.Integer(), sa.ForeignKey('candidate_profiles.id'), primary_key=True),
        sa.Column('last_message_id', sa.Integer(), nullable=False))
    # Old histories have no reliable read state. Start from their current end;
    # do not report all pre-release messages as new or modify message records.
    op.execute("""
        INSERT INTO career_thread_reads (user_id, employer_id, candidate_id, last_message_id)
        SELECT e.user_id, m.employer_id, m.candidate_id, MAX(m.id)
        FROM career_messages m JOIN employer_profiles e ON e.id = m.employer_id
        GROUP BY e.user_id, m.employer_id, m.candidate_id
        UNION
        SELECT c.user_id, m.employer_id, m.candidate_id, MAX(m.id)
        FROM career_messages m JOIN candidate_profiles c ON c.id = m.candidate_id
        GROUP BY c.user_id, m.employer_id, m.candidate_id
    """)


def downgrade():
    op.drop_table('career_thread_reads')
