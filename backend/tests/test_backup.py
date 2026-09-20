import json
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
from starlette.datastructures import UploadFile


class ProjectBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from app.core.settings import settings
        self._old_root = settings.data_root
        settings.data_root = Path(self.tmp.name)
        from app.core.db import initialize_db
        initialize_db()
        from app.services.project_service import project_service
        self.project = project_service.create('Inspection A', 'North interceptor')
        self.pid = self.project['id']

    def tearDown(self):
        from app.core.settings import settings
        settings.data_root = self._old_root
        self.tmp.cleanup()

    def _png(self, name, color='red'):
        buf = BytesIO()
        Image.new('RGB', (8, 8), color).save(buf, 'PNG')
        buf.seek(0)
        return UploadFile(filename=name, file=buf)

    def _seed(self):
        from app.services.annotation_service import annotation_service
        from app.services.media_service import media_service

        uploaded = media_service.upload(self.pid, [self._png('joint.png', 'navy')])
        media = uploaded[0]
        mask = np.zeros((8, 8), dtype=bool)
        mask[2:6, 2:6] = True
        annotation_service.save(media['id'], 0, self.project['labels'][1]['id'], mask, 'manual')
        media_service.set_excluded(media['id'], 0, True, delete_annotations=False)
        return media

    def test_backup_roundtrip_restores_media_masks_and_excluded_frames(self):
        from app.core.db import db
        from app.services.backup_service import backup_service
        from app.services.media_service import media_service
        from app.services.project_service import project_service

        original_media = self._seed()
        source_bytes = Path(original_media['path']).read_bytes()
        zip_path = backup_service.build(self.pid)
        with zipfile.ZipFile(zip_path) as archive:
            data = json.loads(archive.read('backup.json'))
        self.assertEqual(data['format'], 'sewer-annotator-backup-v1')
        self.assertEqual(len(data['excluded_frames']), 1)
        self.assertEqual(len(data['annotations']), 1)

        project_service.delete(self.pid)
        restored = backup_service.restore(zip_path)

        self.assertEqual(restored['name'], 'Inspection A')
        self.assertEqual(restored['description'], 'North interceptor')
        self.assertEqual({row['name'] for row in restored['labels']}, {row['name'] for row in self.project['labels']})
        self.assertEqual(len(restored['media']), 1)
        media = restored['media'][0]
        self.assertEqual(media['name'], 'joint.png')
        self.assertEqual(Path(media['path']).read_bytes(), source_bytes)
        self.assertEqual(media['annotation_count'], 1)
        self.assertEqual(media['excluded_count'], 1)
        frames = media_service.frames(media['id'], 0, 10)
        self.assertTrue(frames[0]['excluded'])
        self.assertEqual(frames[0]['annotation_count'], 1)
        with db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) n FROM projects').fetchone()['n'], 1)

    def test_import_keeps_existing_project_and_renames_copy(self):
        from app.services.backup_service import backup_service
        from app.services.project_service import project_service

        self._seed()
        zip_path = backup_service.build(self.pid)
        restored = backup_service.restore(zip_path)
        self.assertEqual(restored['name'], 'Inspection A (recovered)')
        self.assertNotEqual(restored['id'], self.pid)
        self.assertEqual(project_service.get(self.pid)['name'], 'Inspection A')

    def test_native_export_is_rejected_as_backup(self):
        from app.services.backup_service import backup_service

        path = Path(self.tmp.name) / 'native.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('project.json', json.dumps({'format': 'sewer-annotator-v2'}))
        with self.assertRaises(ValueError) as raised:
            backup_service.restore(path)
        self.assertIn('recovery backup', str(raised.exception).lower())


if __name__ == '__main__':
    unittest.main()
