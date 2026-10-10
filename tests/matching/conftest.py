"""Writes target a new SQLite or owned PostgreSQL test DB, never app SessionLocal."""
from datetime import datetime, UTC, date
import os, socket, threading, time, uuid
import httpx, pytest, uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from app.db.base import Base
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import app.db.models
from app.main import app
from app.db.session import get_session
from app.modules.auth.models import User, UserRole
from app.modules.auth.security import create_access_token
from app.modules.candidates.models import CandidateProfile, CandidateSkill, CandidateExperience, FspAchievement, FspRegistryLink, WorkFormat
from app.modules.assessments.models import Specialization, Grade, Category, CandidateCategory, CategoryStatus, TestAttempt, AttemptStatus
from app.modules.career.models import PrivacyConsent

@pytest.fixture
def database():
    admin = None
    database_name = None
    test_url = os.getenv('MATCHING_TEST_DATABASE_URL')
    if test_url:
        url = make_url(test_url)
        if url.get_backend_name() != 'postgresql' or url.database != 'fsp_matching_test':
            pytest.fail('MATCHING_TEST_DATABASE_URL must target the isolated fsp_matching_test database')
        # Each test owns a fresh database. Neither the app database nor an
        # existing schema is truncated or dropped.
        admin = create_engine(url, isolation_level='AUTOCOMMIT')
        database_name = 'fsp_matching_case_' + uuid.uuid4().hex
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        engine = create_engine(url.set(database=database_name))
        Base.metadata.create_all(engine)
    else:
        engine=create_engine('sqlite:///:memory:',connect_args={'check_same_thread':False},poolclass=StaticPool)
        @event.listens_for(engine,'connect')
        def foreign_keys(connection,record):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.create_function('lower',1,lambda value: value.lower() if value is not None else None)
        for model in [User,CandidateProfile,CandidateSkill,CandidateExperience,FspAchievement,FspRegistryLink,Specialization,Grade,Category,CandidateCategory,TestAttempt,PrivacyConsent]:
            model.__table__.create(engine)
    with Session(engine,expire_on_commit=False) as s:
        employer=User(email='employer@example.invalid',password_hash='unused',role=UserRole.EMPLOYER);s.add(employer)
        backend=Specialization(code='backend',name='Backend');frontend=Specialization(code='frontend',name='Frontend')
        junior=Grade(code='junior',name='Junior',order=1);middle=Grade(code='middle',name='Middle',order=2)
        s.add_all([backend,frontend,junior,middle]);s.flush()
        cat=Category(specialization_id=backend.id,grade_id=middle.id);other=Category(specialization_id=frontend.id,grade_id=junior.id)
        s.add_all([cat,other]);s.flush();profiles=[];users=[]
        for i in range(9):
            u=User(email=f'candidate-secret-{i}@example.invalid',password_hash='unused',role=UserRole.CANDIDATE,is_active=i!=6,is_email_verified=True);s.add(u);s.flush();users.append(u)
            s.add(PrivacyConsent(user_id=u.id,kind='processing',accepted=True,recorded_at=datetime.now(UTC)))
            p=CandidateProfile(user_id=u.id,full_name='Алексей' if i<3 else f'Профиль {i}',phone='+7 (999) 123-45-67',
                about='API. secret-contact@example.invalid +7 (999) 123-45-67 https://t.me/secret_handle @secret_handle',
                location='Москва' if i!=3 else 'Казань',work_format=WorkFormat.REMOTE if i!=3 else WorkFormat.HYBRID,is_searchable=i!=4)
            s.add(p);s.flush();profiles.append(p)
            s.add_all([CandidateSkill(candidate_profile_id=p.id,skill='Python'),CandidateSkill(candidate_profile_id=p.id,skill='SQL' if i!=2 else 'CSS')])
            s.add(CandidateExperience(candidate_profile_id=p.id,company_name='Компания',position='Разработчик',started_at=date(2024,1,1),description='secret-contact@example.invalid',is_current=True))
            s.add(CandidateCategory(candidate_profile_id=p.id,category_id=cat.id,is_current=False,status=CategoryStatus.CONFIRMED,test_score=99))
            s.add(CandidateCategory(candidate_profile_id=p.id,category_id=other.id if i==3 else cat.id,is_current=i!=7,status=CategoryStatus.NOT_CONFIRMED if i==5 else CategoryStatus.CONFIRMED,confirmed_at=datetime.now(UTC),test_score=80+i))
            s.add(TestAttempt(candidate_profile_id=p.id,specialization_id=backend.id,declared_grade_id=middle.id,target_grade_id=middle.id,status=AttemptStatus.COMPLETED,score=80,passed=True,finished_at=datetime.now(UTC)))
        users[8].role=UserRole.EMPLOYER
        s.add(CandidateCategory(candidate_profile_id=profiles[0].id,category_id=cat.id,is_current=True,status=CategoryStatus.CONFIRMED,test_score=85))
        s.add(CandidateSkill(candidate_profile_id=profiles[0].id,skill='python'))
        s.add(FspAchievement(candidate_profile_id=profiles[1].id,external_achievement_id='demo',title='Демо-результат',competition_date=date(2025,1,1),is_demo=True))
        s.commit();data={'employer':employer,'candidate':users[0],'profiles':profiles,'users':users,'category':cat}
    def sessions():
        with Session(engine) as session: yield session
    old=app.dependency_overrides.copy();app.dependency_overrides[get_session]=sessions
    try: yield engine,data
    finally:
        app.dependency_overrides.clear();app.dependency_overrides.update(old);engine.dispose()
        if admin is not None:
            # database_name is generated locally above; never taken from input.
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{database_name}"'))
            admin.dispose()

@pytest.fixture
def client(database):
    with TestClient(app) as c: yield c
@pytest.fixture
def headers(database): return {'Authorization':'Bearer '+create_access_token(database[1]['employer'].id)}
@pytest.fixture
def candidate_headers(database): return {'Authorization':'Bearer '+create_access_token(database[1]['candidate'].id)}
@pytest.fixture
def matching_server(database):
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'));thread=threading.Thread(target=server.run,daemon=True);thread.start();base=f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                if httpx.get(base+'/health',timeout=.3).status_code==200: break
            except httpx.HTTPError: pass
            time.sleep(.05)
        else: pytest.fail('Isolated server failed to start')
        yield base
    finally: server.should_exit=True;thread.join(timeout=10)
