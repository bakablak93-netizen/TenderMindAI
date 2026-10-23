"""Simple local single-user SQLite project store.

No API keys are ever persisted. Intended for a local MVP; deploy with
user authentication, per-tenant access control and a managed DB for production.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / 'data' / 'projects.sqlite3'


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute('''CREATE TABLE IF NOT EXISTS projects (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Другое',
      status TEXT NOT NULL DEFAULT 'В анализе', mode TEXT NOT NULL DEFAULT 'Демо',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      tender_json TEXT NOT NULL, offers_json TEXT NOT NULL,
      hits_json TEXT NOT NULL, optimization_json TEXT NOT NULL,
      cash_json TEXT NOT NULL
    )''')
    return conn


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def save_project(p):
    now = utcnow()
    p = dict(p)
    p.setdefault('created_at', now)
    p['updated_at'] = now
    with db() as conn:
        conn.execute('''INSERT INTO projects (id,name,category,status,mode,created_at,updated_at,
             tender_json,offers_json,hits_json,optimization_json,cash_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET name=excluded.name, category=excluded.category,
             status=excluded.status, mode=excluded.mode, updated_at=excluded.updated_at,
             tender_json=excluded.tender_json, offers_json=excluded.offers_json,
             hits_json=excluded.hits_json, optimization_json=excluded.optimization_json,
             cash_json=excluded.cash_json''',
           (p['id'], p['name'], p.get('category','Другое'), p.get('status','В анализе'),
            p.get('mode','Демо'), p['created_at'], p['updated_at'],
            json.dumps(p.get('tender') or {}, ensure_ascii=False),
            json.dumps(p.get('offers') or {}, ensure_ascii=False),
            json.dumps(p.get('hits') or {}, ensure_ascii=False),
            json.dumps(p.get('optimization') or {}, ensure_ascii=False),
            json.dumps(p.get('cash'), ensure_ascii=False)))
    return p


def get_projects():
    with db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT * FROM projects ORDER BY updated_at DESC').fetchall()
    result=[]
    for r in rows:
        obj=dict(r)
        for k in ('tender','offers','hits','optimization','cash'):
            obj[k] = json.loads(obj.pop(k+'_json'))
        result.append(obj)
    return result


def get_project(project_id):
    return next((p for p in get_projects() if p['id'] == project_id), None)


def delete_project(project_id):
    with db() as conn:
        conn.execute('DELETE FROM projects WHERE id = ?', (project_id,))


def seed_demo_projects(force=False):
    """Insert bundled examples by stable IDs, without editing existing user projects.

    A one-time marker prevents re-seeding after users delete the examples.
    force=True inserts missing examples when the user explicitly requests a reset.
    """
    from .demo_data import demo_projects
    examples=demo_projects()
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        already=conn.execute("SELECT value FROM app_meta WHERE key='demo_seed_v1'").fetchone()
        if already and not force:
            return 0
        existing={r[0] for r in conn.execute('SELECT id FROM projects').fetchall()}
        count=0
        for example in examples:
            if example['id'] not in existing:
                save_project(example)
                count+=1
        conn.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES ('demo_seed_v1','done')")
        return count
