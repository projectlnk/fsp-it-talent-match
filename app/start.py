import subprocess
import time
import uvicorn
from sqlalchemy import text, select
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import get_settings
from app.db.session import engine, SessionLocal
from app.modules.assessments.models import Question
from app.modules.assessments.seed_loader import load_all_seeds

def main():
    print("Waiting for PostgreSQL", flush=True)
    for attempt in range(30):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            break
        except SQLAlchemyError:
            if attempt == 29:
                raise
            time.sleep(2)
    print("PostgreSQL is ready; applying Alembic migrations", flush=True)
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    # Bootstrap only an empty question bank; never overwrite edited questions on restart.
    with SessionLocal() as session:
        if session.scalar(select(Question.id).limit(1)) is None:
            load_all_seeds(session)
    print("Alembic migrations applied; starting Uvicorn", flush=True)
    from app.scripts.process_events import start_worker
    start_worker()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=get_settings().reload)

if __name__ == "__main__":
    main()
