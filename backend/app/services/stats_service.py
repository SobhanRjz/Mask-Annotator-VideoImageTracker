import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from app.core.db import db
from app.core.settings import settings
from app.utils.cluster import kmeans_1d

HEATMAP_SIZE = 64
MAX_MASK_PIXELS = 64_000_000
BITS_BYTES = HEATMAP_SIZE * HEATMAP_SIZE // 8
REPORT_TTL_SECONDS = 60
ROW_BATCH = 4096
BACKFILL_CHUNK = 256
BACKFILL_WORKERS = 4
UNUSABLE = (0, b'')


def _ready_clause():
    return "(m.kind = 'image' OR m.extract_status = 'ready')"


def mask_features(gray):
    """Return (pixel area, packed 64x64 occupancy bits) for an 'L' mask image."""
    area = sum(gray.histogram()[128:])
    if area <= 0:
        return UNUSABLE
    small = np.asarray(
        gray.resize((HEATMAP_SIZE, HEATMAP_SIZE), Image.Resampling.BILINEAR)
    )
    return int(area), np.packbits(small > 16).tobytes()


def read_mask_features(path):
    """Decode a mask file once. None means the file is missing (retry later)."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        with Image.open(path) as image:
            if image.width * image.height > MAX_MASK_PIXELS:
                return UNUSABLE
            return mask_features(image.convert('L'))
    except Exception:
        return UNUSABLE


class _SpatialAccumulator:
    def __init__(self):
        self.total = np.zeros(HEATMAP_SIZE * HEATMAP_SIZE, dtype=np.float64)
        self.by_label = {}
        self.areas = []
        self._pending = []

    def add(self, label, area, bits):
        if area <= 0 or len(bits) != BITS_BYTES:
            return
        self._pending.append((label, area, bits))
        if len(self._pending) >= ROW_BATCH:
            self.flush()

    def flush(self):
        if not self._pending:
            return
        packed = np.frombuffer(
            b''.join(item[2] for item in self._pending), dtype=np.uint8
        ).reshape(len(self._pending), BITS_BYTES)
        occupied = np.unpackbits(packed, axis=1)
        self.total += occupied.sum(axis=0)
        groups = {}
        for index, (label, area, _bits) in enumerate(self._pending):
            self.areas.append(int(area))
            groups.setdefault(label, []).append(index)
        for label, indexes in groups.items():
            if label not in self.by_label:
                self.by_label[label] = np.zeros_like(self.total)
            self.by_label[label] += occupied[indexes].sum(axis=0)
        self._pending = []

    def result(self):
        self.flush()
        return {
            'all': _grid(self.total),
            'by_label': {name: _grid(acc) for name, acc in self.by_label.items()},
        }, self.areas


def _grid(acc):
    peak = float(acc.max())
    values = acc / peak if peak > 0 else acc
    return {
        'width': HEATMAP_SIZE,
        'height': HEATMAP_SIZE,
        'values': values.reshape(HEATMAP_SIZE, HEATMAP_SIZE).tolist(),
    }


class StatsService:
    def __init__(self):
        self._lock = threading.Lock()
        self._cached = None

    def overview(self):
        with self._lock:
            stamp = self._stamp()
            cached = self._cached
            if cached and cached[0] == stamp and time.monotonic() - cached[2] < REPORT_TTL_SECONDS:
                return cached[1]
            report = self._build_overview()
            self._cached = (stamp, report, time.monotonic())
            return report

    def remember_mask(self, path, mask):
        """Prefill the per-mask cache when a mask is saved, so the dashboard never decodes it."""
        gray = Image.fromarray(np.asarray(mask, dtype=np.uint8) * 255)
        area, bits = mask_features(gray)
        self._store([(str(path), area, bits)])

    def _stamp(self):
        """Cheap change detector: any SQLite commit touches the db file or its WAL."""
        db_path = Path(settings.db_path)
        parts = [str(db_path)]
        for path in (db_path, db_path.with_name(db_path.name + '-wal')):
            try:
                info = path.stat()
                parts.append((info.st_mtime_ns, info.st_size))
            except OSError:
                parts.append(None)
        return tuple(parts)

    def _store(self, entries):
        if not entries:
            return
        with db() as conn:
            conn.executemany(
                'INSERT OR REPLACE INTO mask_stats(mask_path, area, bits) VALUES (?, ?, ?)',
                entries,
            )

    def _prune(self):
        with db() as conn:
            conn.execute(
                '''DELETE FROM mask_stats
                   WHERE mask_path NOT IN (
                       SELECT mask_path FROM annotations
                       UNION
                       SELECT mask_path FROM archived_annotations
                   )'''
            )

    def _build_overview(self):
        self._prune()
        with db() as conn:
            project_count = conn.execute('SELECT COUNT(*) n FROM projects').fetchone()['n']
            media_rows = [
                dict(row)
                for row in conn.execute(
                    f'''SELECT kind, width, height, frame_count, annotation_seconds
                        FROM media m WHERE {_ready_clause()}'''
                )
            ]
            extracted = conn.execute(
                f'SELECT COALESCE(SUM(frame_count), 0) n FROM media m WHERE {_ready_clause()}'
            ).fetchone()['n']
            annotated = conn.execute(
                f'''SELECT COUNT(*) n FROM (
                        SELECT a.media_id, a.frame
                        FROM annotations a
                        JOIN media m ON m.id = a.media_id
                        WHERE {_ready_clause()}
                        GROUP BY a.media_id, a.frame
                    )'''
            ).fetchone()['n']
            defects = [
                dict(row)
                for row in conn.execute(
                    f'''SELECT l.name, MIN(l.color) color, COUNT(*) count
                        FROM annotations a
                        JOIN media m ON m.id = a.media_id
                        JOIN labels l ON l.id = a.label_id
                        WHERE {_ready_clause()}
                        GROUP BY l.name
                        ORDER BY count DESC, l.name'''
                )
            ]
            continue_target = self._continue_target(conn)
            spatial, areas = self._mask_spatial(conn)
            video_count = sum(1 for row in media_rows if row['kind'] == 'video')
            image_count = sum(1 for row in media_rows if row['kind'] == 'image')
            video_seconds = sum(
                int(row['annotation_seconds'] or 0)
                for row in media_rows
                if row['kind'] == 'video'
            )
            image_seconds = sum(
                int(row['annotation_seconds'] or 0)
                for row in media_rows
                if row['kind'] == 'image'
            )

        widths = [int(row['width'] or 0) for row in media_rows]
        heights = [int(row['height'] or 0) for row in media_rows]
        avg_width = round(sum(widths) / len(widths)) if widths else 0
        avg_height = round(sum(heights) / len(heights)) if heights else 0
        pixels = [w * h for w, h in zip(widths, heights)]
        avg_megapixels = (sum(pixels) / len(pixels) / 1_000_000) if pixels else 0.0
        extracted = int(extracted or 0)
        annotated = int(annotated or 0)
        return {
            'project_count': int(project_count or 0),
            'video_count': video_count,
            'image_count': image_count,
            'frames_extracted': extracted,
            'frames_annotated': annotated,
            'coverage': (annotated / extracted) if extracted else 0.0,
            'avg_width': avg_width,
            'avg_height': avg_height,
            'avg_megapixels': avg_megapixels,
            'defects': defects,
            'heatmap': spatial['all'],
            'heatmaps': spatial['by_label'],
            'continue': continue_target,
            'mask_size_clusters': kmeans_1d(areas, k=3),
            'mask_count': len(areas),
            'video_seconds_total': video_seconds,
            'image_seconds_total': image_seconds,
            'avg_seconds_per_video': (video_seconds / video_count) if video_count else 0,
            'avg_seconds_per_image': (image_seconds / image_count) if image_count else 0,
            'seconds_total': video_seconds + image_seconds,
        }

    def _continue_target(self, conn):
        project = conn.execute(
            '''SELECT p.id, p.slug
               FROM projects p
               LEFT JOIN media m ON m.project_id = p.id
               LEFT JOIN annotations a ON a.media_id = m.id
               GROUP BY p.id
               ORDER BY MAX(COALESCE(a.updated_at, p.updated_at)) DESC, p.id DESC
               LIMIT 1'''
        ).fetchone()
        if not project:
            return None
        media_rows = list(
            conn.execute(
                f'''SELECT m.id, m.frame_count,
                           (SELECT COUNT(DISTINCT a.frame)
                            FROM annotations a WHERE a.media_id = m.id) AS annotated,
                           (SELECT MAX(a.updated_at)
                            FROM annotations a WHERE a.media_id = m.id) AS last_ann
                    FROM media m
                    WHERE m.project_id = ? AND {_ready_clause()}''',
                (project['id'],),
            )
        )
        target = {
            'project_id': int(project['id']),
            'project_slug': project['slug'],
            'media_id': None,
            'frame': None,
        }
        if not media_rows:
            return target
        incomplete = [
            row for row in media_rows
            if int(row['annotated'] or 0) < int(row['frame_count'] or 0)
        ]
        pool = incomplete or media_rows
        pool.sort(key=lambda row: (row['last_ann'] or '', int(row['id'])), reverse=True)
        media = pool[0]
        media_id = int(media['id'])
        annotated_frames = {
            int(row['frame'])
            for row in conn.execute(
                'SELECT DISTINCT frame FROM annotations WHERE media_id = ?',
                (media_id,),
            )
        }
        excluded_frames = {
            int(row['frame'])
            for row in conn.execute(
                'SELECT frame FROM excluded_frames WHERE media_id = ?',
                (media_id,),
            )
        }
        frame = 0
        for index in range(int(media['frame_count'] or 0)):
            if index not in annotated_frames and index not in excluded_frames:
                frame = index
                break
        target['media_id'] = media_id
        target['frame'] = frame
        return target

    def _mask_spatial(self, conn):
        acc = _SpatialAccumulator()
        uncached = []
        rows = conn.execute(
            f'''SELECT a.mask_path, l.name AS label_name, s.area, s.bits
                FROM annotations a
                JOIN media m ON m.id = a.media_id
                JOIN labels l ON l.id = a.label_id
                LEFT JOIN mask_stats s ON s.mask_path = a.mask_path
                WHERE {_ready_clause()}'''
        )
        for row in rows:
            label = row['label_name'] or 'Unknown'
            if row['area'] is None:
                uncached.append((row['mask_path'], label))
                continue
            acc.add(label, row['area'], row['bits'])
        self._backfill(uncached, acc)
        return acc.result()

    def _backfill(self, uncached, acc):
        """Decode masks that were never cached (legacy data), persisting each chunk."""
        if not uncached:
            return
        with ThreadPoolExecutor(max_workers=BACKFILL_WORKERS) as pool:
            for start in range(0, len(uncached), BACKFILL_CHUNK):
                chunk = uncached[start:start + BACKFILL_CHUNK]
                decoded = pool.map(read_mask_features, [path for path, _label in chunk])
                entries = []
                for (path, label), features in zip(chunk, decoded):
                    if features is None:
                        continue
                    area, bits = features
                    entries.append((path, area, bits))
                    acc.add(label, area, bits)
                self._store(entries)


stats_service = StatsService()
