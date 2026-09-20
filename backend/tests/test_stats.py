import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image


class StatsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from app.core.settings import settings
        self._old_root = settings.data_root
        settings.data_root = Path(self.tmp.name)
        from app.core.db import initialize_db
        initialize_db()
        self.conn = sqlite3.connect(settings.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')

    def tearDown(self):
        from app.core.settings import settings
        settings.data_root = self._old_root
        self.conn.close()
        self.tmp.cleanup()

    def _project(self, name):
        from app.services.project_service import project_service
        return project_service.create(name)

    def _media(self, pid, name, kind, frames, width=64, height=48, seconds=0):
        from app.core.settings import settings
        path = Path(self.tmp.name) / name
        path.write_bytes(b'x')
        status = 'ready' if kind == 'image' or frames else 'pending'
        cur = self.conn.execute(
            '''INSERT INTO media(
                project_id,name,kind,path,width,height,frame_count,fps,
                extract_status,annotation_seconds
            ) VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (pid, name, kind, str(path), width, height, frames, 1.0, status, seconds),
        )
        self.conn.commit()
        return cur.lastrowid

    def _mask(self, mid, frame, lid, pixels):
        from app.core.settings import settings
        folder = settings.mask_root / str(mid)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'{frame}.png'
        Image.fromarray((pixels.astype(np.uint8) * 255), 'L').save(path)
        self.conn.execute(
            'INSERT INTO annotations(media_id,frame,label_id,mask_path,source) VALUES (?,?,?,?,?)',
            (mid, frame, lid, str(path), 'manual'),
        )
        self.conn.commit()

    def test_overview_counts_extracted_annotated_time_and_defects(self):
        from app.services.stats_service import stats_service
        project = self._project('Harbor main')
        pid = project['id']
        crack = next(label['id'] for label in project['labels'] if label['name'] == 'Crack')
        root = next(label['id'] for label in project['labels'] if label['name'] == 'Root')
        video = self._media(pid, 'clip.mp4', 'video', 10, 80, 60, seconds=40)
        image = self._media(pid, 'still.jpg', 'image', 1, 40, 20, seconds=10)
        small = np.zeros((60, 80), dtype=bool)
        small[10:14, 10:14] = True
        large = np.zeros((60, 80), dtype=bool)
        large[20:50, 20:60] = True
        self._mask(video, 0, crack, small)
        self._mask(video, 1, crack, small)
        self._mask(image, 0, root, large)
        report = stats_service.overview()
        self.assertEqual(report['project_count'], 1)
        self.assertEqual(report['video_count'], 1)
        self.assertEqual(report['image_count'], 1)
        self.assertEqual(report['frames_extracted'], 11)
        self.assertEqual(report['frames_annotated'], 3)
        self.assertAlmostEqual(report['coverage'], 3 / 11)
        self.assertEqual(report['avg_width'], 60)
        self.assertEqual(report['avg_height'], 40)
        self.assertEqual(report['video_seconds_total'], 40)
        self.assertEqual(report['image_seconds_total'], 10)
        self.assertEqual(report['avg_seconds_per_video'], 40)
        self.assertEqual(report['avg_seconds_per_image'], 10)
        self.assertEqual(report['seconds_total'], 50)
        defects = {row['name']: row['count'] for row in report['defects']}
        self.assertEqual(defects['Crack'], 2)
        self.assertEqual(defects['Root'], 1)
        self.assertEqual(report['heatmap']['width'], 64)
        self.assertEqual(len(report['heatmap']['values']), 64)
        self.assertTrue(max(max(row) for row in report['heatmap']['values']) > 0)
        self.assertIn('Crack', report['heatmaps'])
        self.assertIn('Root', report['heatmaps'])
        crack_heat = report['heatmaps']['Crack']['values']
        root_heat = report['heatmaps']['Root']['values']
        self.assertNotEqual(crack_heat, root_heat)
        def peak(grid):
            best = (0, 0, -1.0)
            for y, row in enumerate(grid):
                for x, value in enumerate(row):
                    if value > best[2]:
                        best = (y, x, value)
            return best
        crack_y, crack_x, _peak = peak(crack_heat)
        root_y, root_x, _root = peak(root_heat)
        self.assertLess(crack_y + crack_x, root_y + root_x)
        self.assertEqual(report['continue']['media_id'], video)
        self.assertEqual(report['continue']['frame'], 2)
        self.assertGreaterEqual(len(report['mask_size_clusters']), 2)
        compact = next(row for row in report['mask_size_clusters'] if row['label'] == 'Compact')
        large_cluster = next(row for row in report['mask_size_clusters'] if row['label'] == 'Large')
        self.assertEqual(compact['count'], 2)
        self.assertEqual(large_cluster['count'], 1)

    def test_empty_overview(self):
        from app.services.stats_service import stats_service
        report = stats_service.overview()
        self.assertEqual(report['frames_extracted'], 0)
        self.assertEqual(report['heatmap']['values'][0][0], 0)
        self.assertEqual(report['heatmaps'], {})
        self.assertIsNone(report['continue'])
        self.assertEqual(report['mask_size_clusters'], [])
        self.assertEqual(report['defects'], [])


if __name__ == '__main__':
    unittest.main()
