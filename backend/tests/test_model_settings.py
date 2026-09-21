import sys
import time
import unittest
from unittest.mock import MagicMock

from app.services.model_catalog import CATALOG, catalog_entry, key_for_model_id

sys.modules.setdefault('torch', MagicMock())
sys.modules.setdefault('sam2', MagicMock())
sys.modules.setdefault('sam2.sam2_video_predictor', MagicMock())


class CatalogTests(unittest.TestCase):
    def test_four_sam21_ids(self):
        self.assertEqual(
            {key: item['model_id'] for key, item in CATALOG.items()},
            {
                'tiny': 'facebook/sam2.1-hiera-tiny',
                'small': 'facebook/sam2.1-hiera-small',
                'balanced': 'facebook/sam2.1-hiera-base-plus',
                'large': 'facebook/sam2.1-hiera-large',
            },
        )

    def test_unknown_key_rejected(self):
        with self.assertRaises(ValueError):
            catalog_entry('latest')

    def test_env_id_maps_to_key(self):
        self.assertEqual(key_for_model_id('facebook/sam2.1-hiera-base-plus'), 'balanced')
        self.assertEqual(key_for_model_id('unknown/model'), 'small')


class SettingStoreTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from app.core.settings import settings
        self.tmp = tempfile.TemporaryDirectory()
        self._old_root = settings.data_root
        settings.data_root = Path(self.tmp.name)
        from app.core.db import initialize_db
        initialize_db()

    def tearDown(self):
        from app.core.settings import settings
        settings.data_root = self._old_root
        self.tmp.cleanup()

    def test_sam_model_roundtrip(self):
        from app.core.db import get_setting, set_setting
        self.assertIsNone(get_setting('sam_model'))
        set_setting('sam_model', 'large')
        self.assertEqual(get_setting('sam_model'), 'large')


class FakeRuntime:
    def __init__(self, key='small'):
        self.predictor = object()
        self.model_key = key
        self.model_id = catalog_entry(key)['model_id']
        self.loading = False
        self.load_error = None
        self.sessions = {}
        self.loads = []
        self.fail_with = None
        self.restored = []

    def status(self):
        return {
            'ready': self.predictor is not None,
            'loading': self.loading,
            'error': self.load_error,
            'model': self.model_id,
            'key': self.model_key,
        }

    def close_all_sessions(self):
        self.sessions.clear()

    def swap(self, key, model_id, progress=None):
        previous_key = self.model_key
        previous_id = self.model_id
        self.close_all_sessions()
        if progress:
            progress(90)
        if self.fail_with:
            self.restored.append(previous_id)
            self.model_key = previous_key
            self.model_id = previous_id
            raise RuntimeError(self.fail_with)
        self.loads.append(model_id)
        self.model_key = key
        self.model_id = model_id
        self.predictor = object()
        if progress:
            progress(100)


class FakeTracking:
    def __init__(self):
        self.busy = False

    def is_busy(self):
        return self.busy


class ModelServiceTests(unittest.TestCase):
    def setUp(self):
        from app.services.model_service import ModelService

        self.runtime = FakeRuntime()
        self.tracking = FakeTracking()
        self.cached = {'small': True, 'tiny': False, 'balanced': False, 'large': True}
        self.downloads = []
        self.saved = {}

        def ensure(key, progress=None):
            if self.cached.get(key):
                if progress:
                    progress(1, 1)
                return f'/cache/{key}.pt'
            self.downloads.append(key)
            if progress:
                progress(50, 100)
                progress(100, 100)
            return f'/dl/{key}.pt'

        self.service = ModelService(
            runtime=self.runtime,
            tracking=self.tracking,
            ensure_checkpoint=ensure,
            is_cached=lambda key: bool(self.cached.get(key)),
            load_setting=lambda: self.saved.get('sam_model'),
            save_setting=lambda key: self.saved.__setitem__('sam_model', key),
        )

    def tearDown(self):
        self.service.pool.shutdown(wait=False)

    def _wait(self, job_id, timeout=2):
        deadline = time.time() + timeout
        while time.time() < deadline:
            snap = self.service.get(job_id)
            if snap['status'] in ('completed', 'failed'):
                return snap
            time.sleep(0.02)
        return self.service.get(job_id)

    def test_cached_checkpoint_skips_download(self):
        job = self.service.start('large')
        snap = self._wait(job['id'])
        self.assertEqual(snap['status'], 'completed')
        self.assertEqual(self.downloads, [])
        self.assertEqual(self.runtime.loads, ['facebook/sam2.1-hiera-large'])
        self.assertEqual(self.saved.get('sam_model'), 'large')

    def test_missing_checkpoint_downloads_then_loads(self):
        job = self.service.start('tiny')
        snap = self._wait(job['id'])
        self.assertEqual(snap['status'], 'completed')
        self.assertEqual(self.downloads, ['tiny'])
        self.assertEqual(self.runtime.loads, ['facebook/sam2.1-hiera-tiny'])
        self.assertGreaterEqual(snap['progress'], 100)
        self.assertEqual(self.saved.get('sam_model'), 'tiny')

    def test_failed_load_keeps_previous_and_does_not_persist(self):
        self.runtime.fail_with = 'CUDA out of memory'
        job = self.service.start('large')
        snap = self._wait(job['id'])
        self.assertEqual(snap['status'], 'failed')
        self.assertIn('CUDA', snap['error'])
        self.assertEqual(self.runtime.model_key, 'small')
        self.assertEqual(self.runtime.restored, ['facebook/sam2.1-hiera-small'])
        self.assertNotIn('sam_model', self.saved)

    def test_switch_waits_while_tracking_runs(self):
        self.tracking.busy = True

        def release():
            time.sleep(0.12)
            self.tracking.busy = False

        import threading
        threading.Thread(target=release, daemon=True).start()
        job = self.service.start('large')
        snap = self._wait(job['id'])
        self.assertEqual(snap['status'], 'completed')
        self.assertEqual(self.runtime.loads, ['facebook/sam2.1-hiera-large'])

    def test_second_switch_is_busy(self):
        from app.services.model_service import ModelSwitchBusy

        self.tracking.busy = True
        first = self.service.start('large')
        with self.assertRaises(ModelSwitchBusy):
            self.service.start('tiny')
        self.tracking.busy = False
        snap = self._wait(first['id'])
        self.assertEqual(snap['status'], 'completed')

    def test_status_lists_cache_flags(self):
        report = self.service.status()
        by_key = {item['key']: item for item in report['models']}
        self.assertTrue(by_key['small']['cached'])
        self.assertFalse(by_key['tiny']['cached'])
        self.assertEqual(report['active'], 'small')
        self.assertEqual(len(report['models']), 4)
