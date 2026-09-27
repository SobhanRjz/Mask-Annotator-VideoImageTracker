import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image


class FullFrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from app.core.settings import settings
        self._old_root = settings.data_root
        settings.data_root = Path(self.tmp.name)
        from app.core.db import initialize_db
        initialize_db()

    def tearDown(self):
        from app.core.settings import settings
        settings.data_root = self._old_root
        self.tmp.cleanup()

    def test_projects_keep_full_frame_labels_outside_the_defect_catalog(self):
        from app.services.project_service import project_service

        project = project_service.create('Site')
        self.assertEqual(
            [row['name'] for row in project['labels'] if row['kind'] == 'full'],
            ['Healthy', 'Loss of view (CU)'],
        )
        project_service.save_defect_labels([{'name': 'Crack', 'color': '#112233'}])
        kept = project_service.get(project['id'])
        self.assertEqual([row['name'] for row in kept['labels'] if row['kind'] != 'full'], ['Crack'])
        self.assertEqual(
            [row['name'] for row in kept['labels'] if row['kind'] == 'full'],
            ['Healthy', 'Loss of view (CU)'],
        )
        with self.assertRaises(ValueError):
            project_service.save_defect_labels([{'name': 'Healthy', 'color': '#225588'}])

    def test_saving_a_full_frame_covers_the_image_and_removes_other_masks(self):
        from app.core.db import db
        from app.core.settings import settings
        from app.services.annotation_service import annotation_service
        from app.services.project_service import project_service

        project = project_service.create('Pipe')
        crack = next(row for row in project['labels'] if row['name'] == 'Crack')
        healthy = next(row for row in project['labels'] if row['name'] == 'Healthy')
        media_id = self._video(project['id'], frames=3, width=4, height=2)
        mask = settings.mask_root / str(media_id) / 'crack.png'
        mask.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.array([[255, 0], [0, 0], [0, 0], [0, 0]], dtype=np.uint8), 'L').save(mask)
        with db() as conn:
            conn.execute(
                'INSERT INTO annotations(media_id,frame,label_id,mask_path,source) VALUES (?,?,?,?,?)',
                (media_id, 1, crack['id'], str(mask), 'manual'),
            )
            conn.execute('INSERT INTO healthy_frames(media_id,frame) VALUES (?,?)', (media_id, 1))

        saved = annotation_service.save_full_frame(media_id, 1, healthy['id'])
        masks = annotation_service.list(media_id, 1)
        self.assertEqual([row['id'] for row in masks], [saved['id']])
        self.assertEqual(masks[0]['label_name'], 'Healthy')
        self.assertTrue(annotation_service.mask(saved['id']).all())
        self.assertFalse(mask.exists())
        with db() as conn:
            healthy_mark = conn.execute(
                'SELECT COUNT(*) n FROM healthy_frames WHERE media_id=? AND frame=?',
                (media_id, 1),
            ).fetchone()['n']
        self.assertEqual(healthy_mark, 0)

    def test_fill_writes_whole_frames_and_keeps_manual_defects(self):
        from app.core.db import db
        from app.core.settings import settings
        from app.services.annotation_service import annotation_service
        from app.services.project_service import project_service

        project = project_service.create('Run')
        crack = next(row for row in project['labels'] if row['name'] == 'Crack')
        loss = next(row for row in project['labels'] if row['name'] == 'Loss of view (CU)')
        media_id = self._video(project['id'], frames=5, width=3, height=2)
        manual = settings.mask_root / str(media_id) / 'manual.png'
        auto = settings.mask_root / str(media_id) / 'auto.png'
        manual.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.zeros((2, 3), dtype=np.uint8), 'L').save(manual)
        Image.fromarray(np.zeros((2, 3), dtype=np.uint8), 'L').save(auto)
        with db() as conn:
            conn.execute(
                'INSERT INTO annotations(media_id,frame,label_id,mask_path,source) VALUES (?,?,?,?,?)',
                (media_id, 2, crack['id'], str(manual), 'manual'),
            )
            conn.execute(
                'INSERT INTO annotations(media_id,frame,label_id,mask_path,source) VALUES (?,?,?,?,?)',
                (media_id, 4, crack['id'], str(auto), 'auto'),
            )
            conn.execute('INSERT INTO excluded_frames(media_id,frame) VALUES (?,?)', (media_id, 0))

        created, stopped = annotation_service.fill_full_frames(media_id, loss['id'], 0, 4, 2, True)
        self.assertFalse(stopped)
        frames = {}
        for row in annotation_service.list(media_id):
            frames.setdefault(row['frame'], []).append(row)
        self.assertNotIn(0, frames)
        self.assertEqual(frames[2][0]['label_name'], 'Crack')
        self.assertEqual(frames[2][0]['source'], 'manual')
        self.assertEqual(frames[4][0]['label_name'], 'Loss of view (CU)')
        self.assertTrue(annotation_service.mask(frames[4][0]['id']).all())
        self.assertIn(frames[4][0]['id'], created)
        self.assertFalse(auto.exists())

    def _video(self, project_id, frames, width, height):
        from app.core.db import db
        from app.core.settings import settings

        path = settings.media_root / str(project_id) / 'clip.bin'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'video')
        with db() as conn:
            cur = conn.execute(
                '''INSERT INTO media(
                    project_id,name,kind,path,width,height,frame_count,fps,extract_status
                ) VALUES (?,?,?,?,?,?,?,?,?)''',
                (project_id, 'clip.mp4', 'video', str(path), width, height, frames, 1.0, 'ready'),
            )
            return cur.lastrowid


class FullFrameTrackingTests(unittest.TestCase):
    def test_full_frame_job_does_not_call_sam2(self):
        sys.modules.setdefault('torch', MagicMock())
        sys.modules.setdefault('sam2', MagicMock())
        sys.modules.setdefault('sam2.sam2_video_predictor', MagicMock())
        from app.services.tracking_service import TrackingService

        service = TrackingService()
        called = {}

        class FakeMedia:
            def get(self, mid):
                return {'id': mid, 'kind': 'video', 'frame_count': 5, 'project_id': 1, 'width': 2, 'height': 2}

        class FakeRuntime:
            def track(self, *_args, **_kwargs):
                called['sam2'] = True
                return []

        class FakeAnnotations:
            def require_full_label(self, _label_id, _project_id):
                return {'id': 3, 'kind': 'full', 'name': 'Healthy'}

            def fill_full_frames(self, *_args, **_kwargs):
                return [11, 12], False

        with patch('app.services.tracking_service.media_service', FakeMedia()), patch(
            'app.services.tracking_service.sam2_runtime', FakeRuntime()
        ), patch('app.services.tracking_service.annotation_service', FakeAnnotations()):
            job = service.start_full(1, 3, 0, 4, 2, True)
            deadline = time.time() + 3
            snap = service.get(job['id'])
            while snap['status'] in ('queued', 'running'):
                if time.time() > deadline:
                    self.fail(f'stuck in {snap}')
                time.sleep(0.02)
                snap = service.get(job['id'])

        self.assertNotIn('sam2', called)
        self.assertEqual(snap['status'], 'completed')
        self.assertEqual(snap['created_annotations'], [11, 12])
