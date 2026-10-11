"""Общий экземпляр Jinja2Templates для всех веб-роутеров."""
from pathlib import Path

from fastapi.templating import Jinja2Templates
from app.modules.assessments.grades import GRADE_LABELS

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
templates.env.globals['grade_labels'] = GRADE_LABELS
templates.env.globals.update(
    opportunity_status_labels={'new':'Новая','stable':'Стабильная','inactive':'Неактивная','deleted':'Удалена в архив','draft':'Черновик'},
    meeting_status_labels={'scheduled':'Назначена','confirmed':'Собеседование подтверждено','disputed':'Встреча оспорена','hired':'Найм подтверждён','cancelled':'Отменена'},
    application_status_labels={'submitted':'Ожидает рассмотрения','accepted':'Кандидат выбран','rejected':'Отказ','revoked':'Отозвано'},
    offer_status_labels={'sent':'Ожидает ответа','viewed':'Просмотрено, ожидает ответа','accepted':'Принято','rejected':'Отказ','revoked':'Отозвано'},
    work_format_labels={'office':'Офис','remote':'Удалённо','hybrid':'Гибрид'},
)
