"""Persistent mock data, shared by read API and protected operator edits."""
import json
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

@contextmanager
def database():
    target = Path(os.getenv('MOCK_STORAGE_PATH', str(Path(__file__).parent / '.runtime' / 'registry.sqlite')))
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as db:
        db.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, data TEXT, PRIMARY KEY(kind,id))')
        db.execute('CREATE TABLE IF NOT EXISTS initialized (id INTEGER PRIMARY KEY)')
        if db.execute('SELECT id FROM initialized').fetchone() is None:
            for kind in ('participants', 'achievements'):
                for row in json.loads((Path(__file__).parent/'data'/f'{kind}.json').read_text(encoding='utf-8')):
                    db.execute('INSERT INTO records VALUES (?,?,?)', (kind,row['id'],json.dumps(row,ensure_ascii=False)))
            db.execute('INSERT INTO initialized VALUES (1)')
        yield db

def rows(kind):
    with database() as db:
        return [json.loads(r[0]) for r in db.execute('SELECT data FROM records WHERE kind=? ORDER BY id',(kind,))]

def save(kind, row):
    with database() as db:
        db.execute('INSERT INTO records VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data',
                   (kind,row['id'],json.dumps(row,ensure_ascii=False)))
