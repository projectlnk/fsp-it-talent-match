"""Зависимости FastAPI: получение текущего пользователя и проверка роли.

Токен принимается из заголовка Authorization: Bearer ... или из cookie
`access_token`, чтобы HTML-формы и JSON API работали одинаково.
"""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.models import User, UserRole
from app.modules.auth.security import decode_access_token

# auto_error=False, чтобы не падать, если заголовка нет —
# тогда попробуем cookie для HTML-страниц.
_bearer_scheme = HTTPBearer(auto_error=False)

COOKIE_NAME = "access_token"


def _extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    """Возвращает токен из заголовка или cookie, если он есть."""
    if credentials is not None and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return request.cookies.get(COOKIE_NAME)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    """Возвращает текущего пользователя по JWT.

    Поднимает 401, если токен отсутствует, невалиден или пользователь
    неактивен.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Требуется аутентификация",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = _extract_token(request, credentials)
    if not token:
        raise unauthorized

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Срок действия токена истёк",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise unauthorized from exc

    subject = payload.get("sub")
    if subject is None:
        raise unauthorized

    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise unauthorized from exc

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized

    return user


def require_role(*roles: UserRole):
    """Фабрика зависимостей: пропускает только указанные роли.

    Использование:

        @router.get("/employer-only")
        def endpoint(user: User = Depends(require_role(UserRole.EMPLOYER))):
            ...
    """
    allowed = set(roles)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return user

    return dependency