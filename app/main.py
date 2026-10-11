from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.router import router as api_router
from app.web.router import router as web_router

app = FastAPI(title="Project API", version="0.1.0")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(api_router)
app.include_router(web_router)

from fastapi import Request, HTTPException
from fastapi.exception_handlers import http_exception_handler
from app.web.templates import templates

@app.exception_handler(HTTPException)
async def page_error(request: Request, exc: HTTPException):
    is_api = request.url.path.startswith('/api/')
    session_error = exc.status_code == 401 or (exc.status_code == 403 and exc.detail == 'Недостаточно прав')
    is_navigation = 'text/html' in request.headers.get('accept', '') or request.headers.get('sec-fetch-mode') == 'navigate'
    if not is_api and session_error and is_navigation and request.headers.get('hx-request') != 'true':
        from fastapi.responses import RedirectResponse
        return RedirectResponse('/auth/session-refresh', status_code=303, headers={'Cache-Control':'no-store'})
    if request.url.path.startswith(('/career', '/design-preview')):
        # An action denial must not look like logout to the session synchronizer.
        from app.db.session import SessionLocal
        from app.modules.auth.dependencies import get_current_user_optional
        with SessionLocal() as session:
            user = get_current_user_optional(request, credentials=None, session=session)
            return templates.TemplateResponse(request=request, name='career/error.html',
                context={'user':user,'error':exc.detail}, status_code=exc.status_code,
                headers={'Cache-Control':'no-store'})
    return await http_exception_handler(request, exc)
