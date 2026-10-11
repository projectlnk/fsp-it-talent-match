"""Explicit local fixtures. Never run during startup or against the public site."""
import argparse
from datetime import timedelta
from urllib.parse import urlsplit
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import SessionLocal
import app.db.models
from app.modules.auth.models import User, UserRole
from app.modules.auth.security import hash_password
from app.modules.candidates.models import CandidateProfile, CandidateSkill, WorkFormat, FspAchievement
from app.modules.employers.models import EmployerProfile
from app.modules.employers import service as employers
from app.modules.employers.schemas import OfferCreate
from app.modules.assessments import service as assessments
from app.modules.career import service as career
from app.modules.career.schemas import OpportunityInput, MeetingInput


def seed(password):
    if urlsplit(get_settings().app_base_url).hostname not in ('localhost','127.0.0.1'):
        raise SystemExit('Fixtures are restricted to a local APP_BASE_URL; production is not allowed')
    if not 8 <= len(password) <= 128:
        raise SystemExit('Password must contain 8–128 characters')
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == 'workspace-hr-a@example.invalid')):
            print('Local workspace fixtures already exist; no data changed')
            return
        companies=[]
        for letter in ('a','b'):
            user=User(email=f'workspace-hr-{letter}@example.invalid',password_hash=hash_password(password),role=UserRole.EMPLOYER,is_email_verified=True)
            db.add(user);db.flush()
            company=EmployerProfile(user_id=user.id,company_name=f'Демо-компания {letter.upper()}',description='Локальные тестовые данные кабинета работодателя',industry='ИТ',contact_email=f'workspace-hr-{letter}@example.com')
            db.add(company);db.commit()
            employers.update_profile(db,user_id=user.id,changes={'description':company.description})
            companies.append((user,company))
        candidates=[]
        for i in range(1,7):
            user=User(email=f'workspace-candidate-{i}@example.invalid',password_hash=hash_password(password),role=UserRole.CANDIDATE,is_email_verified=True)
            db.add(user);db.flush()
            profile=CandidateProfile(user_id=user.id,full_name=f'Демо-кандидат {i}',desired_role='Backend-разработчик',about='Вымышленный кандидат для локальной проверки кабинета',location='Москва' if i%2 else 'Казань',experience_years=i,desired_salary_from=100000+i*10000,desired_salary_to=200000+i*10000,work_format=WorkFormat.REMOTE,is_searchable=True)
            db.add(profile);db.flush()
            db.add_all([CandidateSkill(candidate_profile_id=profile.id,skill='Python'),CandidateSkill(candidate_profile_id=profile.id,skill='SQL')])
            career.consent(db,user.id,'processing',True);career.consent(db,user.id,'publication',True);db.commit()
            # Actual scoring services; the prepared answers are local fixtures.
            attempt=assessments.start_attempt(db,user_id=user.id,specialization_code='backend',grade_code='middle')
            for answer in attempt.answers:
                snapshot=answer.question_snapshot
                correct=snapshot['correct']
                payload={'values':correct if isinstance(correct,list) else [correct]} if snapshot['type']=='multiple_choice' else {'value':correct}
                assessments.submit_answer(db,user_id=user.id,attempt_id=attempt.id,answer_id=answer.id,answer_payload=payload)
            assessments.finish_attempt(db,user_id=user.id,attempt_id=attempt.id)
            if i in (1,3):
                db.add(FspAchievement(candidate_profile_id=profile.id,external_achievement_id=f'workspace-demo-{i}',title='Демонстрационное достижение ФСП',discipline_code='backend',is_demo=True))
                db.commit()
            candidates.append((user,profile))
        for index,(user,company) in enumerate(companies):
            data=OpportunityInput(title=f'Backend-разработчик в демо-компанию {index+1}',description='Разработка API, интеграций и сервисов обработки данных. Вымышленная локальная вакансия.',specialization='backend',grade='middle',skills='Python, SQL',salary_from=140000,salary_to=220000,work_format='remote',contact_method='Внутренние сообщения')
            active=career.save_opportunity(db,user.id,'vacancy',data)
            need=career.save_opportunity(db,user.id,'need',data.model_copy(update={'title':'Демо-потребность команды'}))
            inactive=career.save_opportunity(db,user.id,'vacancy',data.model_copy(update={'title':'Демо-вакансия в архиве'}))
            deleted=career.save_opportunity(db,user.id,'vacancy',data.model_copy(update={'title':'Демо-удалённая вакансия'}))
            for row in (active,need,inactive,deleted): row.demo_set='workspace-fixtures-v1'
            career.change_opportunity(db,user.id,inactive.id,'close')
            career.change_opportunity(db,user.id,deleted.id,'delete')
            instant=career.now(db)
            for j,(candidate,profile) in enumerate(candidates[index*3:index*3+3]):
                application=career.apply(db,candidate.id,active.id,'Локальный демонстрационный отклик')
                career.record_resume_view(db,user,profile.id)
                if index==0 or j==0:
                    career.decide(db,user.id,application.id,'accepted' if j<2 else 'rejected')
                if j in (0,1):
                    offer=employers.create_offer(db,employer_user_id=user.id,payload=OfferCreate(candidate_profile_id=profile.id,opportunity_id=active.id,title='Демо-приглашение по вакансии',description=data.description,salary_from=data.salary_from,salary_to=data.salary_to,contact_method=data.contact_method))
                    employers.respond_to_offer(db,offer_id=offer.id,candidate_user_id=candidate.id,decision='accepted')
                if j==0:
                    career.send_message(db,user,company.id,profile.id,'Демонстрация: обсудим задачи и условия.')
                    career.send_message(db,candidate,company.id,profile.id,'Демонстрация: готов обсудить предложение.')
                    meeting=career.schedule(db,user.id,profile.id,MeetingInput(scheduled_at=instant+timedelta(days=2),timezone='Europe/Moscow',channel='Внутренний канал локальной демонстрации'))
                    if index==0:
                        # Prepared past date only for this synthetic fixture.
                        meeting.scheduled_at=instant-timedelta(days=1)
                        career.meeting_action(db,user,meeting.id,'interview')
                        career.meeting_action(db,candidate,meeting.id,'interview')
                        career.meeting_action(db,user,meeting.id,'hire')
                        career.meeting_action(db,candidate,meeting.id,'hire')
                if j==1: career.schedule(db,user.id,profile.id,MeetingInput(scheduled_at=instant+timedelta(days=3),timezone='Europe/Moscow',channel='Локальная видеовстреча'))
            db.commit()
            for candidate,profile,decision in [(candidates[0][0],candidates[0][1],None),(candidates[4][0],candidates[4][1],'rejected'),(candidates[5][0],candidates[5][1],'accepted')]:
                offer=employers.create_offer(db,employer_user_id=user.id,payload=OfferCreate(candidate_profile_id=profile.id,title='Демо-прямое приглашение без вакансии',description='Вымышленное локальное предложение',salary_from=140000,salary_to=220000,contact_method='Внутренние сообщения'))
                if decision: employers.respond_to_offer(db,offer_id=offer.id,candidate_user_id=candidate.id,decision=decision)
            db.commit()
        print('Created local fixture employers: workspace-hr-a@example.invalid, workspace-hr-b@example.invalid')
        print('Created local fixture candidates: workspace-candidate-1@example.invalid through workspace-candidate-6@example.invalid')
        for row in career.leaderboard(db):
            if row['company'].user_id in [user.id for user,_ in companies]:
                print(row['company'].company_name, row['score'], 'points from existing scoring rules')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--password',required=True)
    seed(parser.parse_args().password)
