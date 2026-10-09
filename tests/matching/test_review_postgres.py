"""Concurrency and JSONB behavior verified on fresh owned PostgreSQL databases."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import threading
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.modules.assessments import service as assessments
from app.modules.assessments.models import (Question, QuestionType, TestAttempt, TestAnswer,
    CandidateCategory, CategoryStatus, GradeChangeCooldown, AttemptStatus)
from app.modules.candidates import service as candidates
from app.modules.candidates.models import FspAchievement, FspRegistryLink
from app.modules.employers import service as employers
from app.modules.employers.models import EmployerProfile, Offer, OfferStatus
from app.modules.employers.schemas import OfferCreate

pytestmark = pytest.mark.skipif(not os.getenv("MATCHING_TEST_DATABASE_URL"), reason="Owned PostgreSQL database required")

@pytest.fixture
def question_pool(database):
    engine, data = database
    with Session(engine) as session:
        category = data['category']
        for index in range(10):
            session.add(Question(specialization_id=category.specialization_id, grade_id=category.grade_id,
                                type=QuestionType.SINGLE_CHOICE, difficulty=1, payload={"text": f"Question {index}", "options": ["Yes", "No"]}, correct_answer={"value": "Yes"}))
        session.commit()


def test_parallel_starts_return_same_attempt(database, question_pool):
    engine, data = database; barrier = threading.Barrier(2)
    def start(_):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            return assessments.start_attempt(session, user_id=data['candidate'].id, specialization_code='backend', grade_code='middle').id
    with ThreadPoolExecutor(2) as pool: ids = list(pool.map(start, range(2)))
    assert len(set(ids)) == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(TestAnswer)) == 10
        assert session.scalar(select(func.count()).select_from(TestAttempt).where(TestAttempt.status == AttemptStatus.IN_PROGRESS)) == 1


def test_invalid_answer_is_not_saved_and_completed_attempt_is_immutable(client, candidate_headers, database, question_pool):
    started = client.post('/api/v1/assessments/attempts', headers=candidate_headers, json={'specialization':'backend','grade':'middle'}).json()
    attempt_id = started['attempt_id']; endpoint = f'/api/v1/assessments/attempts/{attempt_id}'
    state = client.get(endpoint, headers=candidate_headers).json(); answer_id = state['questions'][0]['answer_id']
    assert 'correct' not in str(state['questions'])
    assert client.post(endpoint + f'/answers/{answer_id}', headers=candidate_headers, json={'value':'Unavailable'}).status_code == 400
    assert client.get(endpoint, headers=candidate_headers).json()['answered_count'] == 0
    assert client.post(endpoint + f'/answers/{answer_id}', headers=candidate_headers, json={'value':'Yes'}).status_code == 200
    assert client.post(endpoint + '/finish', headers=candidate_headers).status_code == 200
    assert client.post(endpoint + f'/answers/{answer_id}', headers=candidate_headers, json={'value':'No'}).status_code == 409
    assert client.get(endpoint, headers=candidate_headers).json()['score'] == 10


def test_failed_current_category_cannot_bypass_grade_cooldown(database):
    engine, data = database
    with Session(engine) as session:
        profile = data['profiles'][0]
        session.add(GradeChangeCooldown(candidate_profile_id=profile.id, last_change_at=datetime.now(UTC), next_allowed_at=datetime.now(UTC)+timedelta(days=60)))
        session.query(CandidateCategory).filter_by(candidate_profile_id=profile.id).update({'is_current':False})
        session.add(CandidateCategory(candidate_profile_id=profile.id, category_id=data['category'].id, status=CategoryStatus.NOT_CONFIRMED, is_current=True))
        session.commit()
        with pytest.raises(assessments.AttemptBlocked):
            assessments.check_can_start_attempt(session, user_id=data['candidate'].id, specialization_code='backend', grade_code='junior')
        assessments.check_can_start_attempt(session, user_id=data['candidate'].id, specialization_code='backend', grade_code='middle')


def test_parallel_finishes_create_one_category(database, question_pool):
    engine, data = database
    with Session(engine) as session:
        attempt = assessments.start_attempt(session, user_id=data['candidate'].id, specialization_code='backend', grade_code='middle'); attempt_id=attempt.id
        before = session.scalar(select(func.count()).select_from(CandidateCategory))
    barrier = threading.Barrier(2)
    def finish(_):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try: assessments.finish_attempt(session, user_id=data['candidate'].id, attempt_id=attempt_id); return 'done'
            except assessments.AttemptAlreadyCompleted: return 'conflict'
    with ThreadPoolExecutor(2) as pool: assert sorted(pool.map(finish, range(2))) == ['conflict','done']
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CandidateCategory)) == before + 1
        assert session.scalar(select(func.count()).select_from(CandidateCategory).where(CandidateCategory.candidate_profile_id==data['profiles'][0].id, CandidateCategory.is_current.is_(True))) == 1


def test_foreign_fsp_achievement_rejected_before_any_write(database):
    engine, data = database
    with Session(engine) as session:
        with pytest.raises(candidates.FspParticipantNotFound):
            candidates.link_and_import_fsp(session,user_id=data['candidate'].id,participant_id='demo-1',profile_data={'id':'demo-1'},achievements_data=[{'id':'a','participant_id':'demo-2','title':'Foreign'}])
        session.commit()
        assert session.scalar(select(func.count()).select_from(FspRegistryLink)) == 0
        assert session.scalar(select(func.count()).select_from(FspAchievement).where(FspAchievement.candidate_profile_id==data['profiles'][0].id)) == 0


def test_parallel_offer_decisions_have_single_winner(database):
    engine, data = database
    with Session(engine) as session:
        session.add(EmployerProfile(user_id=data['employer'].id,company_name='Company'));session.commit()
        offer = employers.create_offer(session,employer_user_id=data['employer'].id,payload=OfferCreate(candidate_profile_id=data['profiles'][0].id,title='Developer',salary_from=100,salary_to=200));offer_id=offer.id
    barrier = threading.Barrier(2)
    def decide(decision):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try: return employers.respond_to_offer(session,offer_id=offer_id,candidate_user_id=data['candidate'].id,decision=decision).status
            except employers.InvalidStatusTransition: return 'conflict'
    with ThreadPoolExecutor(2) as pool: results = list(pool.map(decide, ['accepted','rejected']))
    assert results.count('conflict') == 1
    with Session(engine) as session:
        status=session.get(Offer,offer_id).status.value
        assert status in results
        response=employers.get_offer_for_employer(session,offer_id=offer_id,employer_user_id=data['employer'].id)
        assert (response.contacts is not None) == (status=='accepted')


@pytest.mark.parametrize('payload', [{'competition_date':'bad'}, {'place':'not a number'}, {'title':'x'*256}])
def test_invalid_fsp_contract_rejected_atomically(database, payload):
    engine, data = database
    with Session(engine) as session:
        with pytest.raises(candidates.FspRegistryInvalid):
            candidates.link_and_import_fsp(session,user_id=data['candidate'].id,participant_id='demo-1',profile_data={'id':'demo-1'},achievements_data=[{'id':'a','participant_id':'demo-1','title':'Valid',**payload}])
        session.commit()
        assert session.scalar(select(func.count()).select_from(FspRegistryLink)) == 0


def test_parallel_email_confirmation_consumes_token_once(database):
    from app.modules.auth.models import EmailVerificationToken
    from app.modules.auth import service as auth
    engine, data = database
    with Session(engine) as session:
        session.add(EmailVerificationToken(user_id=data['candidate'].id,token='review-test-token',expires_at=datetime.now(UTC)+timedelta(hours=1)))
        session.commit()
    barrier=threading.Barrier(2)
    def confirm(_):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try: auth.verify_email(session,token='review-test-token');return 'confirmed'
            except auth.InvalidVerificationToken: return 'consumed'
    with ThreadPoolExecutor(2) as pool: assert sorted(pool.map(confirm,range(2))) == ['confirmed','consumed']


def test_pending_offer_does_not_leak_contacts_from_candidate_name(database):
    from app.modules.candidates.models import CandidateProfile
    engine,data=database
    with Session(engine) as session:
        session.get(CandidateProfile,data['profiles'][0].id).full_name='Name secret@example.com +7 (999) 123-45-67'
        session.add(EmployerProfile(user_id=data['employer'].id,company_name='Company'));session.commit()
        offer=employers.create_offer(session,employer_user_id=data['employer'].id,payload=OfferCreate(candidate_profile_id=data['profiles'][0].id,title='Developer',salary_from=100,salary_to=200))
        assert offer.contacts is None
        assert 'secret@example.com' not in offer.model_dump_json() and '999' not in offer.model_dump_json()


def test_legacy_confirmation_without_date_does_not_override_latest_dated_grade(database):
    from app.modules.assessments.models import Category, Grade
    engine,data=database
    with Session(engine) as session:
        profile_id=data['profiles'][0].id
        old_category_id=session.scalar(select(Category.id).join(Grade,Grade.id==Category.grade_id).where(Grade.code=='junior'))
        session.query(CandidateCategory).filter(CandidateCategory.candidate_profile_id==profile_id,CandidateCategory.confirmed_at.is_(None)).update({'category_id':old_category_id})
        session.add(GradeChangeCooldown(candidate_profile_id=profile_id,last_change_at=datetime.now(UTC),next_allowed_at=datetime.now(UTC)+timedelta(days=60)))
        session.commit()
        assessments.check_can_start_attempt(session,user_id=data['candidate'].id,specialization_code='backend',grade_code='middle')
        with pytest.raises(assessments.AttemptBlocked):
            assessments.check_can_start_attempt(session,user_id=data['candidate'].id,specialization_code='backend',grade_code='junior')
