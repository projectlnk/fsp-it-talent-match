from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.modules.assessments.web import router as assessments_web_router
from app.modules.auth.dependencies import get_current_user_optional, workspace_home
from app.modules.auth.models import User, UserRole
from app.modules.auth.web import router as auth_web_router
from app.modules.candidates.web import router as candidates_web_router
from app.modules.employers.web import router as employers_web_router
from app.web.templates import templates
from app.modules.candidates.offers_web import router as candidates_offers_web_router
from app.modules.career.demo import router as design_preview_router
from app.modules.matching.web import router as matching_web_router


router = APIRouter()
from app.modules.career.web import router as career_router
router.include_router(career_router)
router.include_router(design_preview_router)
router.include_router(auth_web_router)
router.include_router(candidates_web_router)
router.include_router(employers_web_router)
router.include_router(assessments_web_router)
router.include_router(matching_web_router)
router.include_router(candidates_offers_web_router)


@router.get("/", include_in_schema=False)
def index(request: Request, user: User | None = Depends(get_current_user_optional)):
    if user is not None and workspace_home(user) != "/" and request.query_params.get("public") != "1":
        return RedirectResponse(workspace_home(user), status_code=303, headers={"Cache-Control": "no-store"})
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"user": user, "public_page": True},
        headers={"Cache-Control": "no-store"},
    )
