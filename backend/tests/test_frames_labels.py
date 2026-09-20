import sqlite3
import tempfile
import unittest
from pathlib import Path


class FramesAndLabelTests(unittest.TestCase):
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
            (self.pid, 'clip.mp4', 'video', str(Path(self.tmp.name) / 'clip.mp4'), 64, 48, 8, 2.0, 'ready'),
        )
        self.mid = cur.lastrowid
        self.conn.execute(
            'INSERT INTO annotations(media_id,frame,label_id,mask_path,source) VALUES (?,?,?,?,?)',
            (self.mid, 3, self.lid, str(Path(self.tmp.name) / 'm.png'), 'manual'),
        )
        self.conn.commit()

    def tearDown(self):
        from app.core.settings import settings
        settings.data_root = self._old_root
        self.conn.close()
        self.tmp.cleanup()

    def test_frames_include_label_tags(self):
        from app.services.media_service import media_service
        rows = media_service.frames(self.mid, 0, 20)
        self.assertEqual(len(rows), 8)
        tagged = rows[3]
        self.assertEqual(tagged['annotation_count'], 1)
        self.assertEqual(tagged['labels'][0]['name'], 'Crack')
        self.assertEqual(tagged['labels'][0]['color'], '#E45B5B')
        self.assertTrue(all('labels' in row for row in rows))

    def test_update_label_color_stays_unique(self):
        from app.services.project_service import project_service
        added = project_service.add_label(self.pid, 'Rootish', '#E45B5B')
        self.assertNotEqual(added['color'].upper(), '#E45B5B')
        updated = project_service.update_label(self.pid, added['id'], color='#E45B5B')
        self.assertNotEqual(updated['color'].upper(), '#E45B5B')


if __name__ == '__main__':
    unittest.main()
