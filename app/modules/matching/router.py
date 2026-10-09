"""Employer-only JSON search with bounded page pagination."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.matching import service
from app.modules.matching.schemas import CandidateSearchQuery, CandidateSearchResult, CandidateDetailRead

def no_cache(response: Response):
    response.headers['Cache-Control'] = 'no-store'

router = APIRouter(prefix='/matching', tags=['matching'], dependencies=[Depends(no_cache)])
_EMPLOYER_ONLY = require_role(UserRole.EMPLOYER)

@router.get('/candidates', response_model=CandidateSearchResult)
def search_candidates(filters: Annotated[CandidateSearchQuery, Query()],
    user: User = Depends(_EMPLOYER_ONLY), session: Session = Depends(get_session)):
    return service.search_candidates(session, filters)

@router.get('/candidates/{candidate_id}', response_model=CandidateDetailRead)
def get_candidate(candidate_id: int, user: User = Depends(_EMPLOYER_ONLY), session: Session = Depends(get_session)):
    try:
        return service.get_candidate_card(session, profile_id=candidate_id)
    except service.CandidateNotFound as exc:
        raise HTTPException(404, 'Кандидат не найден') from exc
