from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))

@router.get("/", include_in_schema=False)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")
