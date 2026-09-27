import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np


class HealthyFrameTests(unittest.TestCase):
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
        cur = self.conn.execute("INSERT INTO projects(name,description) VALUES ('p','')")
        self.pid = cur.lastrowid
        cur = self.conn.execute(
            "INSERT INTO labels(project_id,name,color) VALUES (?,?,?)",
            (self.pid, 'Crack', '#E45B5B'),
        )
        self.lid = cur.lastrowid
        cur = self.conn.execute(
            '''INSERT INTO media(project_id,name,kind,path,width,height,frame_count,fps,extract_status)
               VALUES (?,?,?,?,?,?,?,?,?)''',
            (self.pid, 'still.jpg', 'image', str(Path(self.tmp.name) / 'still.jpg'), 8, 8, 1, 1.0, 'ready'),
        )
        self.mid = cur.lastrowid
        Path(self.tmp.name, 'still.jpg').write_bytes(b'not-a-real-jpeg')
        self.conn.commit()

    def tearDown(self):
        from app.core.settings import settings
        settings.data_root = self._old_root
        self.conn.close()
        self.tmp.cleanup()

    def test_marking_healthy_removes_masks_and_saving_a_mask_clears_it(self):
        from app.services.annotation_service import annotation_service
        from app.services.media_service import media_service
        from app.services.project_service import project_service

        mask = np.zeros((8, 8), dtype=bool)
        mask[1:4, 1:4] = True
        annotation_service.save(self.mid, 0, self.lid, mask, 'manual')
        marked = media_service.set_healthy(self.mid, 0, True)
        self.assertTrue(marked['healthy'])
        self.assertEqual(marked['annotations_deleted'], 1)
        frames = media_service.frames(self.mid, 0, 5)
        self.assertTrue(frames[0]['healthy'])
        self.assertEqual(frames[0]['annotation_count'], 0)
        project = project_service.get(self.pid)
        self.assertEqual(project['media'][0]['healthy_count'], 1)
        self.assertEqual(project['media'][0]['annotation_count'], 0)

        annotation_service.save(self.mid, 0, self.lid, mask, 'manual')
        frames = media_service.frames(self.mid, 0, 5)
        self.assertFalse(frames[0]['healthy'])
        self.assertEqual(frames[0]['annotation_count'], 1)

    def test_backup_restores_healthy_frames(self):
        from app.services.backup_service import backup_service
        from app.services.media_service import media_service
        from app.services.project_service import project_service

        media_service.set_healthy(self.mid, 0, True)
        zip_path = backup_service.build(self.pid)
        project_service.delete(self.pid)
        restored = backup_service.restore(zip_path)
        frames = media_service.frames(restored['media'][0]['id'], 0, 5)
        self.assertTrue(frames[0]['healthy'])


if __name__ == '__main__':
    unittest.main()
