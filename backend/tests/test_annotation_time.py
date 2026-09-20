import sqlite3
import tempfile
import unittest
from pathlib import Path


class AnnotationTimeTests(unittest.TestCase):
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
        self.conn.execute(
            "INSERT INTO labels(project_id,name,color) VALUES (?,?,?)",
            (self.pid, 'Crack', '#E45B5B'),
        )
        cur = self.conn.execute(
            '''INSERT INTO media(project_id,name,kind,path,width,height,frame_count,fps,extract_status)
               VALUES (?,?,?,?,?,?,?,?,?)''',
            (self.pid, 'clip.mp4', 'video', str(Path(self.tmp.name) / 'clip.mp4'), 64, 48, 8, 2.0, 'ready'),
        )
        self.mid = cur.lastrowid
        self.conn.commit()

    def tearDown(self):
        from app.core.settings import settings
        settings.data_root = self._old_root
        self.conn.close()
        self.tmp.cleanup()

    def test_heartbeat_adds_seconds_and_project_sum(self):
        from app.services.media_service import media_service
        from app.services.project_service import project_service
        first = media_service.add_annotation_seconds(self.mid, 12)
        self.assertEqual(first['annotation_seconds'], 12)
        self.assertEqual(first['project_annotation_seconds'], 12)
        second = media_service.add_annotation_seconds(self.mid, 8)
        self.assertEqual(second['annotation_seconds'], 20)
        listed = project_service.list()
        self.assertEqual(listed[0]['annotation_seconds'], 20)
        project = project_service.get(self.pid)
        self.assertEqual(project['annotation_seconds'], 20)
        self.assertEqual(project['media'][0]['annotation_seconds'], 20)

    def test_heartbeat_clamps_and_rejects_missing(self):
        from app.services.media_service import media_service
        capped = media_service.add_annotation_seconds(self.mid, 500)
        self.assertEqual(capped['annotation_seconds'], 30)
        with self.assertRaises(KeyError):
            media_service.add_annotation_seconds(99999, 5)


if __name__ == '__main__':
    unittest.main()
