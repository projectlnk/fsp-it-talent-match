"""Генерация PDF-резюме кандидата.

Отдельный модуль: собирает данные профиля, рендерит HTML-шаблон через
Jinja2 и превращает его в PDF через WeasyPrint.

WeasyPrint выбран вместо Playwright: не требует Chromium в runtime-образе,
рендерит HTML/CSS напрямую, работает синхронно. Ограничение — не весь CSS,
но для блочной вёрстки резюме этого достаточно.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.assessments.models import Category, Grade, Specialization, TestAttempt, AttemptStatus
from app.modules.assessments.service import current_category
from app.modules.auth.models import User
from app.modules.candidates.models import CandidateProfile, WorkFormat


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"

WORK_FORMAT_LABELS = {
    WorkFormat.OFFICE: "Офис",
    WorkFormat.REMOTE: "Удалённо",
    WorkFormat.HYBRID: "Гибрид",
}


class ResumeError(Exception):
    """Ошибка генерации резюме."""


class ProfileNotFound(ResumeError):
    """Профиль кандидата не найден."""


def _load_profile(session: Session, user_id: int) -> CandidateProfile:
    """Загружает профиль со всеми связями одним запросом."""
    profile = session.scalar(
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user_id)
        .options(
            selectinload(CandidateProfile.skills),
            selectinload(CandidateProfile.experiences),
            selectinload(CandidateProfile.fsp_achievements),
        )
    )
    if profile is None:
        raise ProfileNotFound("Профиль не найден")
    return profile


def _load_category_context(session: Session, user_id: int):
    """Возвращает объект категории с вложенными specialization и grade.

    None, если у кандидата нет текущей категории.
    """
    record = current_category(session, user_id=user_id)
    if record is None:
        return None

    row = session.execute(
        select(Category, Specialization, Grade)
        .join(Specialization, Specialization.id == Category.specialization_id)
        .join(Grade, Grade.id == Category.grade_id)
        .where(Category.id == record.category_id)
    ).first()
    if row is None:
        return None

    category, spec, grade = row

    # Лёгкий объект-контейнер, чтобы шаблон не знал про ORM
    class CategoryContext:
        pass

    ctx = CategoryContext()
    ctx.specialization = spec
    ctx.grade = grade
    ctx.test_score = record.test_score
    ctx.confirmed_at = record.confirmed_at
    ctx.status = record.status.value
    return ctx


def generate_resume_pdf(session: Session, *, user_id: int) -> bytes:
    """Собирает PDF-резюме и возвращает байты.

    Контакты попадают в PDF всегда — это документ, который кандидат
    скачивает сам для себя. Работодателю через API контакты не отдаются,
    раскрытие идёт только после принятия приглашения.
    """
    profile = _load_profile(session, user_id)
    user = session.get(User, user_id)
    category = _load_category_context(session, user_id)

    work_format_label = (
        WORK_FORMAT_LABELS.get(profile.work_format)
        if profile.work_format
        else None
    )

    results = session.execute(
        select(TestAttempt, Specialization, Grade)
        .join(Specialization, Specialization.id == TestAttempt.specialization_id)
        .join(Grade, Grade.id == TestAttempt.target_grade_id)
        .where(TestAttempt.candidate_profile_id == profile.id,
               TestAttempt.status == AttemptStatus.COMPLETED)
        .order_by(TestAttempt.finished_at.desc().nullslast(), TestAttempt.id.desc())
    ).all()
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)),
                      autoescape=select_autoescape(['html']))
    template = env.get_template("candidates/resume_pdf.html")
    html = template.render(
        profile=profile,
        category=category,
        results=results,
        work_format_label=work_format_label,
        user_email=user.email if user else None,
        generated_at=datetime.now(UTC),
    )

    # Ленивый импорт: на хосте (без системных библиотек pango/cairo/gobject)
    # WeasyPrint недоступен, но приложение и тесты должны загружаться.
    # В runtime-образе (контейнер) всё установлено и работает.
    try:
        from weasyprint import HTML
    except OSError as exc:
        raise ResumeError(
            "WeasyPrint не может загрузить системные библиотеки. "
            "Убедитесь, что приложение запущено в Docker-образе."
        ) from exc

    try:
        pdf = HTML(string=html).write_pdf()
    except Exception as exc:
        raise ResumeError(f"Не удалось сгенерировать PDF: {exc}") from exc
    return pdf
