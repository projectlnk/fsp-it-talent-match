from fastapi import APIRouter, Depends, Request

from app.modules.auth.dependencies import get_current_user_optional
from app.modules.auth.models import User
from app.modules.auth.web import router as auth_web_router
from app.web.templates import templates

router = APIRouter()
router.include_router(auth_web_router)


@router.get("/", include_in_schema=False)
def index(request: Request, user: User | None = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"user": user},
    )