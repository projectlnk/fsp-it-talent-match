"""Read-only visual prototypes. Synthetic data never enters application services or DB."""
from fastapi import APIRouter, HTTPException, Request
from app.web.templates import templates

router = APIRouter(prefix="/design-preview", include_in_schema=False)
CANDIDATES = (
    {"id": "1", "name": "Алексей Морозов", "initials": "АМ", "role": "Backend-разработчик", "specialization": "backend", "grade": "Middle", "location": "Москва", "format": "remote", "years": 4, "score": 87, "salary": "180 000–240 000 ₽", "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"], "fsp": True, "about": "Разрабатываю API и сервисы обработки данных. Люблю понятные контракты, надёжные системы и команды, в которых можно обсуждать решения."},
    {"id": "2", "name": "Анна Соколова", "initials": "АС", "role": "Backend-разработчик", "specialization": "backend", "grade": "Middle", "location": "Санкт-Петербург", "format": "remote", "years": 3, "score": 82, "salary": "170 000–220 000 ₽", "skills": ["Python", "Django", "PostgreSQL", "REST API"], "fsp": False, "about": "Создаю backend для B2B-сервисов. Работаю с интеграциями, тестами и оптимизацией запросов. Ищу команду для совместной работы над продуктом."},
    {"id": "3", "name": "Дмитрий Волков", "initials": "ДВ", "role": "Frontend-разработчик", "specialization": "frontend", "grade": "Junior", "location": "Казань", "format": "hybrid", "years": 2, "score": 79, "salary": "100 000–140 000 ₽", "skills": ["JavaScript", "TypeScript", "HTML", "CSS"], "fsp": False, "about": "Разрабатываю понятные интерфейсы. Интересуюсь доступностью и производительностью приложений."},
)
SCREENS = {"": "index", "candidate": "candidate", "employer": "employer", "search": "search", "invitation": "invitation", "fsp": "fsp", "resume": "resume", "privacy": "privacy"}

@router.get("")
@router.get("/")
def overview(request: Request):
    return render(request, "index")

@router.get("/person/{person_id}")
def person(request: Request, person_id: str):
    candidate = next((c for c in CANDIDATES if c["id"] == person_id), None)
    if candidate is None:
        raise HTTPException(404, "Демонстрационный профиль не найден")
    return render(request, "person", candidate=candidate)

@router.get("/{screen}")
def screen(request: Request, screen: str, candidate: str = "1"):
    if screen not in SCREENS or not screen:
        raise HTTPException(404, "Экран прототипа не найден")
    selected = next((c for c in CANDIDATES if c["id"] == candidate), None)
    if selected is None:
        raise HTTPException(404, "Демонстрационный профиль не найден")
    return render(request, SCREENS[screen], candidate=selected)

def render(request: Request, screen: str, **context):
    return templates.TemplateResponse(request=request, name=f"design_preview/{screen}.html", context={"user": None, "preview_mode": True, "candidates": CANDIDATES, "candidate": CANDIDATES[0], **context})
