from fastapi import APIRouter

from app.api.health import router as health_router
from app.modules.assessments.router import router as assessments_router
from app.modules.auth.router import router as auth_router
from app.modules.candidates.router import router as candidates_router
from app.modules.employers.router import router as employers_router
from app.modules.matching.router import router as matching_router
from app.modules.candidates.offers_router import router as candidate_offers_router
from app.modules.employers.offers_router import router as employer_offers_router

router = APIRouter()

router.include_router(health_router)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth_router)
api_v1.include_router(candidates_router)
api_v1.include_router(employers_router)
api_v1.include_router(assessments_router)
router.include_router(api_v1)
api_v1.include_router(matching_router)
api_v1.include_router(candidates_router)
api_v1.include_router(candidate_offers_router)
api_v1.include_router(employers_router)
api_v1.include_router(employer_offers_router)