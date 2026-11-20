"""Durable run ledger; Vercel uses Postgres and private Blob storage."""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

IS_VERCEL = os.getenv('VERCEL') == '1'
BASE = Path(__file__).resolve().parent.parent
ROOT = Path('/tmp/eucerin') if IS_VERCEL else Path(os.getenv('STORAGE_DIR', str(BASE / 'storage')))
ROOT.mkdir(exist_ok=True, parents=True)
DB = ROOT / 'runs.sqlite3'
LOCK = threading.RLock()


class _PostgresConnection:
    """Small SQL placeholder adapter shared with the SQLite implementation."""

    def __init__(self, connection):
        self._connection = connection

    def execute(self, statement, parameters=()):
        return self._connection.execute(statement.replace('?', '%s'), parameters)


@contextmanager
def connection():
    if IS_VERCEL:
        import psycopg
        from psycopg.rows import dict_row

        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise RuntimeError('DATABASE_URL is required on Vercel; connect a Postgres database.')
        with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5) as db:
            yield _PostgresConnection(db)
        return

    db = sqlite3.connect(DB, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout=30000')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init():
    with LOCK, connection() as db:
        if IS_VERCEL:
            if not os.getenv('BLOB_STORE_ID') and not os.getenv('BLOB_READ_WRITE_TOKEN'):
                raise RuntimeError('Connect a private Vercel Blob store before starting the API.')
            db.execute('''CREATE TABLE IF NOT EXISTS runs(
                run_id TEXT PRIMARY KEY, source_sha TEXT NOT NULL, model_version TEXT NOT NULL,
                source_id TEXT NOT NULL, source_revision TEXT NOT NULL, status TEXT NOT NULL,
                as_of_date TEXT NOT NULL, summary_json TEXT NOT NULL,
                telegram_message_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(source_sha,model_version))''')
            db.execute('''CREATE TABLE IF NOT EXISTS uploads(
                run_id TEXT NOT NULL, file_name TEXT NOT NULL, drive_file_id TEXT NOT NULL,
                uploaded_at TEXT NOT NULL, PRIMARY KEY(run_id,file_name),
                FOREIGN KEY(run_id) REFERENCES runs(run_id))''')
        else:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs(
            run_id TEXT PRIMARY KEY, source_sha TEXT NOT NULL, model_version TEXT NOT NULL,
            source_id TEXT NOT NULL, source_revision TEXT NOT NULL, status TEXT NOT NULL,
            as_of_date TEXT NOT NULL, summary_json TEXT NOT NULL,
            telegram_message_id TEXT, created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
            UNIQUE(source_sha,model_version));
            CREATE TABLE IF NOT EXISTS uploads(
            run_id TEXT NOT NULL, file_name TEXT NOT NULL, drive_file_id TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,PRIMARY KEY(run_id,file_name),
            FOREIGN KEY(run_id) REFERENCES runs(run_id));
            ''')


def now():
    return datetime.now(timezone.utc).isoformat()


def get_run(run_id):
    with connection() as db:
        row = db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
        return dict(row) if row else None


def get_by_hash(source_sha, model_version):
    with connection() as db:
        row = db.execute('SELECT * FROM runs WHERE source_sha=? AND model_version=?',
                         (source_sha, model_version)).fetchone()
        return dict(row) if row else None


def same_source_delivered(source_id, source_revision, model_version):
    with connection() as db:
        return db.execute('''SELECT run_id FROM runs
            WHERE source_id=? AND source_revision=? AND model_version=? AND status=?
            ORDER BY updated_at DESC LIMIT 1''',
            (source_id, source_revision, model_version, 'delivered')).fetchone()


def create_run(run_id, sha, version, source_id, revision, asof, summary):
    timestamp = now()
    with LOCK, connection() as db:
        db.execute('''INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source_sha,model_version) DO NOTHING''',
            (run_id, sha, version, source_id, revision, 'prepared', asof,
             json.dumps(summary, ensure_ascii=False), None, timestamp, timestamp))


def save_upload(run_id, file_name, drive_file_id):
    with LOCK, connection() as db:
        row = db.execute('SELECT status FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if not row or row['status'] not in ('prepared', 'uploaded'):
            raise ValueError('Cannot upload to unknown/closed run')
        previous = db.execute('SELECT drive_file_id FROM uploads WHERE run_id=? AND file_name=?',
                              (run_id, file_name)).fetchone()
        if previous and previous['drive_file_id'] != drive_file_id:
            raise ValueError('Artifact already uploaded to different Drive file ID (manual reconciliation required)')
        db.execute('''INSERT INTO uploads VALUES (?,?,?,?)
            ON CONFLICT(run_id,file_name) DO NOTHING''',
            (run_id, file_name, drive_file_id, now()))
        db.execute('UPDATE runs SET updated_at=? WHERE run_id=?', (now(), run_id))


def uploads(run_id):
    with connection() as db:
        return {row['file_name']: row['drive_file_id'] for row in
                db.execute('SELECT file_name,drive_file_id FROM uploads WHERE run_id=?', (run_id,))}


def reserve_send(run_id, required):
    with LOCK, connection() as db:
        row = db.execute('SELECT status FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if not row:
            raise ValueError('Run not found')
        missing = set(required) - set(uploads(run_id))
        if missing:
            raise ValueError('Cannot send Telegram before all uploads: ' + ', '.join(sorted(missing)))
        # The conditional update makes the notification reservation safe across Vercel instances.
        result = db.execute('''UPDATE runs SET status=?,updated_at=?
            WHERE run_id=? AND status=?''', ('notification_reserved', now(), run_id, 'prepared'))
        return result.rowcount == 1


def delivered(run_id, telegram_message_id):
    with LOCK, connection() as db:
        row = db.execute('SELECT status FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if not row or row['status'] != 'notification_reserved':
            raise ValueError('No reserved notification')
        db.execute('UPDATE runs SET status=?,telegram_message_id=?,updated_at=? WHERE run_id=?',
                   ('delivered', telegram_message_id, now(), run_id))


def history():
    with connection() as db:
        return [dict(row) for row in db.execute('''SELECT run_id,source_sha,model_version,
            source_id,source_revision,status,as_of_date,telegram_message_id,created_at,updated_at
            FROM runs ORDER BY created_at DESC''')]


def store_artifacts(run_id, directory, file_names):
    """Persist generated CSVs in a private Blob store when running on Vercel."""
    if not IS_VERCEL:
        return
    from vercel.blob import sync as blob

    for file_name in file_names:
        path = Path(directory) / file_name
        with path.open('rb') as source:
            blob.put_blob(f'runs/{run_id}/{file_name}', source, access='private',
                          content_type='text/csv', content_length=path.stat().st_size,
                          allow_overwrite=True, cache_control_max_age=0)


def artifact_pathname(run_id, file_name):
    return f'runs/{run_id}/{file_name}'
