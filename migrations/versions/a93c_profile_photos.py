"""One sanitized profile photograph per candidate/company."""
from alembic import op
import sqlalchemy as sa
revision = 'a93c_photos'
down_revision = 'f82b_revoke'
branch_labels = None
depends_on = None

def upgrade():
    for table in ('candidate_profiles','employer_profiles'):
        op.add_column(table, sa.Column('photo_data',sa.LargeBinary(),nullable=True))
        op.add_column(table, sa.Column('photo_version',sa.String(32),nullable=True))

def downgrade():
    for table in ('employer_profiles','candidate_profiles'):
        op.drop_column(table,'photo_version')
        op.drop_column(table,'photo_data')
