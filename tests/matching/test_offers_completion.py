"""Offer routes and form use only the fixture-owned test database."""
import pytest
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from playwright.sync_api import expect
from app.modules.auth.security import create_access_token
from app.modules.employers.models import EmployerProfile, Offer
from app.modules.matching.service import set_publication


@pytest.fixture(autouse=True)
def offer_tables(database):
    engine, data = database
    EmployerProfile.__table__.create(engine, checkfirst=True)
    Offer.__table__.create(engine, checkfirst=True)
    with Session(engine) as session:
        session.add(EmployerProfile(user_id=data['employer'].id, company_name='Компания'))
        session.add(EmployerProfile(user_id=data['users'][8].id, company_name='Другая компания'))
        session.commit()


def payload(database):
    return dict(candidate_profile_id=database[1]['profiles'][0].id, title='Разработчик',
                description='Наша команда', salary_from=100000, salary_to=200000,
                salary_gross=False, contact_method='hr@example.invalid')


@pytest.mark.parametrize('decision', ['accepted', 'rejected'])
def test_revocation_existing_offer_and_repeat(client, database, headers, candidate_headers, decision):
    result = client.post('/api/v1/employers/offers', headers=headers, json=payload(database))
    assert result.status_code == 201
    offer_id = result.json()['id']
    assert result.json()['contacts'] is None
    with Session(database[0]) as session:
        set_publication(session, database[1]['candidate'].id, False)
    assert client.post('/api/v1/employers/offers', headers=headers, json=payload(database)).status_code == 404
    assert client.post('/employer/offers', headers=headers, data=payload(database), follow_redirects=False).status_code == 303
    assert client.get(f'/candidate/offers/{offer_id}', headers=candidate_headers).status_code == 200
    url = f'/api/v1/candidates/me/offers/{offer_id}/respond'
    first = client.post(url, headers=candidate_headers, json={'status': decision})
    repeat = client.post(url, headers=candidate_headers, json={'status': decision})
    assert first.status_code == repeat.status_code == 200
    assert first.json()['responded_at'] == repeat.json()['responded_at']
    assert client.post(url, headers=candidate_headers, json={'status': 'rejected' if decision == 'accepted' else 'accepted'}).status_code == 409
    employer = client.get(f'/api/v1/employers/offers/{offer_id}', headers=headers)
    assert employer.json()['status'] == decision
    assert bool(employer.json()['contacts']) == (decision == 'accepted')
    if decision == 'accepted':
        assert employer.json()['contacts']['email'] == database[1]['candidate'].email
    foreign = {'Authorization': 'Bearer ' + create_access_token(database[1]['users'][8].id)}
    assert client.get(f'/api/v1/employers/offers/{offer_id}', headers=foreign).status_code in (404, 400)
    assert client.get('/employer/offers', headers=headers).status_code == 200
    assert client.get('/candidate/offers', headers=candidate_headers).status_code == 200
    with Session(database[0]) as session:
        assert session.scalar(select(func.count()).select_from(Offer)) == 1


@pytest.mark.parametrize('salary', ['', '-1', 'abc', '1.5', '300000'])
def test_form_error_preserves_fields(client, database, headers, salary):
    form = payload(database)
    form['salary_from'] = salary
    form.pop('salary_gross')
    response = client.post('/employer/offers', headers=headers, data=form)
    assert response.status_code == 400
    assert 'role="alert"' in response.text
    assert 'value="Разработчик"' in response.text
    assert 'Наша команда</textarea>' in response.text
    assert 'value="hr@example.invalid"' in response.text
    assert 'name="salary_gross" value="1" checked' not in response.text
    with Session(database[0]) as session:
        assert session.scalar(select(func.count()).select_from(Offer)) == 0


def test_foreign_candidate_cannot_answer_or_repeat(client, database, headers, candidate_headers):
    created = client.post('/api/v1/employers/offers', headers=headers, json=payload(database))
    assert created.status_code == 201
    offer_id = created.json()['id']
    url = f'/api/v1/candidates/me/offers/{offer_id}/respond'
    foreign = {'Authorization': 'Bearer ' + create_access_token(database[1]['users'][1].id)}
    denied = client.post(url, headers=foreign, json={'status': 'accepted'})
    assert denied.status_code == 404
    with Session(database[0]) as session:
        offer = session.get(Offer, offer_id)
        assert offer.status.value == 'sent' and offer.responded_at is None
    accepted = client.post(url, headers=candidate_headers, json={'status': 'accepted'})
    assert accepted.status_code == 200
    denied_repeat = client.post(url, headers=foreign, json={'status': 'accepted'})
    assert denied_repeat.status_code == 404
    assert 'contacts' not in denied_repeat.json()
    with Session(database[0]) as session:
        offer = session.get(Offer, offer_id)
        assert offer.status.value == 'accepted'
        assert offer.responded_at == datetime.fromisoformat(accepted.json()['responded_at'])


@pytest.mark.e2e
def test_browser_offer_error_send_and_accept(page, matching_server, database, headers):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_extra_http_headers(headers)
    page.goto(matching_server + '/employer/candidates/1')
    page.locator('[name=title]').fill('Предложение команды')
    page.locator('[name=description]').fill('Работа над проектом')
    page.locator('[name=salary_from]').fill('300000')
    page.locator('[name=salary_to]').fill('200000')
    page.locator('[name=contact_method]').fill('hr@example.invalid')
    page.get_by_role('checkbox', name='До вычета НДФЛ').uncheck()
    page.get_by_role('button', name='Пригласить', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('Зарплата от')
    expect(page.locator('[name=title]')).to_have_value('Предложение команды')
    expect(page.locator('[name=description]')).to_have_value('Работа над проектом')
    expect(page.locator('[name=salary_from]')).to_have_value('300000')
    expect(page.locator('[name=contact_method]')).to_have_value('hr@example.invalid')
    expect(page.get_by_role('checkbox', name='До вычета НДФЛ')).not_to_be_checked()
    page.locator('[name=salary_from]').fill('100000')
    page.get_by_role('button', name='Пригласить', exact=True).click()
    expect(page).to_have_url(matching_server + '/employer/offers')
    page.get_by_role('link', name='Открыть', exact=True).click()
    assert database[1]['candidate'].email not in page.content()
    with Session(database[0]) as session:
        offer_id = session.scalar(select(Offer.id))
        set_publication(session, database[1]['candidate'].id, False)
    page.set_extra_http_headers({'Authorization': 'Bearer ' + create_access_token(database[1]['candidate'].id)})
    page.goto(matching_server + '/candidate/offers')
    page.get_by_role('link', name='Предложение команды', exact=True).click()
    page.locator('form:has(input[value="accepted"]) button').click()
    expect(page.locator('main')).to_contain_text('принято')
    page.set_extra_http_headers(headers)
    page.goto(matching_server + f'/employer/offers/{offer_id}')
    expect(page.locator('main')).to_contain_text(database[1]['candidate'].email)
    assert not errors
