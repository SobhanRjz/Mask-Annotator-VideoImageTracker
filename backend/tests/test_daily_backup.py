import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from io import BytesIO
from PIL import Image
from starlette.datastructures import UploadFile


class DailyBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from app.core.settings import settings
        self._old_root = settings.data_root
        settings.data_root = Path(self.tmp.name)
        from app.core.db import initialize_db
        initialize_db()
        from app.services.project_service import project_service
        self.project = project_service.create('Daily job')
        self.pid = self.project['id']

    def tearDown(self):
        from app.core.settings import settings
        settings.data_root = self._old_root
        self.tmp.cleanup()

    def _png(self, name='frame.png'):
        buf = BytesIO()
        Image.new('RGB', (8, 8), 'navy').save(buf, 'PNG')
        buf.seek(0)
        return UploadFile(filename=name, file=buf)

    def _mask(self):
        mask = np.zeros((8, 8), dtype=bool)
        mask[1:6, 1:6] = True
        return mask

    def _annotate(self):
        from app.services.annotation_service import annotation_service
        from app.services.media_service import media_service
        media = media_service.upload(self.pid, [self._png()])[0]
        return annotation_service.save(
            media['id'], 0, self.project['labels'][0]['id'], self._mask(), 'manual'
        )

    def test_no_annotations_writes_nothing(self):
        from app.services.daily_backup_service import daily_backup_service
        result = daily_backup_service.tick(now=datetime(2026, 9, 30, tzinfo=timezone.utc))
        self.assertEqual(result['saved'], 0)
        self.assertTrue(result['skipped'])
        self.assertFalse((Path(self.tmp.name) / 'backups' / '2026-09-30').exists())

    def test_new_annotations_are_copied_into_that_days_folder(self):
        from app.services.daily_backup_service import daily_backup_service
        ann = self._annotate()
        result = daily_backup_service.tick(now=datetime(2026, 9, 30, 12, tzinfo=timezone.utc))
        self.assertEqual(result['saved'], 1)
        folder = Path(self.tmp.name) / 'backups' / '2026-09-30'
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['date'], '2026-09-30')
        self.assertEqual(len(manifest['items']), 1)
        self.assertEqual(manifest['items'][0]['id'], ann['id'])
        self.assertTrue((folder / 'masks' / f"{ann['id']}.png").is_file())

    def test_second_tick_without_new_work_does_not_rewrite(self):
        from app.services.daily_backup_service import daily_backup_service
        self._annotate()
        first = daily_backup_service.tick(now=datetime(2026, 9, 30, 12, tzinfo=timezone.utc))
        second = daily_backup_service.tick(now=datetime(2026, 9, 30, 13, tzinfo=timezone.utc))
        self.assertEqual(first['saved'], 1)
        self.assertEqual(second['saved'], 0)
        self.assertTrue(second['skipped'])
        folder = Path(self.tmp.name) / 'backups' / '2026-09-30'
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['items']), 1)

    def test_later_annotations_append_only_the_new_mask(self):
        from app.services.daily_backup_service import daily_backup_service
        first = self._annotate()
        daily_backup_service.tick(now=datetime(2026, 9, 30, 10, tzinfo=timezone.utc))
        second = self._annotate()
        result = daily_backup_service.tick(now=datetime(2026, 9, 30, 18, tzinfo=timezone.utc))
        self.assertEqual(result['saved'], 1)
        folder = Path(self.tmp.name) / 'backups' / '2026-09-30'
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        ids = [item['id'] for item in manifest['items']]
        self.assertEqual(ids, [first['id'], second['id']])
        self.assertTrue((folder / 'masks' / f"{second['id']}.png").is_file())


class FrontendCacheHeadersTests(unittest.TestCase):
    def test_nginx_does_not_cache_the_html_shell(self):
        nginx = Path(__file__).resolve().parents[2] / 'frontend' / 'nginx.conf'
        text = nginx.read_text(encoding='utf-8')
        self.assertIn('no-store', text)
        self.assertIn('index.html', text)


if __name__ == '__main__':
    unittest.main()
