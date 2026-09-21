import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault('torch', MagicMock())
sys.modules.setdefault('sam2', MagicMock())
sys.modules.setdefault('sam2.sam2_video_predictor', MagicMock())

from app.services.track_settings import (
    DEFAULT_PATCH,
    MAX_PATCH,
    MIN_PATCH,
    parse_patch,
    track_windows,
)


class TrackWindowsTests(unittest.TestCase):
    def test_one_window_when_patch_covers_the_range(self):
        self.assertEqual(track_windows(0, 10, 16), [(0, 10)])
        self.assertEqual(track_windows(10, 0, 16), [(10, 0)])

    def test_forward_windows_share_the_boundary_frame(self):
        self.assertEqual(track_windows(0, 10, 4), [(0, 3), (3, 6), (6, 9), (9, 10)])

    def test_reverse_windows_share_the_boundary_frame(self):
        self.assertEqual(track_windows(10, 0, 4), [(10, 7), (7, 4), (4, 1), (1, 0)])

    def test_patch_of_two_steps_one_frame_at_a_time(self):
        self.assertEqual(track_windows(5, 8, 2), [(5, 6), (6, 7), (7, 8)])

    def test_same_start_and_end_is_empty(self):
        self.assertEqual(track_windows(4, 4, 8), [])


class ParsePatchTests(unittest.TestCase):
    def test_default_and_clamp(self):
        self.assertEqual(parse_patch(None), DEFAULT_PATCH)
        self.assertEqual(parse_patch(''), DEFAULT_PATCH)
        self.assertEqual(parse_patch('32'), 32)
        self.assertEqual(parse_patch(1), MIN_PATCH)
        self.assertEqual(parse_patch(999), MAX_PATCH)
        with self.assertRaises(ValueError):
            parse_patch('nope')


class TrackingSettingsApiTests(unittest.TestCase):
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

    def test_roundtrip_patch_size(self):
        from app.services.track_settings import get_patch, set_patch

        self.assertEqual(get_patch(), DEFAULT_PATCH)
        self.assertEqual(set_patch(48), 48)
        self.assertEqual(get_patch(), 48)

    def test_settings_route_saves_patch_size(self):
        from app.api.routes.settings import TrackingIn, tracking_save, tracking_status

        report = tracking_status()
        self.assertEqual(report['track_patch_size'], DEFAULT_PATCH)
        saved = tracking_save(TrackingIn(track_patch_size=24))
        self.assertEqual(saved['track_patch_size'], 24)
        self.assertEqual(tracking_status()['track_patch_size'], 24)
