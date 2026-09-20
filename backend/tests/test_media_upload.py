import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
from starlette.datastructures import UploadFile


class MediaUploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from app.core.settings import settings
        self._old_root = settings.data_root
        settings.data_root = Path(self.tmp.name)
        from app.core.db import initialize_db
        initialize_db()
        from app.services.project_service import project_service
        self.project = project_service.create('upload-job')
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

    def test_duplicate_image_reuses_existing_media_and_annotations(self):
        from app.services.annotation_service import annotation_service
        from app.services.media_service import media_service
        from app.services.project_service import project_service

        first = media_service.upload(self.pid, [self._png('pipe.png')])
        self.assertEqual(len(first), 1)
        self.assertFalse(first[0].get('reused'))
        mask = np.zeros((8, 8), dtype=bool)
        mask[1:4, 1:4] = True
        annotation_service.save(first[0]['id'], 0, self.project['labels'][0]['id'], mask)

        second = media_service.upload(self.pid, [self._png('pipe-copy.png')])
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]['id'], first[0]['id'])
        self.assertTrue(second[0]['reused'])
        self.assertEqual(second[0]['annotation_count'], 1)
        self.assertEqual(second[0]['name'], 'pipe.png')

        project = project_service.get(self.pid)
        stills = [item for item in project['media'] if item['kind'] == 'image']
        self.assertEqual(len(stills), 1)
        self.assertEqual(stills[0]['annotation_count'], 1)

    def test_different_images_stay_separate(self):
        from app.services.media_service import media_service

        uploaded = media_service.upload(
            self.pid,
            [self._png('a.png', 'red'), self._png('b.png', 'blue')],
        )
        self.assertEqual(len(uploaded), 2)
        self.assertNotEqual(uploaded[0]['id'], uploaded[1]['id'])
        self.assertFalse(any(item.get('reused') for item in uploaded))

    def test_same_bytes_in_one_batch_reuse_the_first(self):
        from app.services.media_service import media_service

        uploaded = media_service.upload(
            self.pid,
            [self._png('one.png'), self._png('two.png')],
        )
        self.assertEqual(uploaded[0]['id'], uploaded[1]['id'])
        self.assertFalse(uploaded[0].get('reused'))
        self.assertTrue(uploaded[1]['reused'])


if __name__ == '__main__':
    unittest.main()
