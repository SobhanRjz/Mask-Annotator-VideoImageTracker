import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from app.utils.colors import ensure_unique, unique_color


class ColorTests(unittest.TestCase):
    def test_palette_avoids_existing(self):
        first = unique_color([])
        second = unique_color([first])
        self.assertNotEqual(first.upper(), second.upper())

    def test_ensure_unique_shifts_duplicate(self):
        taken = '#51B56D'
        shifted = ensure_unique(taken, [taken])
        self.assertNotEqual(shifted.upper(), taken.upper())
        self.assertTrue(shifted.startswith('#'))
        self.assertEqual(len(shifted), 7)


class TrackingStopSavesTests(unittest.TestCase):
    def test_cancel_saves_partial_masks(self):
        sys.modules.setdefault('sam2', MagicMock())
        sys.modules.setdefault('sam2.sam2_video_predictor', MagicMock())
        from app.services.tracking_service import TrackingService

        service = TrackingService()
        saved = {}

        class FakeMedia:
            def get(self, _mid):
                return {'frame_count': 30}

        class FakeRuntime:
            def track(self, _mid, aids, start, end, step, progress, cancel):
                results = {}
                for frame in range(start + step, end + 1, step):
                    if cancel():
                        break
                    time.sleep(0.04)
                    results[frame] = object()
                    progress(frame, 40)
                aid = aids[0] if isinstance(aids, (list, tuple)) else aids
                return [(aid, 4, results)]

        class FakeAnnotations:
            def delete_auto_range(self, *_args, **_kwargs):
                return 1

            def bulk_save(self, _mid, _lid, masks, _source, _group):
                saved['frames'] = list(masks)
                return [100 + index for index in range(len(masks))]

        with patch('app.services.tracking_service.media_service', FakeMedia()), patch(
            'app.services.tracking_service.sam2_runtime', FakeRuntime()
        ), patch('app.services.tracking_service.annotation_service', FakeAnnotations()):
            job = service.start(1, 9, 0, 20, 1, True)
            deadline = time.time() + 2
            snap = service.get(job['id'])
            while snap['status'] in ('queued', 'running') and not snap.get('current_frame'):
                if time.time() > deadline:
                    break
                time.sleep(0.02)
                snap = service.get(job['id'])
            service.cancel(job['id'])
            deadline = time.time() + 3
            snap = service.get(job['id'])
            while snap['status'] in ('queued', 'running'):
                if time.time() > deadline:
                    self.fail(f'stuck in {snap}')
                time.sleep(0.03)
                snap = service.get(job['id'])

        self.assertEqual(snap['status'], 'cancelled')
        self.assertTrue(saved.get('frames'))
        self.assertEqual(len(snap['created_annotations']), len(saved['frames']))
        self.assertLess(len(saved['frames']), 20)
        service.pool.shutdown(wait=False)

    def test_start_tracks_every_seed_annotation(self):
        sys.modules.setdefault('sam2', MagicMock())
        sys.modules.setdefault('sam2.sam2_video_predictor', MagicMock())
        from app.services.tracking_service import TrackingService

        service = TrackingService()
        seen = {}
        saved = []

        class FakeMedia:
            def get(self, _mid):
                return {'frame_count': 12}

        class FakeRuntime:
            def track(self, _mid, aids, start, end, step, progress, cancel):
                seen['aids'] = list(aids)
                progress(end, 90)
                return [(aid, 4 + index, {end: object()}) for index, aid in enumerate(aids)]

        class FakeAnnotations:
            def delete_auto_range(self, _mid, lid, _a, _b, exclude_id=None, exclude_ids=None):
                seen.setdefault('removed', []).append((lid, exclude_ids or ([exclude_id] if exclude_id is not None else [])))
                return 1

            def bulk_save(self, _mid, lid, masks, _source, group):
                saved.append({'label_id': lid, 'frames': list(masks), 'group': group})
                return [200 + len(saved)]

        with patch('app.services.tracking_service.media_service', FakeMedia()), patch(
            'app.services.tracking_service.sam2_runtime', FakeRuntime()
        ), patch('app.services.tracking_service.annotation_service', FakeAnnotations()):
            job = service.start(1, [9, 12], 0, 6, 1, True)
            deadline = time.time() + 3
            snap = service.get(job['id'])
            while snap['status'] in ('queued', 'running'):
                if time.time() > deadline:
                    self.fail(f'stuck in {snap}')
                time.sleep(0.02)
                snap = service.get(job['id'])

        self.assertEqual(snap['status'], 'completed')
        self.assertEqual(seen['aids'], [9, 12])
        self.assertEqual(snap['annotation_ids'], [9, 12])
        self.assertEqual(len(saved), 2)
        self.assertEqual([item['label_id'] for item in saved], [4, 5])
        self.assertEqual(snap['created_annotations'], [201, 202])
        self.assertEqual(len(seen['removed']), 2)
        service.pool.shutdown(wait=False)


if __name__ == '__main__':
    unittest.main()
