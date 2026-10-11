"""Working search pages and HTMX results use the same service as JSON."""
from typing import Literal
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.matching import service, needs
from app.modules.matching.publication import csrf_token, check_csrf, CANDIDATE_ONLY
from app.modules.matching.schemas import CandidateSearchQuery, TeamNeedInput, search_query_from_params
from app.web.templates import templates

router = APIRouter(include_in_schema=False)
EMPLOYER_ONLY = require_role(UserRole.EMPLOYER)

@router.get('/employer/search')
def search(request: Request, user: User = Depends(EMPLOYER_ONLY), session: Session = Depends(get_session)):
    params = request.query_params
    try:
        filters = search_query_from_params(params)
        selected_need, groups = None, []
        if params.get('need_id'):
            selected_need, groups = needs.search_groups(session, user.id, int(params['need_id']), params)
    except (ValidationError, ValueError):
        message = 'Некорректные фильтры или параметры страницы. Проверьте количество навыков и размер страницы (1–50).'
        if request.headers.get('hx-request') == 'true':
            # HTMX swaps successful responses; keep the error visible inside its target.
            response = HTMLResponse('<section id="matching-results" role="alert" class="alert alert-error">' + message + '</section>')
        else:
            response = templates.TemplateResponse(request=request, name='matching/invalid_filters.html',
                context={'user': user, 'error': message}, status_code=422)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Vary'] = 'HX-Request, HX-History-Restore-Request'
        return response
    result = service.search_candidates(session, filters) if selected_need is None else None
    def page_url(page):
        url = request.url.include_query_params(page=page)
        return url.path + '?' + url.query
    def group_page_url(position_id, page):
        url = request.url.include_query_params(**{f'position_page_{position_id}': page})
        return url.path + '?' + url.query
    context = dict(user=user, filters=filters, result=result, page_url=page_url,
                   need_templates=needs.list_templates(session, user.id), selected_need=selected_need,
                   groups=groups, group_page_url=group_page_url,
                   return_to=request.url.path + ('?' + request.url.query if request.url.query else ''),
                   **service.reference_filters(session))
    partial = request.headers.get('hx-request') == 'true' and request.headers.get('hx-history-restore-request') != 'true'
    response = templates.TemplateResponse(request=request,
        name=('matching/_group_results.html' if selected_need else 'matching/_results.html') if partial else 'matching/search.html', context=context)
    response.headers['Vary'] = 'HX-Request, HX-History-Restore-Request'
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.get('/employer/team-needs')
def team_needs(request: Request, user: User = Depends(EMPLOYER_ONLY), session: Session = Depends(get_session)):
    return templates.TemplateResponse(request=request, name='matching/team_needs.html',
        context={'user': user, 'need_templates': needs.list_templates(session, user.id),
                 'csrf_token': csrf_token(user.id)}, headers={'Cache-Control': 'no-store'})


def need_form(request, user, session, item=None, positions=None, name=None, error=None):
    if positions is None:
        positions = [{'name': p.name, 'filters': p.filters} for p in item.positions] if item else [
            {'name': '', 'filters': CandidateSearchQuery()}]
    return templates.TemplateResponse(request=request, name='matching/team_need_form.html',
        context=dict(user=user, item=item, positions=positions, name=name if name is not None else item.name if item else '',
                     error=error, csrf_token=csrf_token(user.id), **service.reference_filters(session)),
        status_code=422 if error else 200, headers={'Cache-Control': 'no-store'})


@router.get('/employer/team-needs/new')
def new_need(request: Request, user: User = Depends(EMPLOYER_ONLY), session: Session = Depends(get_session)):
    return need_form(request, user, session)


@router.get('/employer/team-needs/{template_id}/edit')
def edit_need(request: Request, template_id: int, user: User = Depends(EMPLOYER_ONLY), session: Session = Depends(get_session)):
    return need_form(request, user, session, needs.get_template(session, user.id, template_id))


