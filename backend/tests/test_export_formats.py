import io
import json
import sqlite3
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from app.core.settings import settings
from app.utils.images import save_mask


def _jpeg():
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), (12, 24, 36)).save(buf, 'JPEG')
    return buf.getvalue()


class ExportFormatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old_root = settings.data_root
        settings.data_root = Path(self.tmp.name)
        from app.core.db import initialize_db
        initialize_db()
        self.conn = sqlite3.connect(settings.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.pid_a = self._project('Site A')
        self.pid_b = self._project('Site B')
        self.lid_a_crack = self._label(self.pid_a, 'Crack', '#E45B5B')
        self.lid_a_root = self._label(self.pid_a, 'Root', '#51B56D')
        self.lid_b_crack = self._label(self.pid_b, 'Crack', '#FF0000')
        self.mid_a = self._media(self.pid_a, 'clip-a.mp4', 3)
        self.mid_b = self._media(self.pid_b, 'clip-b.mp4', 2)
        self.ann_manual = self._annotation(self.mid_a, 0, self.lid_a_crack, 'manual', (1, 1, 3, 3))
        self.ann_auto = self._annotation(self.mid_a, 1, self.lid_a_root, 'auto', (4, 4, 2, 2))
        self._annotation(self.mid_b, 0, self.lid_b_crack, 'manual', (2, 2, 3, 3))
        self.conn.execute(
            'INSERT INTO excluded_frames(media_id,frame) VALUES (?,?)',
            (self.mid_a, 2),
        )
        self.conn.commit()

    def tearDown(self):
        settings.data_root = self._old_root
        self.conn.close()
        self.tmp.cleanup()

    def _project(self, name):
        cur = self.conn.execute(
            "INSERT INTO projects(name,description) VALUES (?, '')", (name,)
        )
        return cur.lastrowid

    def _label(self, pid, name, color):
        cur = self.conn.execute(
            'INSERT INTO labels(project_id,name,color) VALUES (?,?,?)',
            (pid, name, color),
        )
        return cur.lastrowid

    def _media(self, pid, name, frames):
        cur = self.conn.execute(
            '''INSERT INTO media(project_id,name,kind,path,width,height,frame_count,fps,extract_status)
               VALUES (?,?,?,?,?,?,?,?,?)''',
            (pid, name, 'video', str(Path(self.tmp.name) / name), 8, 8, frames, 1.0, 'ready'),
        )
        return cur.lastrowid

    def _annotation(self, mid, frame, lid, source, box):
        x, y, w, h = box
        mask = np.zeros((8, 8), dtype=bool)
        mask[y:y + h, x:x + w] = True
        path = Path(self.tmp.name) / 'masks' / f'{mid}'
        path.mkdir(parents=True, exist_ok=True)
        file = path / f'{source}-{frame}-{lid}.png'
        save_mask(file, mask)
        cur = self.conn.execute(
            '''INSERT INTO annotations(media_id,frame,label_id,mask_path,source)
               VALUES (?,?,?,?,?)''',
            (mid, frame, lid, str(file), source),
        )
        return cur.lastrowid

    def _zip(self, project_ids, fmt, **opts):
        from app.services.export_service import export_service
        with patch('app.services.export_service.media_service') as media:
            media.frame_jpeg.return_value = _jpeg()
            return export_service.build_many(project_ids, fmt, **opts)

    def _read(self, path, name):
        with zipfile.ZipFile(path) as archive:
            return archive.read(name)

    def test_coco_instance_schema_and_bbox(self):
        path = self._zip([self.pid_a], 'coco', include_unannotated=False)
        coco = json.loads(self._read(path, 'annotations/instances_default.json'))
        self.assertEqual(set(coco), {'info', 'licenses', 'images', 'annotations', 'categories'})
        self.assertTrue(coco['images'])
        self.assertTrue(all('media_id' not in image for image in coco['images']))
        self.assertTrue(all('/' not in image['file_name'] for image in coco['images']))
        self.assertEqual({row['name'] for row in coco['categories']}, {'Crack', 'Root'})
        crack = next(row for row in coco['annotations'] if row['category_id'] == 1)
        self.assertEqual(crack['bbox'], [1, 1, 3, 3])
        self.assertEqual(crack['iscrowd'], 0)
        self.assertEqual(crack['area'], 9)
        self.assertIsInstance(crack['segmentation'], list)
        self.assertGreaterEqual(len(crack['segmentation'][0]), 6)
        names = zipfile.ZipFile(path).namelist()
        self.assertTrue(any(name.startswith('images/') and name.endswith('.jpg') for name in names))
        self.assertFalse(any('_f000002.jpg' in name for name in names))

    def test_yolo_seg_normalized_and_empty_negatives(self):
        path = self._zip([self.pid_a], 'yolo', include_unannotated=False)
        data = self._read(path, 'data.yaml').decode()
        self.assertIn('train: images', data)
        self.assertIn('val: images', data)
        self.assertIn('0: Crack', data)
        self.assertIn('1: Root', data)
        classes = self._read(path, 'classes.txt').decode().strip().splitlines()
        self.assertEqual(classes, ['Crack', 'Root'])
        with zipfile.ZipFile(path) as archive:
            crack_file = next(
                name for name in archive.namelist()
                if name.startswith('labels/') and name.endswith('_f000000.txt')
            )
            line = archive.read(crack_file).decode().strip().split()
        self.assertEqual(line[0], '0')
        coords = [float(value) for value in line[1:]]
        self.assertGreaterEqual(len(coords), 6)
        self.assertTrue(all(0 <= value <= 1 for value in coords))

        negatives = self._zip([self.pid_b], 'yolo', include_unannotated=True)
        with zipfile.ZipFile(negatives) as archive:
            image_names = [name for name in archive.namelist() if name.startswith('images/')]
            label_names = [name for name in archive.namelist() if name.startswith('labels/')]
            self.assertEqual(len(label_names), len(image_names))
            empty = next(
                name for name in label_names if name.endswith('_f000001.txt')
            )
            self.assertEqual(archive.read(empty).decode(), '')

    def test_voc_writes_class_and_instance_masks(self):
        path = self._zip([self.pid_a], 'voc', include_unannotated=False)
        with zipfile.ZipFile(path) as archive:
            self.assertTrue(any(name.startswith('JPEGImages/') for name in archive.namelist()))
            class_name = next(
                name for name in archive.namelist()
                if name.startswith('SegmentationClass/') and name.endswith('_f000000.png')
            )
            pixels = np.asarray(Image.open(io.BytesIO(archive.read(class_name))))
        self.assertEqual(tuple(pixels[1, 1]), (228, 91, 91))
        self.assertEqual(tuple(pixels[0, 0]), (0, 0, 0))
        labelmap = self._read(path, 'labelmap.txt').decode()
        self.assertIn('Crack:228,91,91::', labelmap)

    def test_excluded_frames_omit_images_and_annotations(self):
        self._annotation(self.mid_a, 2, self.lid_a_crack, 'manual', (1, 1, 2, 2))
        self.conn.commit()
        path = self._zip(
            [self.pid_a],
            'coco',
            include_unannotated=True,
            include_auto=True,
            include_manual=True,
        )
        coco = json.loads(self._read(path, 'annotations/instances_default.json'))
        self.assertFalse(
            any('_f000002.jpg' in image['file_name'] for image in coco['images'])
        )
        self.assertEqual(len(coco['images']), 2)
        self.assertEqual(len(coco['annotations']), 2)
        names = zipfile.ZipFile(path).namelist()
        self.assertFalse(any('_f000002' in name for name in names))

    def test_filter_unannotated_and_auto(self):
        path = self._zip(
            [self.pid_a],
            'native',
            include_unannotated=False,
            include_auto=False,
            include_manual=True,
        )
        data = json.loads(self._read(path, 'project.json'))
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(len(data['annotations']), 1)
        self.assertEqual(data['annotations'][0]['source'], 'manual')

    def test_merge_all_projects_shares_class_names(self):
        path = self._zip(None, 'coco', include_unannotated=False)
        coco = json.loads(self._read(path, 'annotations/instances_default.json'))
        names = [row['name'] for row in coco['categories']]
        self.assertEqual(names, ['Crack', 'Root'])
        self.assertEqual(len(coco['images']), 3)
        self.assertEqual(len(coco['annotations']), 3)
        self.assertIn('Merged export', coco['info']['description'])
        self.assertTrue(path.name.startswith('all-projects-coco-'))

    def test_job_reports_progress_then_completes(self):
        from app.services.export_service import ExportService
        service = ExportService()
        with patch('app.services.export_service.media_service') as media:
            media.frame_jpeg.return_value = _jpeg()
            job = service.start('coco', [self.pid_a], True, True, True)
            deadline = time.time() + 5
            snap = service.get(job['id'])
            while snap['status'] in ('queued', 'running'):
                if time.time() > deadline:
                    self.fail(f'stuck in {snap}')
                time.sleep(0.02)
                snap = service.get(job['id'])
        self.assertEqual(snap['status'], 'completed')
        self.assertEqual(snap['progress'], 100)
        self.assertTrue(snap['filename'].endswith('.zip'))
        service.pool.shutdown(wait=False)

    def test_empty_filters_rejected(self):
        from app.services.export_service import export_service
        with self.assertRaises(ValueError):
            export_service.build_many([self.pid_a], 'coco', False, False, False)


if __name__ == '__main__':
    unittest.main()
