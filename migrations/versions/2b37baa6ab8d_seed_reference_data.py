"""seed reference data: specializations, grades, categories"""
from alembic import op
import sqlalchemy as sa

revision = '2b37baa6ab8d'
down_revision = 'a2c77bf80a3c'
branch_labels = None
depends_on = None


SPECIALIZATIONS = [
    {"code": "backend", "name": "Backend-разработка"},
    {"code": "frontend", "name": "Frontend-разработка"},
]

GRADES = [
    {"code": "intern", "name": "Intern", "order": 1},
    {"code": "junior", "name": "Junior", "order": 2},
    {"code": "middle", "name": "Middle", "order": 3},
    {"code": "senior", "name": "Senior", "order": 4},
]


def upgrade() -> None:
    conn = op.get_bind()

    for spec in SPECIALIZATIONS:
        conn.execute(
            sa.text(
                "INSERT INTO specializations (code, name) "
                "VALUES (:code, :name) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            spec,
        )

    for grade in GRADES:
        conn.execute(
            sa.text(
                'INSERT INTO grades (code, name, "order") '
                "VALUES (:code, :name, :order) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            grade,
        )

    # Декартово произведение: все специализации × все грейды
    conn.execute(
        sa.text(
            "INSERT INTO categories (specialization_id, grade_id) "
            "SELECT s.id, g.id FROM specializations s CROSS JOIN grades g "
            "ON CONFLICT (specialization_id, grade_id) DO NOTHING"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    # Удаляем только то, что создали мы (по коду), чтобы не задеть чужие данные
    conn.execute(sa.text("DELETE FROM categories"))
    conn.execute(
        sa.text(
            "DELETE FROM grades WHERE code IN ('intern', 'junior', 'middle', 'senior')"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM specializations WHERE code IN ('backend', 'frontend')"
        )
    )