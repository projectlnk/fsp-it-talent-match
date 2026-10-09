"""Owner-controlled publication; cookie mutations require a CSRF token."""
import hashlib
import hmac
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.matching.service import set_publication, get_publication, CandidateNotFound
from app.modules.matching.schemas import SearchPublication

def no_cache(response: Response):
    response.headers['Cache-Control'] = 'no-store'

router = APIRouter(prefix='/candidates/me/search-publication', tags=['candidates'], dependencies=[Depends(no_cache)])
CANDIDATE_ONLY = require_role(UserRole.CANDIDATE)

def csrf_token(user_id):
    return hmac.new(get_settings().jwt_secret_key.encode(), f'search-publication:{user_id}'.encode(), hashlib.sha256).hexdigest()

def check_csrf(request, user_id, token):
    if not hmac.compare_digest((token or '').encode(), csrf_token(user_id).encode()):
        raise HTTPException(403, 'Обновите страницу и повторите сохранение')

@router.get('', response_model=SearchPublication)
def read_publication(user: User = Depends(CANDIDATE_ONLY), session: Session = Depends(get_session)):
    try:
        return SearchPublication(is_searchable=get_publication(session, user.id))
    except CandidateNotFound as exc:
        raise HTTPException(404, 'Профиль не найден') from exc

@router.patch('', response_model=SearchPublication)
def update_publication(payload: SearchPublication, request: Request,
    user: User = Depends(CANDIDATE_ONLY), session: Session = Depends(get_session),
    x_csrf_token: str | None = Header(None)):
    if not request.headers.get('authorization', '').lower().startswith('bearer '):
        check_csrf(request, user.id, x_csrf_token)
    try:
        return SearchPublication(is_searchable=set_publication(session, user.id, payload.is_searchable))
    except CandidateNotFound as exc:
        raise HTTPException(404, 'Профиль не найден') from exc
