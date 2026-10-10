"""Общий экземпляр Jinja2Templates для всех веб-роутеров."""
from pathlib import Path

from fastapi.templating import Jinja2Templates
from app.modules.assessments.grades import GRADE_LABELS

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
templates.env.globals['grade_labels'] = GRADE_LABELS
