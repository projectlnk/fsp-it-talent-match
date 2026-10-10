"""Persistent hiring workflows and isolated demo clock."""
from alembic import op
import sqlalchemy as sa
revision = 'd42e910career'
down_revision = 'c91d2048a630'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('career_opportunities',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('employer_id', sa.Integer(), sa.ForeignKey('employer_profiles.id'), primary_key=False, nullable=False),
        sa.Column('kind', sa.String(20), primary_key=False, nullable=False),
        sa.Column('title', sa.String(255), primary_key=False, nullable=False),
        sa.Column('description', sa.Text(), primary_key=False, nullable=False),
        sa.Column('specialization', sa.String(100), primary_key=False, nullable=False),
        sa.Column('grade', sa.String(50), primary_key=False, nullable=False),
        sa.Column('skills', sa.Text(), primary_key=False, nullable=False),
        sa.Column('salary_from', sa.Integer(), primary_key=False, nullable=False),
        sa.Column('salary_to', sa.Integer(), primary_key=False, nullable=False),
        sa.Column('work_format', sa.String(20), primary_key=False, nullable=False),
        sa.Column('contact_method', sa.String(255), primary_key=False, nullable=False),
        sa.Column('status', sa.String(20), primary_key=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), primary_key=False, nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), primary_key=False, nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), primary_key=False, nullable=True),
        sa.Column('fingerprint', sa.String(64), primary_key=False, nullable=False),
        sa.Column('demo_set', sa.String(64), primary_key=False, nullable=True),
        sa.CheckConstraint('salary_from >= 0 AND salary_to >= salary_from', name=op.f('ck_career_opportunities_career_salary_range')),
    )
    op.create_index('ix_career_opportunities_demo_set', 'career_opportunities', ['demo_set'])
    op.create_index('ix_career_opportunities_employer_id', 'career_opportunities', ['employer_id'])
    op.create_index('ix_career_opportunities_fingerprint', 'career_opportunities', ['fingerprint'])
    op.create_index('ix_career_opportunities_status', 'career_opportunities', ['status'])
    op.create_table('job_applications',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('opportunity_id', sa.Integer(), sa.ForeignKey('career_opportunities.id'), primary_key=False, nullable=False),
        sa.Column('candidate_id', sa.Integer(), sa.ForeignKey('candidate_profiles.id'), primary_key=False, nullable=False),
        sa.Column('message', sa.Text(), primary_key=False, nullable=False),
        sa.Column('status', sa.String(20), primary_key=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), primary_key=False, nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), primary_key=False, nullable=True),
        sa.UniqueConstraint('opportunity_id', 'candidate_id', name='one_job_application'),
    )
    op.create_index('ix_job_applications_opportunity_id', 'job_applications', ['opportunity_id'])
    op.create_index('ix_job_applications_candidate_id', 'job_applications', ['candidate_id'])
    op.create_table('employer_activity_events',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('employer_id', sa.Integer(), sa.ForeignKey('employer_profiles.id'), primary_key=False, nullable=False),
        sa.Column('event_key', sa.String(150), primary_key=False, nullable=False),
        sa.Column('kind', sa.String(40), primary_key=False, nullable=False),
        sa.Column('points', sa.Integer(), primary_key=False, nullable=False),
        sa.Column('explanation', sa.Text(), primary_key=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), primary_key=False, nullable=False),
        sa.UniqueConstraint('employer_id', 'event_key', name='unique_activity_event'),
    )
    op.create_index('ix_employer_activity_events_employer_id', 'employer_activity_events', ['employer_id'])
    op.create_table('career_meetings',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('employer_id', sa.Integer(), sa.ForeignKey('employer_profiles.id'), primary_key=False, nullable=False),
        sa.Column('candidate_id', sa.Integer(), sa.ForeignKey('candidate_profiles.id'), primary_key=False, nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), primary_key=False, nullable=False),
        sa.Column('timezone', sa.String(100), primary_key=False, nullable=False),
        sa.Column('channel', sa.String(255), primary_key=False, nullable=False),
        sa.Column('status', sa.String(25), primary_key=False, nullable=False),
        sa.Column('employer_confirmed_at', sa.DateTime(timezone=True), primary_key=False, nullable=True),
        sa.Column('interview_confirmed_at', sa.DateTime(timezone=True), primary_key=False, nullable=True),
        sa.Column('candidate_objection_at', sa.DateTime(timezone=True), primary_key=False, nullable=True),
        sa.Column('employer_hire_at', sa.DateTime(timezone=True), primary_key=False, nullable=True),
        sa.Column('candidate_hire_at', sa.DateTime(timezone=True), primary_key=False, nullable=True),
        sa.Column('demo_set', sa.String(64), primary_key=False, nullable=True),
    )
    op.create_index('ix_career_meetings_candidate_id', 'career_meetings', ['candidate_id'])
    op.create_index('ix_career_meetings_employer_id', 'career_meetings', ['employer_id'])
    op.create_index('ix_career_meetings_demo_set', 'career_meetings', ['demo_set'])
    op.create_table('career_messages',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('employer_id', sa.Integer(), sa.ForeignKey('employer_profiles.id'), primary_key=False, nullable=False),
        sa.Column('candidate_id', sa.Integer(), sa.ForeignKey('candidate_profiles.id'), primary_key=False, nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=False, nullable=False),
        sa.Column('body', sa.Text(), primary_key=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), primary_key=False, nullable=False),
    )
    op.create_index('ix_career_messages_employer_id', 'career_messages', ['employer_id'])
    op.create_index('ix_career_messages_candidate_id', 'career_messages', ['candidate_id'])
    op.create_table('privacy_consents',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=False, nullable=False),
        sa.Column('kind', sa.String(25), primary_key=False, nullable=False),
        sa.Column('accepted', sa.Boolean(), primary_key=False, nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), primary_key=False, nullable=False),
        sa.UniqueConstraint('user_id', 'kind', name='one_current_consent'),
    )
    op.create_index('ix_privacy_consents_user_id', 'privacy_consents', ['user_id'])
    op.create_table('demo_clock',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('offset_days', sa.Integer(), primary_key=False, nullable=False),
    )
    op.create_table('demo_sets',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('employer_user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=False, nullable=False),
        sa.Column('candidate_user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=False, nullable=False),
    )

def downgrade():
    op.drop_table('demo_sets')
    op.drop_table('demo_clock')
    op.drop_table('privacy_consents')
    op.drop_table('career_messages')
    op.drop_table('career_meetings')
    op.drop_table('employer_activity_events')
    op.drop_table('job_applications')
    op.drop_table('career_opportunities')
