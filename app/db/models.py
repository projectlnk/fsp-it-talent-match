"""Агрегатор моделей всех модулей для Alembic.

Импортирует модели модулей, чтобы они попали в Base.metadata.
"""
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.candidates import models as candidates_models  # noqa: F401
from app.modules.employers import models as employers_models  # noqa: F401
from app.modules.assessments import models as assessments_models  # noqa: F401
from app.modules.career import models as career_models  # noqa: F401
