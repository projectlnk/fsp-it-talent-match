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
    if request.url.path.startswith(('/career', '/design-preview')):
        return templates.TemplateResponse(request=request, name='career/error.html',
            context={'user':None,'error':exc.detail}, status_code=exc.status_code,
            headers={'Cache-Control':'no-store'})
    return await http_exception_handler(request, exc)
