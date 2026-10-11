"""Persist search templates and delegate every position to ordinary matching."""
from datetime import UTC, datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.modules.employers.models import EmployerProfile
from app.modules.assessments.models import Specialization, Grade
from app.modules.career.models import TeamNeedTemplate, TeamNeedPosition
from app.modules.matching.schemas import CandidateSearchQuery, TeamNeedInput
from app.modules.matching.service import search_candidates


def company_id(session, user_id):
    return session.scalar(select(EmployerProfile.id).where(EmployerProfile.user_id == user_id))


def list_templates(session, user_id):
    return list(session.scalars(select(TeamNeedTemplate)
        .where(TeamNeedTemplate.employer_id == company_id(session, user_id))
        .options(selectinload(TeamNeedTemplate.positions))
        .order_by(TeamNeedTemplate.updated_at.desc(), TeamNeedTemplate.id.desc())))


def get_template(session, user_id, template_id, lock=False):
    stmt = select(TeamNeedTemplate).where(TeamNeedTemplate.id == template_id,
        TeamNeedTemplate.employer_id == company_id(session, user_id))
    if lock:
        stmt = stmt.with_for_update()
    row = session.scalar(stmt.options(selectinload(TeamNeedTemplate.positions)))
    if row is None:
        raise HTTPException(404, 'Потребность команды не найдена')
    return row


def save_template(session, user_id, payload: TeamNeedInput, template_id=None):
    cid = company_id(session, user_id)
    if cid is None:
        raise HTTPException(404, 'Профиль компании не найден')
    for position in payload.positions:
        for code, model in [(position.filters.specialization, Specialization), (position.filters.grade, Grade)]:
            if code and not session.scalar(select(model.id).where(model.code == code)):
                raise HTTPException(422, 'Выберите специализацию и грейд из справочника')
    instant = datetime.now(UTC)
    row = get_template(session, user_id, template_id, lock=True) if template_id else TeamNeedTemplate(
        employer_id=cid, created_at=instant)
    row.name, row.updated_at = payload.name, instant
    session.add(row)
    # Flush old positions before reusing ordinal values under the unique key.
    row.positions.clear()
    session.flush()
    row.positions = [TeamNeedPosition(ordinal=i, name=p.name,
        filters=p.filters.model_dump(mode='json', exclude={'page', 'page_size'}))
        for i, p in enumerate(payload.positions)]
    session.flush()
    return row


def delete_template(session, user_id, template_id):
    session.delete(get_template(session, user_id, template_id, lock=True))
    session.flush()


def search_groups(session, user_id, template_id, params):
    row = get_template(session, user_id, template_id)
    groups = []
    for position in row.positions:
        filters = CandidateSearchQuery(**position.filters,
            page=params.get(f'position_page_{position.id}') or 1,
            page_size=params.get('page_size') or 20)
        groups.append({'position': position, 'filters': filters,
                       'result': search_candidates(session, filters)})
    return row, groups
