from pathlib import Path

import numpy as np
from PIL import Image

from app.core.db import db
from app.utils.cluster import kmeans_1d
from app.utils.images import load_mask

HEATMAP_SIZE = 64


def _ready_clause():
    return "(m.kind = 'image' OR m.extract_status = 'ready')"


class StatsService:
    def overview(self):
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
                    '''SELECT l.name, MIN(l.color) color, COUNT(*) count
                       FROM annotations a
                       JOIN labels l ON l.id = a.label_id
                       GROUP BY l.name
                       ORDER BY count DESC, l.name'''
                )
            ]
            mask_rows = list(
                conn.execute(
                    f'''SELECT a.mask_path, l.name AS label_name
                        FROM annotations a
                        JOIN media m ON m.id = a.media_id
                        JOIN labels l ON l.id = a.label_id
                        WHERE {_ready_clause()}'''
                )
            )
            continue_target = self._continue_target(conn)
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

        spatial, areas = self._mask_spatial(mask_rows)
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

    def _grid(self, acc):
        peak = float(acc.max())
        values = acc / peak if peak > 0 else acc
        return {
            'width': HEATMAP_SIZE,
            'height': HEATMAP_SIZE,
            'values': values.tolist(),
        }

    def _mask_spatial(self, rows):
        acc_all = np.zeros((HEATMAP_SIZE, HEATMAP_SIZE), dtype=np.float64)
        acc_by_label = {}
        areas = []
        for row in rows:
            path = Path(row['mask_path'])
            if not path.is_file():
                continue
            try:
                mask = load_mask(path)
            except Exception:
                continue
            area = int(np.count_nonzero(mask))
            if area <= 0:
                continue
            areas.append(area)
            resized = np.asarray(
                Image.fromarray(mask.astype(np.uint8) * 255, 'L').resize(
                    (HEATMAP_SIZE, HEATMAP_SIZE),
                    Image.BILINEAR,
                )
            )
            occupied = resized > 16
            acc_all += occupied
            label = row['label_name'] or 'Unknown'
            if label not in acc_by_label:
                acc_by_label[label] = np.zeros((HEATMAP_SIZE, HEATMAP_SIZE), dtype=np.float64)
            acc_by_label[label] += occupied
        return {
            'all': self._grid(acc_all),
            'by_label': {name: self._grid(grid) for name, grid in acc_by_label.items()},
        }, areas


stats_service = StatsService()
