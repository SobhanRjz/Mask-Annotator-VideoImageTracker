from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import threading

from app.core.db import db, get_setting, set_setting
from app.core.settings import settings


CURSOR_KEY = 'daily_backup_cursor'


def backup_day(now=None):
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).date().isoformat()


def parse_cursor(raw):
    if not raw:
        return '', 0
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return '', 0
    updated = str(data.get('updated_at') or '')
    try:
        annotation_id = int(data.get('id') or 0)
    except (TypeError, ValueError):
        annotation_id = 0
    return updated, annotation_id


def encode_cursor(updated_at, annotation_id):
    return json.dumps({'updated_at': updated_at, 'id': int(annotation_id)})


class DailyBackupService:
    def pending(self, updated_at='', annotation_id=0):
        clause = ''
        args = []
        if updated_at:
            clause = 'WHERE a.updated_at > ? OR (a.updated_at = ? AND a.id > ?)'
            args = [updated_at, updated_at, int(annotation_id)]
        sql = f'''
            SELECT a.id, a.media_id, a.frame, a.label_id, a.source, a.track_group,
                   a.mask_path, a.created_at, a.updated_at,
                   l.name label_name, l.color label_color,
                   m.name media_name, m.project_id,
                   p.name project_name, p.slug project_slug
            FROM annotations a
            JOIN labels l ON l.id = a.label_id
            JOIN media m ON m.id = a.media_id
            JOIN projects p ON p.id = m.project_id
            {clause}
            ORDER BY a.updated_at, a.id
        '''
        with db() as conn:
            return [dict(row) for row in conn.execute(sql, args)]

    def _load_manifest(self, folder: Path, day: str):
        path = folder / 'manifest.json'
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data, dict) and isinstance(data.get('items'), list):
                    return data
            except json.JSONDecodeError:
                pass
        return {'date': day, 'items': []}

    def _write_item(self, folder: Path, row: dict):
        masks = folder / 'masks'
        masks.mkdir(parents=True, exist_ok=True)
        rel = f"masks/{row['id']}.png"
        source = Path(row['mask_path'])
        if source.is_file():
            shutil.copy2(source, folder / rel)
        return {
            'id': row['id'],
            'project_id': row['project_id'],
            'project_name': row['project_name'],
            'project_slug': row.get('project_slug'),
            'media_id': row['media_id'],
            'media_name': row['media_name'],
            'frame': row['frame'],
            'label_id': row['label_id'],
            'label_name': row['label_name'],
            'label_color': row['label_color'],
            'source': row['source'],
            'track_group': row.get('track_group'),
            'created_at': row.get('created_at'),
            'updated_at': row.get('updated_at'),
            'mask': rel,
        }

    def tick(self, now=None):
        updated_at, annotation_id = parse_cursor(get_setting(CURSOR_KEY))
        rows = self.pending(updated_at, annotation_id)
        if not rows:
            return {'saved': 0, 'skipped': True, 'day': backup_day(now)}
        day = backup_day(now)
        folder = settings.backup_root / day
        folder.mkdir(parents=True, exist_ok=True)
        manifest = self._load_manifest(folder, day)
        by_id = {item['id']: index for index, item in enumerate(manifest['items'])}
        for row in rows:
            item = self._write_item(folder, row)
            index = by_id.get(item['id'])
            if index is None:
                by_id[item['id']] = len(manifest['items'])
                manifest['items'].append(item)
            else:
                manifest['items'][index] = item
        manifest['date'] = day
        manifest['updated_at'] = rows[-1]['updated_at']
        (folder / 'manifest.json').write_text(
            json.dumps(manifest, indent=2),
            encoding='utf-8',
        )
        set_setting(CURSOR_KEY, encode_cursor(rows[-1]['updated_at'], rows[-1]['id']))
        return {
            'saved': len(rows),
            'skipped': False,
            'day': day,
            'path': str(folder),
        }


daily_backup_service = DailyBackupService()


class DailyBackupScheduler:
    def __init__(self, interval_seconds=1800):
        self.interval_seconds = max(60, int(interval_seconds))
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        self.thread = threading.Thread(target=self._loop, name='daily-backup', daemon=True)
        self.thread.start()

    def shutdown(self):
        self.stop.set()

    def _loop(self):
        while not self.stop.is_set():
            try:
                daily_backup_service.tick()
            except Exception as exc:
                print(f'Daily annotation backup failed: {exc}', flush=True)
            if self.stop.wait(self.interval_seconds):
                break


daily_backup_scheduler = DailyBackupScheduler()
