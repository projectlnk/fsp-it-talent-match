"""CLI-хелпер: назначить кандидату подтверждённую категорию.

Используется в e2e-тестах, которые запускаются на хосте и не имеют
прямого доступа к БД. Вызывается через `docker compose exec`.

Пример:

    python -m app.scripts.grant_category user@example.com backend junior

Не предназначен для продакшна. В боевой системе категорию присваивает
только тест.
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.assessments.models import (
    CandidateCategory,
    Category,
    CategoryStatus,
    Grade,
    Specialization,
)
from app.modules.auth.models import User
from app.modules.candidates.models import CandidateProfile


def grant(email: str, spec_code: str, grade_code: str, test_score: int = 85) -> None:
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"ERROR: user {email!r} not found", file=sys.stderr)
            sys.exit(1)
        profile = session.scalar(
            select(CandidateProfile).where(CandidateProfile.user_id == user.id).with_for_update()
        )
        if profile is None:
            print(f"ERROR: profile for {email!r} not found", file=sys.stderr)
            sys.exit(1)

        spec = session.scalar(
            select(Specialization).where(Specialization.code == spec_code)
        )
        grade = session.scalar(select(Grade).where(Grade.code == grade_code))
        if spec is None or grade is None:
            print(
                f"ERROR: spec {spec_code!r} or grade {grade_code!r} not found",
                file=sys.stderr,
            )
            sys.exit(1)

        category = session.scalar(
            select(Category).where(
                Category.specialization_id == spec.id,
                Category.grade_id == grade.id,
            )
        )
        if category is None:
            print("ERROR: category not found", file=sys.stderr)
            sys.exit(1)

        # Если уже есть текущая — снимаем флаг
        for existing in session.scalars(
            select(CandidateCategory).where(
                CandidateCategory.candidate_profile_id == profile.id,
                CandidateCategory.is_current.is_(True),
            )
        ):
            existing.is_current = False

        session.add(
            CandidateCategory(
                candidate_profile_id=profile.id,
                category_id=category.id,
                status=CategoryStatus.CONFIRMED,
                is_current=True,
                test_score=test_score,
            )
        )
        session.commit()
        print(f"OK: granted {spec_code}/{grade_code} to {email}")


def main() -> None:
    if len(sys.argv) < 4:
        print(
            "Usage: python -m app.scripts.grant_category <email> <spec> <grade> [score]",
            file=sys.stderr,
        )
        sys.exit(2)
    email, spec, grade = sys.argv[1], sys.argv[2], sys.argv[3]
    score = int(sys.argv[4]) if len(sys.argv) > 4 else 85
    grant(email, spec, grade, score)


if __name__ == "__main__":
    main()