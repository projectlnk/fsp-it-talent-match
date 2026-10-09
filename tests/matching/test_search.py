import pytest
from sqlalchemy.orm import Session
from app.modules.assessments.models import CandidateCategory, CategoryStatus
API='/api/v1/matching/candidates'

@pytest.mark.parametrize('query,expected',[('',4),('?specialization=backend',3),('?grade=junior',1),('?skills=python&skills=sql',4),('?skills=python&skills=sql&all_skills=true',3),('?skills=python&skills=sql&all_skills=false',4),('?skills=python&skills=Rust&all_skills=true',0),('?all_skills=true',4),('?skills=PYTHON&skills=python',4),('?specialization=backend&grade=middle&skills=sql&location=моск&work_format=remote',2),('?skills=Rust',0),('?specialization=unknown',0),('?location=%25',0),('?location=%5F',0)])
def test_filters(client,headers,query,expected):
    r=client.get(API+query,headers=headers);assert r.status_code==200,r.text
    data=r.json();assert data['meta']['total']==expected
    ids=[c['profile_id'] for c in data['items']];assert len(ids)==len(set(ids))==expected
    assert all(c['category_status']=='confirmed' and 'ranking_score' not in c for c in data['items'])
@pytest.mark.parametrize('query',['?page=0','?page_size=51','?page_size=0','?page=oops','?skills='+'x'*101,'?only_confirmed=false','?limit=20','?all_skills=invalid'])
def test_invalid_parameters(client,headers,query): assert client.get(API+query,headers=headers).status_code==422

def test_pagination(client,headers):
    first=client.get(API+'?page_size=3',headers=headers).json();last=client.get(API+'?page_size=3&page=2',headers=headers).json()
    assert first==client.get(API+'?page_size=3',headers=headers).json()
    assert first['meta']=={'total':4,'page':1,'page_size':3,'total_pages':2}
    assert len(first['items'])==3 and len(last['items'])==1
    assert not {i['profile_id'] for i in first['items']} & {i['profile_id'] for i in last['items']}
    assert client.get(API+'?page=3&page_size=3',headers=headers).json()['items']==[]
@pytest.mark.parametrize('path',[API,API+'/1','/employer/search','/employer/candidates/1'])
def test_permissions(client,candidate_headers,path):
    assert client.get(path).status_code==401
    assert client.get(path,headers=candidate_headers).status_code==403
@pytest.mark.parametrize('idx',[4,5,6,7,8])
def test_hidden_direct_profile(client,headers,database,idx):
    pid=database[1]['profiles'][idx].id
    for path in [API+f'/{pid}',f'/employer/candidates/{pid}']: assert client.get(path,headers=headers).status_code==404

def test_no_contacts_and_safe_details(client,headers,database):
    pid=database[1]['profiles'][0].id
    for path in [API,API+f'/{pid}','/employer/search',f'/employer/candidates/{pid}']:
        r=client.get(path,headers=headers);assert r.status_code==200,r.text
        for secret in ['candidate-secret-','secret-contact@example.invalid','999','secret_handle','password_hash','registry_participant_id','question_snapshot']: assert secret not in r.text
    data=client.get(API+f'/{pid}',headers=headers).json()
    assert data['fsp_achievements']==[] and data['results'][0]['score']==80
    assert data['experiences'][0]['description']=='[контакт скрыт]'
    assert 'email' not in data and 'phone' not in data

def test_fsp_optional_date(client,headers,database):
    pid=database[1]['profiles'][1].id;data=client.get(API+f'/{pid}',headers=headers).json()
    assert data['fsp_achievements'][0]['competition_date']=='2025-01-01' and data['fsp_achievements'][0]['is_demo']
    assert 'Демонстрационное достижение' in client.get(f'/employer/candidates/{pid}',headers=headers).text

def test_failed_current_cannot_resurrect_history(client,headers,database):
    engine,data=database
    with Session(engine) as s:
        s.add(CandidateCategory(candidate_profile_id=data['profiles'][0].id,category_id=data['category'].id,is_current=True,status=CategoryStatus.NOT_CONFIRMED));s.commit()
    assert client.get(API+'/1',headers=headers).status_code==404
    assert client.get(API,headers=headers).json()['meta']['total']==3

def test_htmx_and_restore(client,headers):
    url='/employer/search?skills=Python&page_size=2&page=2'
    r=client.get(url,headers={**headers,'HX-Request':'true'});assert r.status_code==200
    assert '<html' not in r.text and 'id="matching-results"' in r.text
    assert 'skills=Python' in r.text and 'page_size=2' in r.text
    assert 'HX-History-Restore-Request' in r.headers['vary']
    assert '<html' in client.get(url,headers={**headers,'HX-Request':'true','HX-History-Restore-Request':'true'}).text

