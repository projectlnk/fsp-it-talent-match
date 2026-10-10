"""Working search pages and HTMX results use the same service as JSON."""
from typing import Literal
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.matching import service
from app.modules.matching.publication import csrf_token, check_csrf, CANDIDATE_ONLY
from app.modules.matching.schemas import CandidateSearchQuery
from app.web.templates import templates

router = APIRouter(include_in_schema=False)
EMPLOYER_ONLY = require_role(UserRole.EMPLOYER)

@router.get('/employer/search')
def search(request: Request, user: User = Depends(EMPLOYER_ONLY), session: Session = Depends(get_session)):
    params = request.query_params
    try:
        filters = CandidateSearchQuery(specialization=params.get('specialization'), grade=params.get('grade'),
            skills=[s for value in params.getlist('skills') for s in value.split(',')],
            all_skills=params.get('all_skills', False),
            location=params.get('location'), work_format=params.get('work_format') or None,
            page=params.get('page', 1), page_size=params.get('page_size', 20))
    except ValidationError:
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
    result = service.search_candidates(session, filters)
    def page_url(page):
        url = request.url.include_query_params(page=page)
        return url.path + '?' + url.query
    context = dict(user=user, filters=filters, result=result, page_url=page_url,
                   **service.reference_filters(session))
    partial = request.headers.get('hx-request') == 'true' and request.headers.get('hx-history-restore-request') != 'true'
    response = templates.TemplateResponse(request=request,
        name='matching/_results.html' if partial else 'matching/search.html', context=context)
    response.headers['Vary'] = 'HX-Request, HX-History-Restore-Request'
    response.headers['Cache-Control'] = 'no-store'
    return response

@router.get('/employer/candidates/{candidate_id}')
def detail(request: Request, candidate_id: int, user: User = Depends(EMPLOYER_ONLY), session: Session = Depends(get_session)):
    try:
        card = service.get_candidate_card(session, profile_id=candidate_id)
    except service.CandidateNotFound as exc:
        raise HTTPException(404, 'Кандидат не найден') from exc
    response = templates.TemplateResponse(request=request, name='matching/detail.html', context={'user': user, 'card': card})
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
