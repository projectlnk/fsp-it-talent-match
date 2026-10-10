"""Apply Alembic only to brand-new owned databases on the isolated test cluster."""
import os
from pathlib import Path
import subprocess
import sys
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

pytestmark=[pytest.mark.integration,pytest.mark.skipif(not os.getenv('MATCHING_TEST_DATABASE_URL'),reason='Isolated Docker PostgreSQL required')]

@pytest.fixture
def migration_database():
    url=make_url(os.environ['MATCHING_TEST_DATABASE_URL'])
    assert url.get_backend_name()=='postgresql' and url.database=='fsp_matching_test'
    name='fsp_matching_migration_'+uuid.uuid4().hex
    admin=create_engine(url,isolation_level='AUTOCOMMIT')
    with admin.connect() as conn: conn.execute(text(f'CREATE DATABASE "{name}"'))
    own_url=url.set(database=name)
    engine=create_engine(own_url)
    def upgrade(revision):
        env=os.environ.copy();env['DATABASE_URL']=own_url.render_as_string(hide_password=False)
        result=subprocess.run([sys.executable,'-m','alembic','upgrade',revision],cwd=Path(__file__).resolve().parents[2],env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
    try: yield engine,upgrade
    finally:
        engine.dispose()
        with admin.connect() as conn: conn.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()

def test_fresh_migrations_and_repeat_upgrade(migration_database):
    engine,upgrade=migration_database
    upgrade('head');upgrade('head')
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT version_num FROM alembic_version'))=='d42e910career'
        assert conn.scalar(text("SELECT column_default FROM information_schema.columns WHERE table_name='test_answers' AND column_name='answered_at'")) is None
        column=conn.execute(text("SELECT is_nullable, column_default FROM information_schema.columns WHERE table_name='candidate_profiles' AND column_name='is_searchable'")).one()
        assert column.is_nullable=='NO' and 'false' in column.column_default
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.db.base import Base
    import app.db.models
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn,opts={'compare_server_default':True}),Base.metadata)==[]

def test_publication_migration_preserves_filled_profiles_and_answers(migration_database):
    engine,upgrade=migration_database
    upgrade('8f70f2f704de')
    with engine.begin() as conn:
        uid=conn.scalar(text("INSERT INTO users (email,password_hash,role,is_active,is_email_verified) VALUES ('migration@example.invalid','unused','CANDIDATE',true,true) RETURNING id"))
        pid=conn.scalar(text("INSERT INTO candidate_profiles (user_id,full_name,phone,about) VALUES (:uid,'Existing candidate','private phone','Existing description') RETURNING id"),{'uid':uid})
        sid=conn.scalar(text("SELECT id FROM specializations WHERE code='backend'"));gid=conn.scalar(text("SELECT id FROM grades WHERE code='junior'"))
        qid=conn.scalar(text("INSERT INTO questions (specialization_id,grade_id,type,payload,correct_answer,difficulty,is_active) VALUES (:s,:g,'SINGLE_CHOICE','{}','{}',1,true) RETURNING id"),{'s':sid,'g':gid})
        aid=conn.scalar(text("INSERT INTO test_attempts (candidate_profile_id,specialization_id,declared_grade_id,target_grade_id,status,score,passed) VALUES (:p,:s,:g,:g,'COMPLETED',80,true) RETURNING id"),{'p':pid,'s':sid,'g':gid})
        conn.execute(text("INSERT INTO test_answers (test_attempt_id,question_id,question_snapshot,answer,is_correct) VALUES (:a,:q,'{\"text\":\"preserved\"}','{\"value\":\"saved\"}',true)"),{'a':aid,'q':qid})
    upgrade('head');upgrade('head')
    with engine.connect() as conn:
        row=conn.execute(text('SELECT full_name,phone,about,is_searchable FROM candidate_profiles WHERE id=:p'),{'p':pid}).one()
        assert tuple(row)==('Existing candidate','private phone','Existing description',False)
        assert conn.scalar(text("SELECT answer->>'value' FROM test_answers WHERE test_attempt_id=:a"),{'a':aid})=='saved'
        assert conn.scalar(text("SELECT question_snapshot->>'text' FROM test_answers WHERE test_attempt_id=:a"),{'a':aid})=='preserved'


def test_startup_bootstraps_empty_bank_and_preserves_edits(migration_database, monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy.orm import sessionmaker
    import app.start as startup
    engine, upgrade = migration_database
    monkeypatch.setattr(startup, 'engine', engine)
    monkeypatch.setattr(startup, 'SessionLocal', sessionmaker(bind=engine))
    monkeypatch.setattr(startup, 'subprocess', SimpleNamespace(run=lambda *args, **kwargs: upgrade('head')))
    monkeypatch.setattr(startup, 'uvicorn', SimpleNamespace(run=lambda *args, **kwargs: None))
    startup.main()
    with engine.begin() as connection:
        count=connection.scalar(text('SELECT count(*) FROM questions'))
        assert count == 101
        connection.execute(text("UPDATE questions SET difficulty=99 WHERE id=(SELECT min(id) FROM questions)"))
    startup.main()
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM questions')) == count
        assert connection.scalar(text('SELECT max(difficulty) FROM questions')) == 99


def test_legacy_populated_snapshot_migration_reports_known_blocker(migration_database):
    # Diagnostic: verify the existing failure without fabricating missing historical parameters.
    engine, upgrade = migration_database
    upgrade('2b37baa6ab8d')
    with engine.begin() as connection:
        uid=connection.scalar(text("INSERT INTO users (email,password_hash,role,is_active,is_email_verified) VALUES ('legacy@example.invalid','unused','CANDIDATE',true,true) RETURNING id"))
        pid=connection.scalar(text("INSERT INTO candidate_profiles (user_id,full_name) VALUES (:u,'Legacy') RETURNING id"),{'u':uid})
        sid=connection.scalar(text("SELECT id FROM specializations WHERE code='backend'"));gid=connection.scalar(text("SELECT id FROM grades WHERE code='junior'"))
        qid=connection.scalar(text("INSERT INTO questions (specialization_id,grade_id,type,payload,correct_answer,difficulty,is_active) VALUES (:s,:g,'SINGLE_CHOICE','{}','{}',1,true) RETURNING id"),{'s':sid,'g':gid})
        aid=connection.scalar(text("INSERT INTO test_attempts (candidate_profile_id,specialization_id,declared_grade_id,target_grade_id,status) VALUES (:p,:s,:g,:g,'COMPLETED') RETURNING id"),{'p':pid,'s':sid,'g':gid})
        connection.execute(text("INSERT INTO test_answers (test_attempt_id,question_id,answer,is_correct) VALUES (:a,:q,'{\"value\":\"saved\"}',true)"),{'a':aid,'q':qid})
    with pytest.raises(AssertionError,match='contains null values'):
        upgrade('88945e7ea258')
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '2b37baa6ab8d'
        assert connection.scalar(text("SELECT answer->>'value' FROM test_answers")) == 'saved'


def test_migrated_schema_matches_orm_metadata(migration_database):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.db.base import Base
    import app.db.models
    engine,upgrade=migration_database
    upgrade('head')
    with engine.connect() as connection:
        differences=compare_metadata(MigrationContext.configure(connection, opts={'compare_server_default':True}),Base.metadata)
        assert differences == []
