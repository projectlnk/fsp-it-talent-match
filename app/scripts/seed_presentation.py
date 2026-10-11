"""Explicit presentation fixtures; accepts credentials through stdin, never sends email.

The reset removes account-dependent records only and leaves identity sequences,
reference data, the question bank, configuration and storage volumes intact.
"""
import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session
import app.db.models
from app.db.base import Base
from app.db.session import engine
from app.core.config import get_settings
from app.modules.auth.models import User, UserRole
from app.modules.auth.security import hash_password
from app.modules.candidates.models import CandidateProfile, CandidateSkill, CandidateExperience, WorkFormat
from app.modules.candidates import service as candidates
from app.modules.employers.models import EmployerProfile
from app.modules.employers import service as employers
from app.modules.employers.schemas import OfferCreate
from app.modules.assessments import service as assessments
from app.modules.assessments.models import CandidateCategory, GradeChangeCooldown
from app.modules.career import service as career
from app.modules.career.models import Application, Opportunity, ThreadMessage, Meeting, PrivacyConsent
from app.modules.career.schemas import OpportunityInput, MeetingInput
from app.modules.matching import needs, service as matching
from app.modules.matching.schemas import TeamNeedInput, CandidateSearchQuery


def parse_source(text):
    records = []
    for block in re.split(r'(?m)^\d+\. ', text)[1:]:
        values = {}
        for label, key in [('ФИО', 'name'), ('Email', 'email'), ('Пароль', 'password'), ('Роль', 'role'), ('Компания', 'company')]:
            match = re.search(r'(?m)^'+label+r':\s*(.+)$', block)
            if match:
                values[key] = match.group(1).strip()
        if 'email' in values:
            values['source'] = block
            records.append(values)
    if len(records) != 10 or sum(r.get('role') == 'employer' for r in records) != 5 or sum(r.get('role') == 'candidate' for r in records) != 5:
        raise ValueError('Source must contain exactly five employers and five candidates')
    if len({r['email'].lower() for r in records}) != 10:
        raise ValueError('Demo addresses must be unique')
    if any(not 8 <= len(r.get('password','')) <= 128 for r in records):
        raise ValueError('Each source password must contain 8–128 characters')
    return records


def reset_accounts(db):
    dependent = {'users'}
    while True:
        expanded = dependent | {table.name for table in Base.metadata.tables.values()
            if any(fk.column.table.name in dependent for fk in table.foreign_keys)}
        if expanded == dependent:
            break
        dependent = expanded
    counts = {}
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in dependent:
            counts[table.name] = db.scalar(select(func.count()).select_from(table))
            db.execute(delete(table))
    db.flush()
    # Deliberately do not reset sequences: an old JWT cannot acquire a new account ID.
    return counts


