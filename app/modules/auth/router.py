"""JSON API модуля auth."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth import service
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    EmailVerificationRequest,
    MessageResponse,
    TokenResponse,
    UserLogin,
    UserRead,
    UserRegister,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация пользователя",
)
def register(payload: UserRegister, session: Session = Depends(get_session)) -> User:
    """Создаёт пользователя и профиль по его роли.

    Отправляет письмо с подтверждением email. Токен доступа не выдаётся.
    Вход пока разрешён и без подтверждения; обязательность подтверждения
    требует отдельного согласования.
    """
    try:
        return service.register_user(
            session,
            email=payload.email,
            password=payload.password,
            role=payload.role,
            full_name=payload.full_name,
            processing_consent=payload.processing_consent,
        )
    except service.EmailAlreadyExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email уже зарегистрирован",
        ) from exc

    except service.VerificationEmailDeliveryError:
        raise HTTPException(status_code=503, detail="Аккаунт создан, но письмо не отправлено. Войдите и запросите письмо повторно.") from None


@router.post("/login", response_model=TokenResponse, summary="Вход по email и паролю")
def login(payload: UserLogin, session: Session = Depends(get_session)) -> TokenResponse:
    """Проверяет email и пароль, выпускает JWT."""
    try:
        user = service.authenticate_user(
            session, email=payload.email, password=payload.password
        )
    except service.InvalidCredentials as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    token, expires_in = service.issue_access_token(user)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    summary="Подтверждение email по токену",
)
def verify_email(
    payload: EmailVerificationRequest,
    session: Session = Depends(get_session),
) -> MessageResponse:
    """Помечает email подтверждённым по одноразовому токену из письма."""
    try:
        service.verify_email(session, token=payload.token)
    except service.InvalidVerificationToken as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Токен недействителен или истёк",
        ) from exc
    return MessageResponse(message="Email подтверждён")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    summary="Повторная отправка письма с подтверждением",
)
def resend_verification(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MessageResponse:
    """Создаёт новый токен и отправляет письмо заново.

    Доступно только аутентифицированному пользователю — чтобы нельзя было
    слать письма на чужие адреса.
    """
    if current_user.is_email_verified:
        return MessageResponse(message="Email уже подтверждён")
    try:
        service.resend_verification_email(session, user=current_user)
    except service.VerificationEmailDeliveryError:
        raise HTTPException(status_code=503, detail="Письмо не отправлено. Попробуйте повторить позже.") from None
    return MessageResponse(message="Письмо отправлено повторно")


@router.get("/me", response_model=UserRead, summary="Текущий пользователь")
def me(current_user: User = Depends(get_current_user)) -> User:
    """Возвращает данные пользователя по access-токену."""
    return current_user
