from fastapi import APIRouter

from app.api.health import router as health_router
from app.modules.auth.router import router as auth_router

router = APIRouter()

# Служебные эндпоинты (health, readiness) остаются на корне.
router.include_router(health_router)

# Предметные модули живут под версионированным префиксом.
api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth_router)
router.include_router(api_v1)