def seed(records, expected_url):
    settings = get_settings()
    if settings.app_base_url.rstrip('/') != expected_url.rstrip('/'):
        raise ValueError('APP_BASE_URL differs from the explicitly selected target')
    # Verify source before deleting anything; passwords stay out of output.
    assert len(records) == 10 and len({r['email'].lower() for r in records}) == 10
    assert sum(r['role'] == 'employer' for r in records) == 5
    assert sum(r['role'] == 'candidate' for r in records) == 5
    assert all(8 <= len(r['password']) <= 128 for r in records)
    registry = {}
    with httpx.Client(base_url=settings.fsp_base_url, timeout=10) as client:
        for pid in ['demo-2', 'demo-3']:
            profile = client.get('/participants/'+pid); profile.raise_for_status()
            achievements = client.get('/participants/'+pid+'/achievements'); achievements.raise_for_status()
            registry[pid] = (profile.json(), achievements.json())
    # Service commits use savepoints; all reset/fixtures are one outer transaction.
    with engine.begin() as connection:
        with Session(bind=connection, join_transaction_mode='create_savepoint', expire_on_commit=False) as db:
            before = reset_accounts(db)
            instant = career.now(db)
            companies, people = [], []
            for record in [r for r in records if r['role'] == 'employer']:
                user = User(email=record['email'].lower(), password_hash=hash_password(record['password']),
                    role=UserRole.EMPLOYER, is_email_verified=True, is_active=True)
                db.add(user); db.flush()
                source = record['source']
                direction = re.search(r'(?m)^Направление:\s*(.+)$',source)
                industry = re.search(r'(?m)^Отрасль:\s*(.+)$',source)
                site = re.search(r'(?m)^Сайт:\s*(https?://\S+)',source)
                complete = len(companies) != 2
                company = EmployerProfile(user_id=user.id, company_name=record['company'],
                    description=('Демонстрационный профиль. '+direction.group(1)) if complete and direction else None,
                    industry=industry.group(1) if industry else None,
                    website=site.group(1).rstrip('.') if site else None,
                    contact_email=record['email'] if complete else None,
                    contact_phone=('+7 999 000-00-0'+str(len(companies))) if complete else None)
                db.add(company); db.flush(); career.consent(db,user.id,'processing',True)
                companies.append((user,company))
            params = [
                ('backend','middle','Backend-разработчик','Москва',4,220000,300000,'remote',['Python','FastAPI','PostgreSQL','Docker','Redis'],9,2),
                ('frontend','junior','Frontend-разработчик','Санкт-Петербург',1,90000,130000,'hybrid',['JavaScript','React','CSS','HTML'],8,1),
                ('backend','intern','Начинающий Backend-разработчик','Казань',0,None,None,'remote',['Python'],8,0),
                ('backend','middle','Go-разработчик','Новосибирск',6,250000,350000,'remote',['Go','PostgreSQL','Kubernetes','gRPC'],9,3),
                ('backend','junior','Backend-разработчик','Екатеринбург',0,None,None,'remote',['Python','SQL'],7,0)]
            for index,record in enumerate(r for r in records if r['role'] == 'candidate'):
                spec,grade,role,location,experience,low,high,work,skills,correct_count,jobs = params[index]
                user = User(email=record['email'].lower(),password_hash=hash_password(record['password']),
                    role=UserRole.CANDIDATE,is_email_verified=True,is_active=True)
                db.add(user); db.flush()
                phone = re.search(r'(?m)^Телефон:\s*(.+)$',record['source'])
                profile = CandidateProfile(user_id=user.id,full_name=record['name'],desired_role=role,
                    location=location,experience_years=experience,desired_salary_from=low,desired_salary_to=high,
                    work_format=WorkFormat(work),phone=phone.group(1) if phone else None,
                    about='Демонстрационный кандидат для презентации сервиса.',is_searchable=False)
                db.add(profile);db.flush()
                db.add_all(CandidateSkill(candidate_profile_id=profile.id,skill=skill) for skill in skills)
                for j in range(jobs):
                    db.add(CandidateExperience(candidate_profile_id=profile.id,company_name='Демонстрационная компания '+str(j+1),
                        position=role if j == jobs-1 else 'Разработчик',started_at=date(instant.year-max(1,experience)+j,1,1),
                        ended_at=None if j == jobs-1 else date(instant.year-max(1,experience)+j+1,1,1),is_current=j == jobs-1))
                career.consent(db,user.id,'processing',True);db.commit()
                attempt = assessments.start_attempt(db,user_id=user.id,specialization_code=spec,grade_code=grade)
                for j,answer in enumerate(attempt.answers):
                    snapshot=answer.question_snapshot; correct=snapshot['correct']
                    if j < correct_count:
                        payload={'values':correct if isinstance(correct,list) else [correct]} if snapshot['type']=='multiple_choice' else {'value':correct}
                        assessments.submit_answer(db,user_id=user.id,attempt_id=attempt.id,answer_id=answer.id,answer_payload=payload)
                attempt=assessments.finish_attempt(db,user_id=user.id,attempt_id=attempt.id)
                assert attempt.passed
                if index in (0,3):
                    past=instant-timedelta(days=70 if index == 0 else 15)
                    attempt.started_at=past-timedelta(minutes=15);attempt.finished_at=past
                    category=db.scalar(select(CandidateCategory).where(CandidateCategory.candidate_profile_id==profile.id,CandidateCategory.is_current.is_(True)))
                    category.confirmed_at=past
                    cooldown=db.scalar(select(GradeChangeCooldown).where(GradeChangeCooldown.candidate_profile_id==profile.id))
                    cooldown.last_change_at=past;cooldown.next_allowed_at=past+timedelta(days=60)
                    db.commit()
                matching.set_publication(db,user.id,True)
                if index in (0,1):
                    pid='demo-3' if index == 0 else 'demo-2'
                    candidates.link_and_import_fsp(db,user_id=user.id,participant_id=pid,
                        profile_data=registry[pid][0],achievements_data=registry[pid][1])
                people.append((user,profile))
            db.commit()
            positions=[('Backend Python Middle','backend','middle','Python, FastAPI, PostgreSQL',180000,300000,'remote'),
                ('Frontend React Junior','frontend','junior','JavaScript, React, CSS',90000,150000,'hybrid'),
                ('Backend Go Middle','backend','middle','Go, PostgreSQL, gRPC',220000,350000,'remote'),
                ('Backend Python Junior','backend','junior','Python, SQL',100000,170000,'remote')]
            vacancies=[]
            for index,(user,company) in enumerate(companies):
                company_jobs=[]
                for j in range([4,2,0,3,0][index]):
                    title,spec,grade,skills,low,high,work=positions[j]
                    row=career.save_opportunity(db,user.id,'vacancy',OpportunityInput(title=title,
                        description='Демонстрационная вакансия: разработка сервисов, работа с API и командой. Данные для презентации.',
                        specialization=spec,grade=grade,skills=skills,salary_from=low,salary_to=high,work_format=work,contact_method='Чат платформы'))
                    if index == 3:
                        row.created_at=instant-timedelta(days=31);row.expires_at=instant-timedelta(days=1)
                    company_jobs.append(row)
                vacancies.append(company_jobs)
            db.commit()
            # Synthetic candidate actions on real service paths, not manually assigned score.
            for index,(user,company) in enumerate(companies):
                if index in (0,1,3):
                    selected_people=people if index != 1 else people[:2]
                    for row in vacancies[index]:
                        for candidate,profile in selected_people:
                            application=career.apply(db,candidate.id,row.id,'Демонстрационный отклик для презентации') if index != 3 else None
                            if application and (index == 0 or profile.id == people[0][1].id):
                                application.resume_viewed_at=instant
                    if index == 3:
                        # Historical applications arrived while the vacancy was published.
                        for candidate,profile in people:
                            db.add(Application(opportunity_id=vacancies[index][0].id,candidate_id=profile.id,
                                message='Демонстрационный исторический отклик',status='submitted',created_at=instant-timedelta(days=20)))
                count=[18,8,0,12,25][index]
                for j in range(count):
                    candidate,profile=people[j%5]
                    linked=vacancies[index][j%len(vacancies[index])] if vacancies[index] else None
                    offer=employers.create_offer(db,employer_user_id=user.id,payload=OfferCreate(candidate_profile_id=profile.id,
                        opportunity_id=linked.id if linked else None,title='Демонстрационное предложение обсудить работу',
                        description='Обсудим задачи и условия работы. Вымышленное предложение для презентации.',
                        salary_from=100000,salary_to=250000,contact_method='Чат платформы'))
                    accept=(index == 0 and j < 7) or (index == 1 and j < 2)
                    if accept:
                        employers.respond_to_offer(db,offer_id=offer.id,candidate_user_id=candidate.id,decision='accepted')
                    elif (index == 0 and j < 12) or (index == 1 and j < 4):
                        employers.mark_offer_viewed(db,offer_id=offer.id,candidate_user_id=candidate.id)
                if index in (0,1):
                    available=people if index == 0 else people[:2]
                    prepared=[]
                    for j,(candidate,profile) in enumerate(available):
                        career.send_message(db,user,company.id,profile.id,'Демонстрация: обсудим задачи и условия.')
                        career.send_message(db,candidate,company.id,profile.id,'Демонстрация: готов обсудить предложение.')
                        linked=vacancies[index][j%len(vacancies[index])]
                        meeting=career.schedule(db,user.id,profile.id,MeetingInput(scheduled_at=instant+timedelta(days=j+2),
                            timezone='Europe/Moscow',channel='Демонстрационная видеовстреча',opportunity_id=linked.id))
                        prepared.append((meeting,candidate))
                    for j,(meeting,candidate) in enumerate(prepared):
                        meeting.scheduled_at=instant-timedelta(days=1)
                        career.meeting_action(db,user,meeting.id,'interview')
                        if j < (3 if index == 0 else 1):
                            career.meeting_action(db,candidate,meeting.id,'interview')
                            if j < (2 if index == 0 else 1):
                                career.meeting_action(db,user,meeting.id,'hire')
                                career.meeting_action(db,candidate,meeting.id,'hire')
                elif index == 2:
                    for _,profile in people[:3]:
                        career.event(db,company.id,'resume-view:'+str(profile.id),'resume_view',0,'Демонстрационный просмотр профиля без начисления баллов')
                db.commit()
            for index in (0,1):
                user,_=companies[index]
                needs.save_template(db,user.id,TeamNeedInput(name='Команда нового проекта',positions=[
                    {'name':'Backend Middle','filters':{'specialization':'backend','grade':'middle','skills':['PostgreSQL']}},
                    {'name':'Frontend Junior','filters':{'specialization':'frontend','grade':'junior','skills':['React']}}]))
            career.process_due(db);db.commit()
            assert db.scalar(select(func.count(User.id))) == 10
            assert db.scalar(select(func.count(User.id)).where(User.is_email_verified.is_(True))) == 10
            assert matching.search_candidates(db,CandidateSearchQuery()).meta.total == 5
            report={'reset_tables':before,'users':10,'employers':5,'candidates':5,
                'vacancies':db.scalar(select(func.count(Opportunity.id)).where(Opportunity.kind=='vacancy')),
                'messages':db.scalar(select(func.count(ThreadMessage.id))),
                'meetings':db.scalar(select(func.count(Meeting.id))),
                'ranking':[{'company':r['company'].company_name,'score':r['score'],'activity_percent':r['viewed_percent'],
                    'confirmed_meetings':r['interviews'],'scheduled_meetings':r['meetings'],'closed_vacancies':r['closed_vacancies']} for r in career.leaderboard(db)]}
            db.commit()
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reset-accounts',action='store_true',required=True)
    parser.add_argument('--expect-base-url',required=True)
    args=parser.parse_args()
    records=json.load(sys.stdin)
    print(json.dumps(seed(records,args.expect_base_url),ensure_ascii=False))
