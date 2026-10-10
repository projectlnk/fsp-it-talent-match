"""Бизнес-логика аутентификации: регистрация, вход, подтверждение email."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from html import escape
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import EmailDeliveryError, send_email
from app.modules.auth.models import EmailVerificationToken, User, UserRole
from app.modules.auth.security import (
    create_access_token,
    generate_email_verification_token,
    hash_password,
    verify_password,
)
from app.modules.candidates.models import CandidateProfile
from app.modules.employers.models import EmployerProfile


class AuthError(Exception):
    """Базовая ошибка модуля auth."""


class EmailAlreadyExists(AuthError):
    """Пользователь с таким email уже зарегистрирован."""


class InvalidCredentials(AuthError):
    """Неверный email или пароль, либо аккаунт деактивирован."""


class InvalidVerificationToken(AuthError):
    """Токен подтверждения не найден, уже использован или истёк."""


class VerificationEmailDeliveryError(AuthError):
    """Аккаунт и токен сохранены, но письмо не отправлено."""


class ExpiredVerificationToken(InvalidVerificationToken):
    pass


class AlreadyVerifiedEmail(InvalidVerificationToken):
    pass


def register_user(
    session: Session,
    *,
    email: str,
    password: str,
    role: UserRole,
    full_name: str | None = None,
    processing_consent: bool = False,
) -> User:
    """Регистрирует пользователя и создаёт профиль по его роли.

    Коммитит изменения. При конфликте email поднимает EmailAlreadyExists.
    Отправляет письмо с ссылкой подтверждения.
    """
    email_normalized = email.strip().lower()

    existing = session.scalar(select(User).where(User.email == email_normalized))
    if existing is not None:
        raise EmailAlreadyExists(email_normalized)

    user = User(
        email=email_normalized,
        password_hash=hash_password(password),
        role=role,
        is_email_verified=False,
        is_active=True,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise EmailAlreadyExists(email_normalized) from exc

    if role is UserRole.CANDIDATE:
        session.add(CandidateProfile(user_id=user.id, full_name=full_name or ""))
    elif role is UserRole.EMPLOYER:
        session.add(EmployerProfile(user_id=user.id, company_name=full_name or ""))

    token = _create_verification_token(session, user)
    if processing_consent:
        from app.modules.career.service import consent
        consent(session, user.id, 'processing', True)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise EmailAlreadyExists(email_normalized) from exc

    session.refresh(user)
    _send_verification_email(user, token)
    return user


def authenticate_user(session: Session, *, email: str, password: str) -> User:
    """Проверяет email и пароль, возвращает пользователя.

    Поднимает InvalidCredentials при неверных данных или неактивном аккаунте.
    """
    email_normalized = email.strip().lower()
    user = session.scalar(select(User).where(User.email == email_normalized))
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentials()
    if not user.is_active:
        raise InvalidCredentials()
    return user


def issue_access_token(user: User) -> tuple[str, int]:
    """Выпускает JWT для пользователя.

    Возвращает (token, expires_in_seconds).
    """
    settings = get_settings()
    token = create_access_token(user.id, extra={"role": user.role.value})
    expires_in = settings.jwt_access_token_expire_minutes * 60
    return token, expires_in


def verify_email(session: Session, *, token: str) -> User:
    """Подтверждает email по токену.

    Поднимает InvalidVerificationToken, если токен не найден, уже использован
    или истёк.
    """
    record = session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.token == token).with_for_update()
    )
    if record is None:
        raise InvalidVerificationToken()
    if record.used_at is not None:
        user = session.get(User, record.user_id)
        if user is not None and user.is_email_verified:
            raise AlreadyVerifiedEmail()
        raise InvalidVerificationToken()

    now = datetime.now(UTC)
    if record.expires_at <= now:
        raise ExpiredVerificationToken()

    user = session.get(User, record.user_id)
    if user is None:
        raise InvalidVerificationToken()

    user.is_email_verified = True
    record.used_at = now
    session.commit()
    session.refresh(user)
    return user


def resend_verification_email(session: Session, *, user: User) -> None:
    """Создаёт новый токен и отправляет письмо повторно.

    Ничего не делает, если email уже подтверждён.
    """
    if user.is_email_verified:
        return
    token = _create_verification_token(session, user)
    session.commit()
    _send_verification_email(user, token)


def _create_verification_token(session: Session, user: User) -> str:
    """Генерирует токен, сохраняет его и возвращает строку."""
    settings = get_settings()
    token = generate_email_verification_token()
    expires_at = datetime.now(UTC) + timedelta(
        hours=settings.email_verification_token_expire_hours
    )
    session.add(
        EmailVerificationToken(user_id=user.id, token=token, expires_at=expires_at)
    )
    return token


def _send_verification_email(user: User, token: str) -> None:
    """Собирает и отправляет письмо с ссылкой подтверждения."""
    settings = get_settings()
    link = settings.app_base_url.rstrip("/") + "/auth/verify?" + urlencode({"token": token})
    body = (
        "Здравствуйте!\n\n"
        "Подтвердите email на платформе FSP IT Talent Match.\n"
        f"Перейдите по ссылке:\n{link}\n\n"
        f"Ссылка действует {settings.email_verification_token_expire_hours} ч.\n\n"
        "Если вы не регистрировались — проигнорируйте письмо."
    )
    html = (
        '<html lang="ru"><body><h1>FSP IT Talent Match</h1>'
        '<p>Здравствуйте! Подтвердите email, чтобы завершить регистрацию.</p>'
        f'<p><a href="{escape(link, quote=True)}">Подтвердить email</a></p>'
        f'<p>Если ссылка не открывается, скопируйте её: {escape(link)}</p>'
        f'<p>Ссылка действует {settings.email_verification_token_expire_hours} ч.</p>'
        '<p>Если вы не создавали аккаунт, проигнорируйте письмо.</p></body></html>'
    )
    try:
        send_email(to=user.email, subject="Подтверждение email — FSP IT Talent Match",
                   body=body, html_body=html)
    except EmailDeliveryError:
        raise VerificationEmailDeliveryError() from None
