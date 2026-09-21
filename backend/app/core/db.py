import sqlite3
from contextlib import contextmanager
from app.core.settings import settings
SCHEMA = r'''
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,slug TEXT,description TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS labels (id INTEGER PRIMARY KEY AUTOINCREMENT,project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,name TEXT NOT NULL,color TEXT NOT NULL DEFAULT '#5B8FF9',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(project_id,name));
CREATE TABLE IF NOT EXISTS media (id INTEGER PRIMARY KEY AUTOINCREMENT,project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,name TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('video','image')),path TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,frame_count INTEGER NOT NULL,fps REAL NOT NULL DEFAULT 1.0,source_fps REAL,source_frame_count INTEGER,extract_fps REAL,frames_dir TEXT,extract_status TEXT NOT NULL DEFAULT 'ready',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS annotations (id INTEGER PRIMARY KEY AUTOINCREMENT,media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,frame INTEGER NOT NULL,label_id INTEGER NOT NULL REFERENCES labels(id) ON DELETE RESTRICT,mask_path TEXT NOT NULL,source TEXT NOT NULL DEFAULT 'manual',track_group TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_ann_media_frame ON annotations(media_id,frame);
CREATE TABLE IF NOT EXISTS excluded_frames (media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,frame INTEGER NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(media_id,frame));
CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
'''
MEDIA_COLUMNS = (
    ('source_fps', 'REAL'),
    ('source_frame_count', 'INTEGER'),
    ('extract_fps', 'REAL'),
    ('frames_dir', 'TEXT'),
    ('extract_status', "TEXT NOT NULL DEFAULT 'ready'"),
    ('annotation_seconds', 'INTEGER NOT NULL DEFAULT 0'),
    ('annotation_complete', 'INTEGER NOT NULL DEFAULT 0'),
    ('content_hash', 'TEXT'),
)


def _migrate(conn: sqlite3.Connection):
    cols = {row[1] for row in conn.execute('PRAGMA table_info(media)')}
    for name, definition in MEDIA_COLUMNS:
        if name not in cols:
            conn.execute(f'ALTER TABLE media ADD COLUMN {name} {definition}')
    conn.execute(
        '''UPDATE media
           SET source_fps = COALESCE(source_fps, fps),
               source_frame_count = COALESCE(source_frame_count, frame_count)
           WHERE source_fps IS NULL OR source_frame_count IS NULL'''
    )
    conn.execute(
        '''UPDATE media
           SET extract_status = 'pending'
           WHERE kind = 'video'
             AND (frames_dir IS NULL OR frames_dir = '')
             AND extract_status = 'ready'
             AND id NOT IN (SELECT DISTINCT media_id FROM annotations)'''
    )
    conn.execute(
        '''CREATE UNIQUE INDEX IF NOT EXISTS idx_media_project_hash
           ON media(project_id, content_hash)
           WHERE content_hash IS NOT NULL AND content_hash != \'\''''
    )
    _migrate_project_slugs(conn)


def _migrate_project_slugs(conn: sqlite3.Connection):
    from app.utils.slugs import allocate_slug, slugify

    cols = {row[1] for row in conn.execute('PRAGMA table_info(projects)')}
    if 'slug' not in cols:
        conn.execute('ALTER TABLE projects ADD COLUMN slug TEXT')
    seen_names = {}
    for row in conn.execute('SELECT id, name FROM projects ORDER BY id'):
        key = (row['name'] or '').casefold()
        if key not in seen_names:
            seen_names[key] = row['id']
            continue
        index = 2
        while True:
            candidate = f"{row['name']} {index}"
            next_key = candidate.casefold()
            if next_key not in seen_names:
                conn.execute('UPDATE projects SET name=? WHERE id=?', (candidate, row['id']))
                seen_names[next_key] = row['id']
                break
            index += 1
    used = set()
    for row in conn.execute('SELECT id, name, slug FROM projects ORDER BY id'):
        slug = row['slug'] if row['slug'] else allocate_slug(used, row['name'] or slugify(str(row['id'])))
        used.add(slug)
        if slug != row['slug']:
            conn.execute('UPDATE projects SET slug=? WHERE id=?', (slug, row['id']))
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_slug ON projects(slug)')
    conn.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_name_nocase ON projects(name COLLATE NOCASE)'
    )


def initialize_db():
    for p in (settings.data_root, settings.media_root, settings.mask_root, settings.export_root):
        p.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    try:
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
@contextmanager
def db():
    conn=sqlite3.connect(settings.db_path,timeout=30); conn.row_factory=sqlite3.Row; conn.execute('PRAGMA foreign_keys=ON')
    try: yield conn; conn.commit()
    finally: conn.close()


def get_setting(key: str, default: str | None = None):
    with db() as conn:
        row = conn.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
        return row['value'] if row else default


def set_setting(key: str, value: str):
    with db() as conn:
        conn.execute(
            'INSERT INTO app_settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
            (key, value),
        )
