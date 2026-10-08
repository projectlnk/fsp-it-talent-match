"""Общий экземпляр Jinja2Templates для всех веб-роутеров."""
from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))