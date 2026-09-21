from pathlib import Path
import io
import shutil
import sqlite3
import uuid

from PIL import Image

from app.core.db import db
from app.core.settings import settings
from app.utils.extract import clamp_extract_fps, duration_seconds
from app.utils.files import sha256_copy, sha256_file
from app.utils.video import extract_jpegs, is_nearly_black, probe, read_frame

VIDEO_EXT = {'.mp4', '.avi', '.mov', '.mkv', '.m4v', '.webm', '.wmv', '.mpg', '.mpeg'}
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}


def enrich(row) -> dict:
    media = dict(row)
    source_fps = float(media.get('source_fps') or media.get('fps') or 1.0)
    source_count = int(media.get('source_frame_count') or media.get('frame_count') or 0)
    media['source_fps'] = source_fps
    media['source_frame_count'] = source_count
    media['duration_sec'] = duration_seconds(source_count, source_fps)
    media['extract_fps'] = media.get('extract_fps')
    media['extract_status'] = media.get('extract_status') or 'ready'
    media['frames_dir'] = media.get('frames_dir')
    media['annotation_seconds'] = int(media.get('annotation_seconds') or 0)
    media['annotation_complete'] = bool(int(media.get('annotation_complete') or 0))
    return media


class MediaService:
    def upload(self, project_id, files):
        out = []
        folder = settings.media_root / str(project_id)
        folder.mkdir(parents=True, exist_ok=True)
        self._backfill_hashes(project_id)
        seen = {}
        for uploaded in files:
            ext = Path(uploaded.filename or '').suffix.lower()
            if ext not in VIDEO_EXT | IMAGE_EXT:
                continue
            dest = folder / f'{uuid.uuid4().hex}{ext}'
            digest = sha256_copy(uploaded.file, dest)
            existing = self._find_by_hash(project_id, digest) or seen.get(digest)
            if existing:
                dest.unlink(missing_ok=True)
                reused = dict(existing)
                reused['reused'] = True
                out.append(reused)
                continue
            if ext in IMAGE_EXT:
                with Image.open(dest) as image:
                    width, height = image.size
                kind = 'image'
                count = 1
                fps = 1.0
                status = 'ready'
            else:
                info = probe(str(dest))
                width, height = info['width'], info['height']
                count = info['frame_count']
                fps = info['fps'] or 25.0
                kind = 'video'
                status = 'pending'
            with db() as conn:
                cur = conn.execute(
                    '''INSERT INTO media(
                        project_id, name, kind, path, width, height, frame_count, fps,
                        source_fps, source_frame_count, extract_status, content_hash
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        project_id,
                        uploaded.filename,
                        kind,
                        str(dest),
                        width,
                        height,
                        count if kind == 'image' else 0,
                        fps,
                        fps,
                        count,
                        status,
                        digest,
                    ),
                )
                item = self._load(cur.lastrowid, conn)
            item['reused'] = False
            seen[digest] = item
            out.append(item)
        return out

    def get(self, mid):
        with db() as conn:
            return self._load(mid, conn)

    def add_annotation_seconds(self, mid, seconds):
        added = max(0, min(int(seconds or 0), 30))
        with db() as conn:
            row = conn.execute('SELECT id, project_id FROM media WHERE id=?', (mid,)).fetchone()
            if not row:
                raise KeyError('Media not found')
            conn.execute(
                'UPDATE media SET annotation_seconds = COALESCE(annotation_seconds, 0) + ? WHERE id=?',
                (added, mid),
            )
            media_seconds = conn.execute(
                'SELECT annotation_seconds FROM media WHERE id=?',
                (mid,),
            ).fetchone()['annotation_seconds']
            project_seconds = conn.execute(
                'SELECT COALESCE(SUM(annotation_seconds), 0) s FROM media WHERE project_id=?',
                (row['project_id'],),
            ).fetchone()['s']
        return {
            'annotation_seconds': int(media_seconds or 0),
            'project_annotation_seconds': int(project_seconds or 0),
        }

    def _load(self, mid, conn):
        row = conn.execute('SELECT * FROM media WHERE id=?', (mid,)).fetchone()
        if not row:
            raise KeyError('Media not found')
        item = enrich(row)
        item['annotation_count'] = conn.execute(
            'SELECT COUNT(*) n FROM annotations WHERE media_id=?',
            (mid,),
        ).fetchone()['n']
        item['excluded_count'] = conn.execute(
            'SELECT COUNT(*) n FROM excluded_frames WHERE media_id=?',
            (mid,),
        ).fetchone()['n']
        return item

    def _find_by_hash(self, project_id, digest):
        with db() as conn:
            row = conn.execute(
                'SELECT id FROM media WHERE project_id=? AND content_hash=?',
                (project_id, digest),
            ).fetchone()
            if not row:
                return None
            return self._load(row['id'], conn)

    def _backfill_hashes(self, project_id):
        with db() as conn:
            rows = conn.execute(
                '''SELECT id, path, content_hash FROM media
                   WHERE project_id=? AND (content_hash IS NULL OR content_hash='')''',
                (project_id,),
            ).fetchall()
            for row in rows:
                path = Path(row['path'])
                if not path.is_file():
                    continue
                digest = sha256_file(path)
                try:
                    conn.execute(
                        'UPDATE media SET content_hash=? WHERE id=?',
                        (digest, row['id']),
                    )
                except sqlite3.IntegrityError:
                    continue

    def extract(self, mid, frames_per_second: float):
        media = self.get(mid)
        if media['kind'] != 'video':
            raise ValueError('Only videos need frame extraction')
        source_fps = media['source_fps'] or media['fps'] or 25.0
        source_count = int(media['source_frame_count'] or 0)
        if source_count <= 0:
            raise ValueError('Video has no readable frames')
        extract_fps = clamp_extract_fps(source_fps, frames_per_second)
        frames_dir = Path(media['path']).parent / f'{mid}_frames'
        if frames_dir.exists():
            shutil.rmtree(frames_dir, ignore_errors=True)
        frames_dir.mkdir(parents=True, exist_ok=True)
        with db() as conn:
            conn.execute(
                "UPDATE media SET extract_status='extracting', extract_fps=? WHERE id=?",
                (extract_fps, mid),
            )
        try:
            extracted = extract_jpegs(media['path'], frames_dir, extract_fps)
        except Exception:
            shutil.rmtree(frames_dir, ignore_errors=True)
            with db() as conn:
                conn.execute("UPDATE media SET extract_status='failed' WHERE id=?", (mid,))
            raise
        if extracted <= 0:
            shutil.rmtree(frames_dir, ignore_errors=True)
            with db() as conn:
                conn.execute("UPDATE media SET extract_status='failed' WHERE id=?", (mid,))
            raise ValueError('Could not extract any frames from this video')
        with db() as conn:
            conn.execute(
                '''UPDATE media
                   SET frame_count=?, fps=?, extract_fps=?, frames_dir=?, extract_status='ready'
                   WHERE id=?''',
                (extracted, extract_fps, extract_fps, str(frames_dir), mid),
            )
            return self._load(mid, conn)

    def frame_rgb(self, mid, frame):
        media = self.get(mid)
        if media['extract_status'] not in (None, 'ready'):
            raise ValueError('Extract frames before opening this video')
        if frame < 0 or frame >= media['frame_count']:
            raise ValueError('Frame out of range')
        frames_dir = media.get('frames_dir')
        if frames_dir:
            jpeg = Path(frames_dir) / f'{frame:06d}.jpg'
            png = Path(frames_dir) / f'{frame:06d}.png'
            path = jpeg if jpeg.exists() else png
            if path.exists():
                with Image.open(path) as image:
                    loaded = image.convert('RGB')
                if not is_nearly_black(loaded):
                    return loaded
        if media['kind'] == 'image':
            with Image.open(media['path']) as image:
                return image.convert('RGB')
        fps = float(media.get('extract_fps') or media.get('fps') or media.get('source_fps') or 25.0)
        return read_frame(media['path'], frame / max(fps, 0.001))

    def frame_jpeg(self, mid, frame, quality=92):
        image = self.frame_rgb(mid, frame)
        out = io.BytesIO()
        image.save(out, 'JPEG', quality=quality, subsampling=0)
        return out.getvalue()

    def frames(self, mid, start, limit):
        media = self.get(mid)
        count = int(media['frame_count'] or 0)
        if count <= 0:
            return []
        start = max(0, min(int(start), count - 1))
        end = min(count, start + max(0, min(int(limit), 20000)))
        labels_by_frame: dict[int, list[dict]] = {}
        with db() as conn:
            anns = {
                row['frame']: row['n']
                for row in conn.execute(
                    'SELECT frame, COUNT(*) n FROM annotations WHERE media_id=? AND frame>=? AND frame<? GROUP BY frame',
                    (mid, start, end),
                )
            }
            excluded = {
                row['frame']
                for row in conn.execute(
                    'SELECT frame FROM excluded_frames WHERE media_id=? AND frame>=? AND frame<?',
                    (mid, start, end),
                )
            }
            for row in conn.execute(
                '''SELECT a.id annotation_id, a.frame, a.source, l.id label_id, l.name, l.color
                   FROM annotations a JOIN labels l ON l.id=a.label_id
                   WHERE a.media_id=? AND a.frame>=? AND a.frame<?
                   ORDER BY a.frame, a.id''',
                (mid, start, end),
            ):
                labels_by_frame.setdefault(row['frame'], []).append(
                    {
                        'annotation_id': row['annotation_id'],
                        'id': row['label_id'],
                        'name': row['name'],
                        'color': row['color'],
                        'source': row['source'],
                    }
                )
        return [
            {
                'frame': index,
                'annotation_count': anns.get(index, 0),
                'excluded': index in excluded,
                'labels': labels_by_frame.get(index, []),
            }
            for index in range(start, end)
        ]

    def set_excluded(self, mid, frame, excluded=True, delete_annotations=False):
        masks = []
        with db() as conn:
            if excluded:
                conn.execute(
                    'INSERT OR IGNORE INTO excluded_frames(media_id, frame) VALUES (?,?)',
                    (mid, frame),
                )
            else:
                conn.execute(
                    'DELETE FROM excluded_frames WHERE media_id=? AND frame=?',
                    (mid, frame),
                )
            if delete_annotations:
                masks = [
                    row['mask_path']
                    for row in conn.execute(
                        'SELECT mask_path FROM annotations WHERE media_id=? AND frame=?',
                        (mid, frame),
                    )
                ]
                conn.execute('DELETE FROM annotations WHERE media_id=? AND frame=?', (mid, frame))
        for path in masks:
            Path(path).unlink(missing_ok=True)
        return {'frame': frame, 'excluded': excluded, 'annotations_deleted': len(masks)}

    def delete(self, mid):
        media = self.get(mid)
        with db() as conn:
            masks = [
                row['mask_path']
                for row in conn.execute('SELECT mask_path FROM annotations WHERE media_id=?', (mid,))
            ]
            conn.execute('DELETE FROM media WHERE id=?', (mid,))
        Path(media['path']).unlink(missing_ok=True)
        if media.get('frames_dir'):
            shutil.rmtree(media['frames_dir'], ignore_errors=True)
        for path in masks:
            Path(path).unlink(missing_ok=True)

    def set_complete(self, mid, complete: bool):
        media = self.get(mid)
        if media['kind'] == 'image':
            raise ValueError('Use the project stills complete endpoint')
        flag = 1 if complete else 0
        with db() as conn:
            conn.execute('UPDATE media SET annotation_complete=? WHERE id=?', (flag, mid))
            return self._load(mid, conn)

    def set_project_images_complete(self, project_id, complete: bool):
        flag = 1 if complete else 0
        with db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) n FROM media WHERE project_id=? AND kind='image'",
                (project_id,),
            ).fetchone()['n']
            if not count:
                raise ValueError('No stills in this project')
            conn.execute(
                "UPDATE media SET annotation_complete=? WHERE project_id=? AND kind='image'",
                (flag, project_id),
            )
        return {'annotation_complete': bool(complete), 'updated': int(count)}

    def delete_project_images(self, project_id):
        with db() as conn:
            rows = conn.execute(
                "SELECT id FROM media WHERE project_id=? AND kind='image' ORDER BY id",
                (project_id,),
            ).fetchall()
        ids = [row['id'] for row in rows]
        for mid in ids:
            self.delete(mid)
        return {'ok': True, 'deleted': len(ids)}

    def project_stills(self, project_id):
        with db() as conn:
            rows = conn.execute(
                "SELECT id FROM media WHERE project_id=? AND kind='image' ORDER BY id",
                (project_id,),
            ).fetchall()
            return [self._load(row['id'], conn) for row in rows]


media_service = MediaService()
