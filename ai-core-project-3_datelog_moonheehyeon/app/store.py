"""SQLite 저장소. 라우터는 SQL 대신 저장 함수를 사용한다."""
import json
import os
import sqlite3
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / 'data' / 'planner.db'

@contextmanager
def connect():
    path = Path(os.getenv('PLANNER_DB_PATH', str(DEFAULT_DB)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=15)) as db, db:
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE IF NOT EXISTS plans (plan_id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS itineraries (itinerary_id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, summary TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS events_session ON events(session_id, event_id);
        """)
        yield db

def now():
    return datetime.now(timezone.utc).isoformat()

def _plan(row):
    return {**json.loads(row['payload']), 'plan_id': row['plan_id'], 'created_at': row['created_at']}

def _warnings(db, item):
    from .itineraries import intervals, overlaps as interval_overlaps, decode
    overlaps = []
    itinerary_overlaps = []
    if item.get('start_time') and item.get('end_time'):
        for row in db.execute('SELECT * FROM plans WHERE plan_id != ?', (item['plan_id'],)):
            other = _plan(row)
            if other['watch_date'] == item['watch_date'] and other.get('start_time') and other.get('end_time') and item['start_time'] < other['end_time'] and other['start_time'] < item['end_time']:
                overlaps.append(other['plan_id'])
    warnings = [f'같은 날짜에 시간이 겹치는 계획이 있습니다: {overlaps}'] if overlaps else []
    own = intervals(item, legacy=True)
    for row in db.execute('SELECT * FROM itineraries ORDER BY itinerary_id'):
        other = decode(row)
        if any(interval_overlaps(a,b) for a in own for b in intervals(other)):
            itinerary_overlaps.append(other['itinerary_id'])
    if itinerary_overlaps:
        warnings.append(f'시간이 겹치는 데이트 약속이 있습니다: {itinerary_overlaps}. 저장은 유지됩니다.')
    if not item.get('start_time') or not item.get('end_time'):
        warnings.append('시작·종료 시각이 모두 있어야 시간 겹침을 확인할 수 있습니다.')
    return {**item, 'overlap_plan_ids': overlaps, 'overlap_itinerary_ids': itinerary_overlaps, 'warnings': warnings}

def save_plan(plan, plan_id=None):
    payload = json.dumps(plan.model_dump(mode='json'), ensure_ascii=False)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if plan_id is None:
            plan_id = db.execute('INSERT INTO plans(payload, created_at) VALUES (?, ?)', (payload, now())).lastrowid
        elif db.execute('UPDATE plans SET payload=? WHERE plan_id=?', (payload, plan_id)).rowcount == 0:
            return None
        return _warnings(db, _plan(db.execute('SELECT * FROM plans WHERE plan_id=?', (plan_id,)).fetchone()))

def list_plans():
    with connect() as db:
        return [_warnings(db, _plan(row)) for row in db.execute('SELECT * FROM plans ORDER BY plan_id')]

def get_plan(plan_id):
    with connect() as db:
        row = db.execute('SELECT * FROM plans WHERE plan_id=?', (plan_id,)).fetchone()
        return _warnings(db, _plan(row)) if row else None

def delete_plan(plan_id):
    with connect() as db:
        return db.execute('DELETE FROM plans WHERE plan_id=?', (plan_id,)).rowcount > 0

def get_memory(session_id):
    with connect() as db:
        row = db.execute('SELECT summary FROM sessions WHERE session_id=?', (session_id,)).fetchone()
        return json.loads(row['summary']) if row else {}

def save_memory(session_id, summary):
    with connect() as db:
        db.execute('INSERT INTO sessions VALUES (?, ?) ON CONFLICT(session_id) DO UPDATE SET summary=excluded.summary', (session_id, json.dumps(summary, ensure_ascii=False)))

def append_event(event):
    with connect() as db:
        db.execute('INSERT INTO events(session_id,payload,created_at) VALUES (?,?,?)', (event['session_id'], json.dumps(event, ensure_ascii=False), event['timestamp']))

def list_logs():
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT session_id,COUNT(*) AS event_count,MAX(created_at) AS updated_at FROM events GROUP BY session_id ORDER BY updated_at DESC')]

def get_logs(session_id):
    with connect() as db:
        return [json.loads(row['payload']) for row in db.execute('SELECT payload FROM events WHERE session_id=? ORDER BY event_id', (session_id,))]

def delete_logs(session_id):
    with connect() as db:
        return db.execute('DELETE FROM events WHERE session_id=?', (session_id,)).rowcount > 0

