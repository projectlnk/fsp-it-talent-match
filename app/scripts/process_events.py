"""Same idempotent processor used by the web pages and demo time controls."""
import logging
import threading
from app.db.session import SessionLocal
from app.modules.career.service import process_due

def run_once():
    with SessionLocal() as session:
        changes = process_due(session)
        session.commit()
        return changes

def start_worker():
    def work():
        stop = threading.Event()
        while not stop.wait(60):
            try:
                run_once()
            except Exception as exc:
                logging.getLogger(__name__).error('Business processing failed: %s', type(exc).__name__)
    threading.Thread(target=work, name='business-processing', daemon=True).start()

if __name__ == '__main__':
    print(run_once())
