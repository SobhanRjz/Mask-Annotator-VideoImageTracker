import sqlite3
import tempfile
import unittest
from pathlib import Path


class ProjectDeleteTests(unittest.TestCase):
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

    def test_delete_removes_annotated_project_files_and_frees_the_name(self):
        from app.core.db import db
        from app.core.settings import settings
        from app.services.project_service import project_service

        project = project_service.create('Job to delete')
        pid = project['id']
        label_id = project['labels'][0]['id']
        media_dir = settings.media_root / str(pid)
        media_file = media_dir / 'clip.mp4'
        media_file.write_bytes(b'fake-video')
        mask_path = settings.mask_root / '1' / 'mask.png'
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        mask_path.write_bytes(b'fake-mask')
        with db() as conn:
            cur = conn.execute(
                '''INSERT INTO media(project_id,name,kind,path,width,height,frame_count,fps,extract_status)
                   VALUES (?,?,?,?,?,?,?,?,?)''',
                (pid, 'clip.mp4', 'video', str(media_file), 64, 48, 8, 2.0, 'ready'),
            )
            conn.execute(
                'INSERT INTO annotations(media_id,frame,label_id,mask_path,source) VALUES (?,?,?,?,?)',
                (cur.lastrowid, 0, label_id, str(mask_path), 'manual'),
            )

        project_service.delete(pid)

        self.assertEqual(project_service.list(), [])
        with self.assertRaises(KeyError):
            project_service.get(pid)
        self.assertFalse(media_dir.exists())
        self.assertFalse(mask_path.exists())
        reused = project_service.create('Job to delete')
        self.assertEqual(reused['slug'], 'job-to-delete')
        conn = sqlite3.connect(settings.db_path)
        try:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM labels').fetchone()[0], 8)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM media').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM annotations').fetchone()[0], 0)
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
