"""Загрузчик шаблонов вопросов из JSON-файлов в БД.

Идемпотентно: повторный запуск не создаёт дубликатов, а обновляет
существующие шаблоны по ключу (specialization, grade, topic, text_template).

Ключ уникальности: нельзя заводить два вопроса с одинаковым текстом
в одной категории. Это защита от случайного дублирования при копипасте.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.assessments.models import Grade, Question, QuestionType, Specialization

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).parent / "seed"


class SeedError(Exception):
    """Ошибка загрузки сидов."""


def _normalize_text(payload: dict[str, Any]) -> str:
    """Возвращает канонический текст шаблона для проверки уникальности."""
    return (payload.get("text_template") or payload.get("text") or "").strip()


def load_questions_from_file(session: Session, path: Path) -> tuple[int, int]:
    """Загружает вопросы из одного JSON-файла.

    Возвращает (создано, обновлено).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    spec_code = data["specialization"]
    grade_code = data["grade"]
    questions = data.get("questions") or []

    spec = session.scalar(
        select(Specialization).where(Specialization.code == spec_code)
    )
    if spec is None:
        raise SeedError(f"Специализация {spec_code!r} не найдена")

    grade = session.scalar(select(Grade).where(Grade.code == grade_code))
    if grade is None:
        raise SeedError(f"Грейд {grade_code!r} не найден")

    created = updated = 0
    for item in questions:
        qtype = QuestionType(item["type"])
        payload = item["payload"]
        key_text = _normalize_text(payload)

        existing = session.scalar(
            select(Question).where(
                Question.specialization_id == spec.id,
                Question.grade_id == grade.id,
                Question.topic == item.get("topic"),
                Question.type == qtype,
                # сравниваем по каноническому тексту через JSONB ->> text_template
                Question.payload["text_template"].astext == key_text,
            )
        )

        if existing is not None:
            existing.difficulty = item["difficulty"]
            existing.payload = payload
            existing.correct_answer = item.get("correct_answer")
            existing.is_active = True
            updated += 1
            continue

        session.add(
            Question(
                specialization_id=spec.id,
                grade_id=grade.id,
                topic=item.get("topic"),
                type=qtype,
                payload=payload,
                correct_answer=item.get("correct_answer"),
                difficulty=item["difficulty"],
                is_active=True,
            )
        )
        created += 1

    session.commit()
    return created, updated


def load_all_seeds(session: Session) -> dict[str, tuple[int, int]]:
    """Загружает все файлы из seed/. Возвращает статистику по файлам."""
    if not SEED_DIR.exists():
        raise SeedError(f"Директория {SEED_DIR} не найдена")

    result: dict[str, tuple[int, int]] = {}
    for path in sorted(SEED_DIR.glob("*.json")):
        try:
            created, updated = load_questions_from_file(session, path)
            result[path.name] = (created, updated)
            logger.info("%s: created=%d updated=%d", path.name, created, updated)
        except Exception as exc:
            session.rollback()
            logger.exception("Ошибка загрузки %s: %s", path.name, exc)
            raise
    return result


def main() -> None:
    """CLI-точка входа: python -m app.modules.assessments.seed_loader."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        stats = load_all_seeds(session)
    total_created = sum(c for c, _ in stats.values())
    total_updated = sum(u for _, u in stats.values())
    print(f"Files: {len(stats)} | created: {total_created} | updated: {total_updated}")
    for name, (c, u) in stats.items():
        print(f"  {name}: +{c} / ~{u}")


if __name__ == "__main__":
    main()