def test_publication_owner_revoke(client,headers,candidate_headers):
    route='/api/v1/candidates/me/search-publication'
    assert client.patch(route,headers=headers,json={'is_searchable':False}).status_code==403
    assert client.patch(route,headers=candidate_headers,json={'is_searchable':False}).json()=={'is_searchable':False}
    assert client.get(API+'/1',headers=headers).status_code==404
    assert client.patch(route,headers=candidate_headers,json={'is_searchable':True}).status_code==200
    assert client.get(API+'/1',headers=headers).status_code==200

def test_cookie_csrf(client,database):
    from app.modules.auth.security import create_access_token
    from app.modules.matching.publication import csrf_token
    uid=database[1]['candidate'].id;client.cookies.set('access_token',create_access_token(uid))
    assert client.post('/candidate/search-publication',data={'published':'yes'}).status_code==403
    assert client.post('/candidate/search-publication',data={'token':csrf_token(uid)},follow_redirects=False).status_code==303
    assert client.get('/api/v1/candidates/me/search-publication').json()['is_searchable'] is False
    assert client.patch('/api/v1/candidates/me/search-publication',json={'is_searchable':True}).status_code==403

def test_missing(client,headers): assert client.get(API+'/99999',headers=headers).status_code==404

def test_query_postgresql():
    from sqlalchemy.dialects import postgresql
    from app.modules.matching.queries import page_candidates
    from app.modules.matching.schemas import CandidateSearchQuery
    sql=str(page_candidates(CandidateSearchQuery(skills=['python','sql'],all_skills=True)).compile(dialect=postgresql.dialect()))
    assert sql.count('EXISTS')==2 and 'LIMIT' in sql and 'OFFSET' in sql and 'max(' in sql


def test_default_publication_is_private(database):
    from app.modules.auth.models import User,UserRole
    from app.modules.candidates.models import CandidateProfile
    with Session(database[0]) as session:
        u=User(email='new-private@example.invalid',password_hash='unused',role=UserRole.CANDIDATE)
        session.add(u);session.flush()
        p=CandidateProfile(user_id=u.id,full_name='Private')
        session.add(p);session.commit();session.refresh(p)
        assert p.is_searchable is False


def test_html_escapes_professional_text(client,headers,database):
    from app.modules.candidates.models import CandidateProfile
    with Session(database[0]) as session:
        p=session.get(CandidateProfile,1);p.about='<script>alert(1)</script>';session.commit()
    response=client.get('/employer/candidates/1',headers=headers)
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in response.text
    assert '<script>alert(1)</script>' not in response.text


def test_matches_explain_all_skills(client,headers):
    data=client.get(API+'?skills=PYTHON&skills=sql&all_skills=true',headers=headers).json()
    assert all(set(c['matched_skills'])=={'python','sql'} for c in data['items'])
    assert all(any('Совпали все' in reason for reason in c['match_reasons']) for c in data['items'])


def test_any_skills_explanation(client,headers):
    data=client.get(API+'?skills=Python&skills=Rust',headers=headers).json()
    assert data['meta']['total']==4
    assert all(c['matched_skills']==['python'] for c in data['items'])
    assert all(any('Совпавшие навыки:' in reason for reason in c['match_reasons']) for c in data['items'])
    assert all(not any('Совпали все' in reason for reason in c['match_reasons']) for c in data['items'])

def test_all_skills_allows_extra_skills(client,headers):
    data=client.get(API+'?skills=SQL&all_skills=true',headers=headers).json()
    assert data['meta']['total']==3
    assert all({'python','sql'}.issubset({s['skill'].lower() for s in c['skills']}) for c in data['items'])

def test_any_skills_sql_uses_in():
    from sqlalchemy.dialects import postgresql
    from app.modules.matching.queries import page_candidates
    from app.modules.matching.schemas import CandidateSearchQuery
    sql=str(page_candidates(CandidateSearchQuery(skills=['python','sql'])).compile(dialect=postgresql.dialect()))
    assert sql.count('EXISTS')==1 and ' IN (' in sql

def test_all_skills_preserved_in_pagination_and_form(client,headers):
    r=client.get('/employer/search?skills=Python,SQL&all_skills=true&page_size=1',headers=headers)
    assert r.status_code==200
    assert 'name="all_skills" value="true" checked' in r.text
    assert 'all_skills=true' in r.text and 'page=2' in r.text
    assert client.get('/employer/search?all_skills=invalid',headers=headers).status_code==422
