"""JSON API профиля кандидата.

Все эндпоинты защищены ролью candidate и работают с профилем текущего
пользователя. Обращения по candidate_profile_id извне нет — это исключает
доступ к чужому профилю.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.candidates import service
from app.modules.candidates.schemas import (
    CandidateExperienceCreate,
    CandidateExperienceUpdate,
    CandidateProfileRead,
    CandidateProfileUpdate,
    CandidateSkillCreate,
    CandidateSkillUpdate,
)

from app.modules.candidates.fsp_router import router as fsp_router

from fastapi import Response
from app.modules.candidates import resume as resume_service

router = APIRouter(prefix="/candidates", tags=["candidates"])

router.include_router(fsp_router)

_CANDIDATE_ONLY = require_role(UserRole.CANDIDATE)


def _handle_service_error(exc: service.CandidateError) -> HTTPException:
    """Преобразует ошибки сервиса в HTTPException."""
    if isinstance(exc, service.ProfileNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Профиль не найден")
    if isinstance(exc, service.SkillAlreadyExists):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Навык уже добавлен")
    if isinstance(exc, (service.SkillNotFound, service.ExperienceNotFound)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный запрос")


@router.get("/me", response_model=CandidateProfileRead, summary="Профиль текущего кандидата")
def get_me(
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        return service.get_profile_by_user_id(session, user.id)
    except service.CandidateError as exc:
        raise _handle_service_error(exc) from exc


@router.patch("/me", response_model=CandidateProfileRead, summary="Обновить профиль")
def update_me(
    payload: CandidateProfileUpdate,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    changes = payload.model_dump(exclude_unset=True)
    try:
        return service.update_profile(session, user_id=user.id, changes=changes)
    except service.CandidateError as exc:
        raise _handle_service_error(exc) from exc


# --- Навыки --------------------------------------------------------------


@router.post(
    "/me/skills",
    response_model=CandidateProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить навык",
)
def add_skill(
    payload: CandidateSkillCreate,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        return service.add_skill(
            session, user_id=user.id, skill=payload.skill, level=payload.level
        )
    except service.CandidateError as exc:
        raise _handle_service_error(exc) from exc


@router.patch(
    "/me/skills/{skill_id}",
    response_model=CandidateProfileRead,
    summary="Обновить навык",
)
def update_skill(
    skill_id: int,
    payload: CandidateSkillUpdate,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    changes = payload.model_dump(exclude_unset=True)
    try:
        return service.update_skill(
            session, user_id=user.id, skill_id=skill_id, changes=changes
        )
    except service.CandidateError as exc:
        raise _handle_service_error(exc) from exc


@router.delete(
    "/me/skills/{skill_id}",
    response_model=CandidateProfileRead,
    summary="Удалить навык",
)
def delete_skill(
    skill_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        return service.delete_skill(session, user_id=user.id, skill_id=skill_id)
    except service.CandidateError as exc:
        raise _handle_service_error(exc) from exc


# --- Опыт ----------------------------------------------------------------


@router.post(
    "/me/experiences",
    response_model=CandidateProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить место работы",
)
def add_experience(
    payload: CandidateExperienceCreate,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        return service.add_experience(
            session, user_id=user.id, data=payload.model_dump()
        )
    except service.CandidateError as exc:
        raise _handle_service_error(exc) from exc


@router.patch(
    "/me/experiences/{experience_id}",
    response_model=CandidateProfileRead,
    summary="Обновить место работы",
)
def update_experience(
    experience_id: int,
    payload: CandidateExperienceUpdate,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    changes = payload.model_dump(exclude_unset=True)
    try:
        return service.update_experience(
            session, user_id=user.id, experience_id=experience_id, changes=changes
        )
    except service.CandidateError as exc:
        raise _handle_service_error(exc) from exc


@router.delete(
    "/me/experiences/{experience_id}",
    response_model=CandidateProfileRead,
    summary="Удалить место работы",
)
def delete_experience(
    experience_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        return service.delete_experience(
            session, user_id=user.id, experience_id=experience_id
        )
    except service.CandidateError as exc:
        raise _handle_service_error(exc) from exc

# --- PDF-резюме -----------------------------------------------------------


@router.get(
    "/me/resume.pdf",
    summary="Скачать PDF-резюме",
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF-резюме кандидата",
        },
    },
)
def download_resume(
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    """Генерирует и возвращает PDF-резюме текущего кандидата.

    Доступно только владельцу. Чужие резюме недоступны — ручка работает
    от текущего пользователя.
    """
    try:
        pdf_bytes = resume_service.generate_resume_pdf(session, user_id=user.id)
    except resume_service.ProfileNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except resume_service.ResumeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    filename = f"resume_{user.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )