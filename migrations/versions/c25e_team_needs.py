"""Saved multi-position templates over the existing matching service."""
from alembic import op
import sqlalchemy as sa

revision = 'c25e_needs'
down_revision = 'b14d_reads'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('team_need_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employer_id', sa.Integer(), sa.ForeignKey('employer_profiles.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_team_need_templates_employer_id', 'team_need_templates', ['employer_id'])
    op.create_table('team_need_positions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('team_need_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('filters', sa.JSON(), nullable=False),
        sa.UniqueConstraint('template_id', 'ordinal', name='one_team_position_order'))
    op.create_index('ix_team_need_positions_template_id', 'team_need_positions', ['template_id'])


def downgrade():
    op.drop_table('team_need_positions')
    op.drop_table('team_need_templates')
