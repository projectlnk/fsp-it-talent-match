"""HTML-страницы модуля auth: регистрация, вход, подтверждение email."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import ValidationError
from app.modules.auth.schemas import UserRegister

from app.db.session import get_session
from app.modules.auth import service
from app.modules.auth.dependencies import COOKIE_NAME, get_current_user_optional
from app.modules.auth.models import User, UserRole
from app.web.templates import templates

router = APIRouter(prefix="/auth", tags=["auth-web"], include_in_schema=False)


def _safe_next(value: str | None) -> str:
    """Защита от open redirect: разрешаем только относительные пути."""
    if (not value or not value.startswith("/") or value.startswith("//")
            or "\\" in value or any(ord(char) < 32 for char in value)):
        return "/"
    return value


@router.get("/register", response_class=HTMLResponse)
def register_form(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
):
    if user is not None:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={"user": None, "error": None, "email": "", "role": "candidate", "full_name": ""},
    )


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    full_name: str = Form(""),
    session: Session = Depends(get_session),
):
    error: str | None = None
    try:
        payload = UserRegister(email=email, password=password, role=role,
                               full_name=full_name or None)
        service.register_user(session, **payload.model_dump())
        return RedirectResponse("/auth/check-email", status_code=status.HTTP_303_SEE_OTHER)
    except ValidationError:
        error = "Проверьте email, роль, имя и пароль (от 8 до 128 символов)"
    except service.EmailAlreadyExists:
        error = "Пользователь с таким email уже зарегистрирован"

    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={
            "user": None,
            "error": error,
            "email": email,
            "role": role,
            "full_name": full_name,
        },
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    next: str | None = None,
    user: User | None = Depends(get_current_user_optional),
):
    if user is not None:
        return RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={"user": None, "error": None, "email": "", "next": _safe_next(next)},
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    session: Session = Depends(get_session),
):
    try:
        user = service.authenticate_user(session, email=email, password=password)
    except service.InvalidCredentials:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "user": None,
                "error": "Неверный email или пароль",
                "email": email,
                "next": _safe_next(next),
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token, expires_in = service.issue_access_token(user)
    response = RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=expires_in,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/check-email", response_class=HTMLResponse)
def check_email(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/check_email.html",
        context={"user": None},
    )


@router.get("/verify", response_class=HTMLResponse)
def verify_email_page(
    request: Request,
    token: str,
    session: Session = Depends(get_session),
):
    success = False
    try:
        service.verify_email(session, token=token)
        success = True
        message = "Email подтверждён. Теперь можно войти."
    except service.InvalidVerificationToken:
        message = "Ссылка недействительна или истекла. Запросите письмо заново."

    return templates.TemplateResponse(
        request=request,
        name="auth/verify_result.html",
        context={"user": None, "message": message, "success": success},
        status_code=200 if success else status.HTTP_400_BAD_REQUEST,
    )