async def submit_need(request, user, session, template_id=None):
    item = needs.get_template(session, user.id, template_id) if template_id else None
    form = await request.form()
    check_csrf(request, user.id, form.get('token'))
    indexes = form.getlist('position_index')
    if not 1 <= len(indexes) <= 10 or len(set(indexes)) != len(indexes) or any(not i.isdecimal() or len(i)>4 for i in indexes):
        return need_form(request, user, session, item, error='Добавьте от 1 до 10 позиций.')
    positions = []
    for index in indexes:
        prefix = 'position_' + index + '_'
        raw = {key: form.get(prefix + key) or None for key in CandidateSearchQuery.model_fields if key not in ('page','page_size','skills','all_skills')}
        raw['all_skills'] = form.get(prefix + 'all_skills') == 'true'
        raw['skills'] = [s.strip() for value in form.getlist(prefix+'skills') for s in value.split(',') if s.strip()]
        positions.append({'name': form.get(prefix + 'name', ''), 'filters': raw})
    try:
        payload = TeamNeedInput(name=form.get('name', ''), positions=positions)
        row = needs.save_template(session, user.id, payload, template_id)
        session.commit()
    except ValidationError:
        session.rollback()
        return need_form(request,user,session,item,positions,form.get('name',''),
            'Проверьте названия позиций, диапазоны и фильтры. Названия обязательны, не более 255 символов; навыков — не более 20.')
    except HTTPException as exc:
        session.rollback()
        if exc.status_code != 422:
            raise
        return need_form(request,user,session,item,positions,form.get('name',''),exc.detail)
    return RedirectResponse(f'/employer/team-needs?saved={row.id}', status_code=303)


@router.post('/employer/team-needs')
async def create_need(request: Request, user: User = Depends(EMPLOYER_ONLY), session: Session = Depends(get_session)):
    return await submit_need(request, user, session)


@router.post('/employer/team-needs/{template_id}/edit')
async def update_need(request: Request, template_id: int, user: User = Depends(EMPLOYER_ONLY), session: Session = Depends(get_session)):
    return await submit_need(request, user, session, template_id)


@router.post('/employer/team-needs/{template_id}/delete')
def remove_need(request: Request, template_id: int, token: str = Form(''), user: User = Depends(EMPLOYER_ONLY), session: Session = Depends(get_session)):
    check_csrf(request, user.id, token)
    needs.delete_template(session, user.id, template_id)
    session.commit()
    return RedirectResponse('/employer/team-needs?deleted=1', status_code=303)

@router.get('/employer/candidates/{candidate_id}')
def detail(request: Request, candidate_id: int, user: User = Depends(EMPLOYER_ONLY), session: Session = Depends(get_session)):
    try:
        card = service.get_candidate_card(session, profile_id=candidate_id)
    except service.CandidateNotFound as exc:
        raise HTTPException(404, 'Кандидат не найден') from exc
    from app.modules.career.service import event, employer
    company=employer(session,user.id)
    event(session,company.id,f'resume-view:{candidate_id}','resume_view',0,'Просмотр опубликованного профиля; баллы общего рейтинга не начисляются')
    session.commit()
    from urllib.parse import urlsplit
    target = request.query_params.get('return_to', '/employer/search')
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.path != '/employer/search':
        target = '/employer/search'
    response = templates.TemplateResponse(request=request, name='matching/detail.html', context={'user': user, 'card': card, 'return_to': target})
    response.headers['Cache-Control'] = 'no-store'
    return response

@router.get('/candidate/search-publication')
def publication(request: Request, user: User = Depends(CANDIDATE_ONLY), session: Session = Depends(get_session)):
    return RedirectResponse('/candidate/profile#visibility', status_code=303)

@router.post('/candidate/search-publication')
def save_publication(request: Request, published: Literal['', 'yes'] = Form(''), token: str = Form(''),
    user: User = Depends(CANDIDATE_ONLY), session: Session = Depends(get_session)):
    check_csrf(request, user.id, token)
    try:
        service.set_publication(session, user.id, published == 'yes')
    except service.CandidateNotFound as exc:
        raise HTTPException(404, 'Профиль не найден') from exc
    return RedirectResponse('/candidate/profile?saved=1#visibility', status_code=303)
