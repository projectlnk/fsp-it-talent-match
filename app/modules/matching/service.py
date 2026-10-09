"""Сервис поиска кандидатов.

Работает по категориям, присвоенным по итогам тестирования, а не по
самоописанному резюме. Внутри категории ранжирует кандидатов по силе
подтверждённого профиля.

Контакты кандидата не возвращаются: телефон и email скрыты до принятия
приглашения. ФИО и места работы показывать допустимо (Q&A).
"""
from __future__ import annotations

from sqlalchemy import Select, exists, func, select
from sqlalchemy.orm import Session, selectinload

from app.modules.assessments.models import (
    CandidateCategory,
    Category,
    CategoryStatus,
    Grade,
    Specialization,
)
from app.modules.candidates.models import (
    CandidateProfile,
    CandidateSkill,
    FspAchievement,
)
from app.modules.matching.schemas import (
    CandidateCardRead,
    CandidateExperienceBrief,
    CandidateSearchQuery,
    CandidateSearchResult,
    CandidateSkillBrief,
    FspAchievementBrief,
    SearchMeta,
)

from app.modules.matching.ranking import rank_candidate

class MatchingError(Exception):
    """Базовая ошибка модуля поиска."""


class InvalidFilter(MatchingError):
    """Некорректное значение фильтра."""

class CandidateNotFound(MatchingError):
    """Кандидат не найден или не имеет подтверждённой категории."""


def _base_query(query: CandidateSearchQuery) -> Select:
    """Строит SELECT по текущим категориям с фильтрами.

    Использует JOIN к категории, специализации и грейду. Профиль
    присоединяется через candidate_profile_id. Скрывает:
    - контактные данные (не выбираются);
    - недоступные категории (только is_current).
    """
    stmt = (
        select(CandidateProfile, CandidateCategory, Category, Specialization, Grade)
        .join(CandidateCategory, CandidateCategory.candidate_profile_id == CandidateProfile.id)
        .join(Category, Category.id == CandidateCategory.category_id)
        .join(Specialization, Specialization.id == Category.specialization_id)
        .join(Grade, Grade.id == Category.grade_id)
        .where(CandidateCategory.is_current.is_(True))
    )

    if query.only_confirmed:
        stmt = stmt.where(CandidateCategory.status == CategoryStatus.CONFIRMED)
    else:
        # Неподтверждённые показываем, но не отсекаем подтверждённые
        stmt = stmt.where(
            CandidateCategory.status.in_(
                [CategoryStatus.CONFIRMED, CategoryStatus.NOT_CONFIRMED]
            )
        )

    if query.specialization:
        stmt = stmt.where(Specialization.code == query.specialization)

    if query.grade:
        stmt = stmt.where(Grade.code == query.grade)

    if query.skills:
        normalized = [s.strip().lower() for s in query.skills if s.strip()]
        if normalized:
            subq = (
                select(CandidateSkill.candidate_profile_id)
                .where(func.lower(CandidateSkill.skill).in_(normalized))
                .scalar_subquery()
            )
            stmt = stmt.where(CandidateProfile.id.in_(subq))

    if query.has_fsp_achievements is True:
        stmt = stmt.where(
            exists(
                select(FspAchievement.id).where(
                    FspAchievement.candidate_profile_id == CandidateProfile.id
                )
            )
        )
    elif query.has_fsp_achievements is False:
        stmt = stmt.where(
            ~exists(
                select(FspAchievement.id).where(
                    FspAchievement.candidate_profile_id == CandidateProfile.id
                )
            )
        )

    return stmt


def _count_query(query: CandidateSearchQuery) -> Select:
    """Строит SELECT для подсчёта общего числа без пагинации."""
    inner = _base_query(query).with_only_columns(CandidateProfile.id).subquery()
    return select(func.count()).select_from(inner)


def _load_profiles(session: Session, ids: list[int]) -> dict[int, CandidateProfile]:
    """Загружает профили с навыками, опытом и достижениями одним запросом."""
    if not ids:
        return {}
    profiles = session.scalars(
        select(CandidateProfile)
        .where(CandidateProfile.id.in_(ids))
        .options(
            selectinload(CandidateProfile.skills),
            selectinload(CandidateProfile.experiences),
            selectinload(CandidateProfile.fsp_achievements),
        )
    ).all()
    return {p.id: p for p in profiles}


