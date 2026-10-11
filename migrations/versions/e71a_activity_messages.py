"""Invitation chat provenance, per-application views and mutual meeting confirmation."""
from alembic import op
import sqlalchemy as sa

revision = 'e71a_activity'
down_revision = 'd42e910career'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('job_applications', sa.Column('resume_viewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('offers', sa.Column('opportunity_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_offer_opportunity_activity', 'offers', 'career_opportunities', ['opportunity_id'], ['id'])
    op.create_index('ix_offers_opportunity_id', 'offers', ['opportunity_id'])
    op.add_column('career_meetings', sa.Column('opportunity_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_meeting_opportunity_activity', 'career_meetings', 'career_opportunities', ['opportunity_id'], ['id'])
    op.create_index('ix_career_meetings_opportunity_id', 'career_meetings', ['opportunity_id'])
    op.add_column('career_meetings', sa.Column('candidate_confirmed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('career_messages', sa.Column('kind', sa.String(25), nullable=False, server_default='message'))
    op.add_column('career_messages', sa.Column('offer_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_message_offer_activity', 'career_messages', 'offers', ['offer_id'], ['id'])
    op.create_index('ix_career_messages_offer_id', 'career_messages', ['offer_id'])
    op.create_unique_constraint('one_offer_technical_message', 'career_messages', ['offer_id', 'kind'])
    # Decisions prove review of that particular application, not all company applications.
    op.execute('UPDATE job_applications SET resume_viewed_at = decided_at WHERE decided_at IS NOT NULL')
    # Existing confirmations remain authoritative. Do not infer a vacancy for historic pairs.
    connection = op.get_bind()
    rows = connection.execute(sa.text("""SELECT o.id, o.title, o.description, o.salary_from, o.salary_to,
        o.salary_gross, o.contact_method, COALESCE(o.responded_at, o.created_at) AS accepted_at,
        o.employer_profile_id AS eid, o.candidate_profile_id AS cid,
        e.user_id AS employer_user, c.user_id AS candidate_user
        FROM offers o JOIN employer_profiles e ON e.id=o.employer_profile_id
        JOIN candidate_profiles c ON c.id=o.candidate_profile_id WHERE lower(CAST(o.status AS text))='accepted'""")).mappings().all()
    insert = sa.text("""INSERT INTO career_messages
        (employer_id, candidate_id, author_id, body, created_at, kind, offer_id)
        VALUES (:eid, :cid, :author, :body, :accepted_at, :kind, :offer_id)""")
    for row in rows:
        body = (f"{row['title']}\n{row['description'] or ''}\n"
                f"Зарплата: {row['salary_from']}–{row['salary_to']} ₽ "
                f"({'до' if row['salary_gross'] else 'после'} вычета НДФЛ).\n"
                f"Способ связи: {row['contact_method'] or 'Не указан'}")
        for author, kind, text in [(row['employer_user'], 'invitation', body),
                (row['candidate_user'], 'acceptance', 'Приглашение принято. Готов обсудить предложенные условия')]:
            connection.execute(insert, dict(eid=row['eid'], cid=row['cid'], author=author, body=text,
                accepted_at=row['accepted_at'], kind=kind, offer_id=row['id']))


def downgrade():
    # Preserve message history if rolling back: provenance columns can be removed without deleting messages.
    op.drop_constraint('one_offer_technical_message', 'career_messages', type_='unique')
    op.drop_index('ix_career_messages_offer_id', table_name='career_messages')
    op.drop_constraint('fk_message_offer_activity', 'career_messages', type_='foreignkey')
    op.drop_column('career_messages', 'offer_id')
    op.drop_column('career_messages', 'kind')
    op.drop_column('career_meetings', 'candidate_confirmed_at')
    op.drop_index('ix_career_meetings_opportunity_id', table_name='career_meetings')
    op.drop_constraint('fk_meeting_opportunity_activity', 'career_meetings', type_='foreignkey')
    op.drop_column('career_meetings', 'opportunity_id')
    op.drop_index('ix_offers_opportunity_id', table_name='offers')
    op.drop_constraint('fk_offer_opportunity_activity', 'offers', type_='foreignkey')
    op.drop_column('offers', 'opportunity_id')
    op.drop_column('job_applications', 'resume_viewed_at')