def _to_card(
    profile: CandidateProfile,
    category_record: CandidateCategory,
    specialization: Specialization,
    grade: Grade,
) -> CandidateCardRead:
    """Собирает карточку кандидата с рассчитанным рейтингом."""
    achievements = sorted(
        profile.fsp_achievements,
        key=lambda a: (a.competition_date is None, a.competition_date),
        reverse=True,
    )

    ranking = rank_candidate(
        profile,
        specialization_code=specialization.code,
        test_score=category_record.test_score,
    )

    return CandidateCardRead(
        profile_id=profile.id,
        full_name=profile.full_name,
        location=profile.location,
        desired_role=profile.desired_role,
        desired_salary_from=profile.desired_salary_from,
        desired_salary_to=profile.desired_salary_to,
        experience_years=profile.experience_years,
        specialization_code=specialization.code,
        specialization_name=specialization.name,
        grade_code=grade.code,
        grade_name=grade.name,
        category_status=category_record.status.value,
        test_score=category_record.test_score,
        ranking_score=ranking.score,
        ranking_reasons=ranking.reasons,
        skills=[
            CandidateSkillBrief.model_validate(s)
            for s in sorted(profile.skills, key=lambda x: x.skill)
        ],
        experiences=[
            CandidateExperienceBrief.model_validate(e)
            for e in sorted(profile.experiences, key=lambda x: (not x.is_current, x.id))
        ],
        fsp_achievements=[
            FspAchievementBrief.model_validate(a) for a in achievements[:5]
        ],
        fsp_has_achievements=bool(profile.fsp_achievements),
    )

def search_candidates(
    session: Session,
    query: CandidateSearchQuery,
) -> CandidateSearchResult:
    """Выполняет поиск кандидатов с фильтрами и пагинацией.

    Возвращает страницу результатов и метаданные. Ранжирование —
    на уровне выборки: базовый порядок по test_score, детальный
    рейтинг появится в 5.2.3.
    """
    total = int(session.scalar(_count_query(query)) or 0)

    stmt = _base_query(query)
    # Черновая сортировка по test_score: точное ранжирование делаем
    # в Python после загрузки профилей, потому что рейтинг зависит от
    # достижений ФСП и релевантности дисциплин. Для больших выборок
    # это можно вынести в SQL, но на MVP пагинация по 20 элементов
    # сортируется в памяти мгновенно.
    stmt = stmt.order_by(
        CandidateCategory.test_score.desc().nullslast(),
        CandidateProfile.id.asc(),
    )
    # Забираем с запасом, чтобы после сортировки в Python отдать
    # стабильно заполненную страницу нужного размера
    fetch_limit = query.limit + query.offset
    stmt = stmt.limit(fetch_limit)

    rows = session.execute(stmt).all()
    if not rows:
        return CandidateSearchResult(
            items=[],
            meta=SearchMeta(total=total, limit=query.limit, offset=query.offset),
        )

    # Отдельная загрузка профилей с related-сущностями: одна выборка
    # по всем id, чтобы не было N+1
    profile_ids = [row[0].id for row in rows]
    profiles = _load_profiles(session, profile_ids)

    items: list[CandidateCardRead] = []
    for profile, category_record, category, spec, grade in rows:
        full_profile = profiles.get(profile.id, profile)
        items.append(_to_card(full_profile, category_record, spec, grade))

    items.sort(key=lambda c: (-c.ranking_score, c.profile_id))
    items = items[query.offset : query.offset + query.limit]

    return CandidateSearchResult(
        items=items,
        meta=SearchMeta(total=total, limit=query.limit, offset=query.offset),
    )

def get_candidate_card(session: Session, *, profile_id: int) -> CandidateCardRead:
    """Возвращает карточку конкретного кандидата.

    Показывает только кандидатов с активной категорией. Если у профиля
    нет текущей категории — карточка недоступна.
    """
    row = session.execute(
        select(CandidateProfile, CandidateCategory, Category, Specialization, Grade)
        .join(CandidateCategory, CandidateCategory.candidate_profile_id == CandidateProfile.id)
        .join(Category, Category.id == CandidateCategory.category_id)
        .join(Specialization, Specialization.id == Category.specialization_id)
        .join(Grade, Grade.id == Category.grade_id)
        .where(
            CandidateProfile.id == profile_id,
            CandidateCategory.is_current.is_(True),
        )
    ).first()

    if row is None:
        raise CandidateNotFound("Кандидат не найден")

    profile, category_record, category, spec, grade = row
    full_profile = _load_profiles(session, [profile.id]).get(profile.id, profile)
    return _to_card(full_profile, category_record, spec, grade)