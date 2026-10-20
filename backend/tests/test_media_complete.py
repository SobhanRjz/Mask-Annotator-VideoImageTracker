import sqlite3
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image
from starlette.datastructures import UploadFile


class MediaCompleteTests(unittest.TestCase):
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
        from app.services.project_service import project_service
        self.project = project_service.create('complete-job')
        self.pid = self.project['id']

    def tearDown(self):
        from app.core.settings import settings
        settings.data_root = self._old_root
        self.conn.close()
        self.tmp.cleanup()

    def _media(self, name, kind, frames=1):
        path = Path(self.tmp.name) / name
        path.write_bytes(b'x')
        status = 'ready' if kind == 'image' or frames else 'pending'
        cur = self.conn.execute(
            '''INSERT INTO media(
                project_id,name,kind,path,width,height,frame_count,fps,extract_status
            ) VALUES (?,?,?,?,?,?,?,?,?)''',
            (self.pid, name, kind, str(path), 32, 24, frames, 1.0, status),
        )
        self.conn.commit()
        return cur.lastrowid

    def _png(self, name):
        buf = BytesIO()
        Image.new('RGB', (8, 8), 'red').save(buf, 'PNG')
        buf.seek(0)
        return UploadFile(filename=name, file=buf)

    def test_new_media_defaults_incomplete(self):
        from app.services.media_service import media_service
        mid = self._media('clip.mp4', 'video', 8)
        loaded = media_service.get(mid)
        self.assertFalse(loaded['annotation_complete'])

    def test_video_patch_flips_only_that_row(self):
        from app.services.media_service import media_service
        a = self._media('a.mp4', 'video', 4)
        b = self._media('b.mp4', 'video', 4)
        updated = media_service.set_complete(a, True)
        self.assertTrue(updated['annotation_complete'])
        self.assertFalse(media_service.get(b)['annotation_complete'])
        cleared = media_service.set_complete(a, False)
        self.assertFalse(cleared['annotation_complete'])

    def test_image_patch_via_media_is_rejected(self):
        from app.services.media_service import media_service
        mid = self._media('still.png', 'image')
        with self.assertRaises(ValueError) as caught:
            media_service.set_complete(mid, True)
        self.assertIn('stills complete', str(caught.exception))
        self.assertFalse(media_service.get(mid)['annotation_complete'])

    def test_project_stills_complete_updates_images_only(self):
        from app.services.media_service import media_service
        video = self._media('clip.mp4', 'video', 4)
        first = self._media('a.png', 'image')
        second = self._media('b.png', 'image')
        result = media_service.set_project_images_complete(self.pid, True)
        self.assertEqual(result['updated'], 2)
        self.assertTrue(result['annotation_complete'])
        self.assertTrue(media_service.get(first)['annotation_complete'])
        self.assertTrue(media_service.get(second)['annotation_complete'])
        self.assertFalse(media_service.get(video)['annotation_complete'])

    def test_new_still_upload_clears_album_complete(self):
        from app.services.media_service import media_service
        self._media('a.png', 'image')
        media_service.set_project_images_complete(self.pid, True)
        uploaded = media_service.upload(self.pid, [self._png('b.png')])
        self.assertEqual(len(uploaded), 1)
        self.assertFalse(uploaded[0]['annotation_complete'])
        from app.services.project_service import project_service
        project = project_service.get(self.pid)
        stills = [item for item in project['media'] if item['kind'] == 'image']
        self.assertEqual(len(stills), 2)
        self.assertFalse(all(item['annotation_complete'] for item in stills))

    def test_delete_project_images_leaves_videos(self):
        from app.services.media_service import media_service
        video = self._media('clip.mp4', 'video', 4)
        first = self._media('a.png', 'image')
        result = media_service.delete_project_images(self.pid)
        self.assertEqual(result['deleted'], 1)
        self.assertEqual(result['ok'], True)
        media_service.get(video)
        with self.assertRaises(KeyError):
            media_service.get(first)
        empty = media_service.delete_project_images(self.pid)
        self.assertEqual(empty['deleted'], 0)

    def test_missing_media_and_empty_stills(self):
        from app.services.media_service import media_service
        with self.assertRaises(KeyError):
            media_service.set_complete(99999, True)
        with self.assertRaises(ValueError) as caught:
            media_service.set_project_images_complete(self.pid, True)
        self.assertIn('No stills', str(caught.exception))

    def test_project_stills_are_images_ordered_by_id(self):
        from app.services.media_service import media_service
        self._media('clip.mp4', 'video', 4)
        first = self._media('a.png', 'image')
        second = self._media('b.png', 'image')
        stills = media_service.project_stills(self.pid)
        self.assertEqual([item['id'] for item in stills], [first, second])
        self.assertTrue(all(item['kind'] == 'image' for item in stills))

    def test_project_image_frames_returns_every_still_in_one_list(self):
        from app.services.media_service import media_service
        video = self._media('clip.mp4', 'video', 4)
        bare = self._media('bare.png', 'image')
        marked = self._media('marked.png', 'image')
        excluded = self._media('skip.png', 'image')
        label = self.conn.execute(
            "SELECT id, color FROM labels WHERE project_id=? AND name='Crack'",
            (self.pid,),
        ).fetchone()
        self.assertIsNotNone(label)
        self.conn.execute(
            '''INSERT INTO annotations(media_id,frame,label_id,mask_path,source)
               VALUES (?,?,?,?,?)''',
            (marked, 0, label['id'], 'mask.png', 'manual'),
        )
        self.conn.execute(
            'INSERT INTO excluded_frames(media_id,frame) VALUES (?,?)',
            (excluded, 0),
        )
        self.conn.execute(
            'INSERT INTO healthy_frames(media_id,frame) VALUES (?,?)',
            (bare, 0),
        )
        self.conn.execute(
            '''INSERT INTO annotations(media_id,frame,label_id,mask_path,source)
               VALUES (?,?,?,?,?)''',
            (video, 0, label['id'], 'video-mask.png', 'manual'),
        )
        self.conn.commit()

        rows = media_service.project_image_frames(self.pid)

        self.assertEqual([row['media_id'] for row in rows], [bare, marked, excluded])
        by_id = {row['media_id']: row for row in rows}
        self.assertEqual(by_id[bare]['frame'], 0)
        self.assertEqual(by_id[bare]['annotation_count'], 0)
        self.assertTrue(by_id[bare]['healthy'])
        self.assertEqual(by_id[bare]['labels'], [])
        self.assertEqual(by_id[marked]['annotation_count'], 1)
        self.assertEqual(by_id[marked]['labels'][0]['name'], 'Crack')
        self.assertEqual(by_id[marked]['labels'][0]['color'], label['color'])
        self.assertEqual(by_id[marked]['labels'][0]['source'], 'manual')
        self.assertGreater(by_id[marked]['labels'][0]['annotation_id'], 0)
        self.assertFalse(by_id[marked]['excluded'])
        self.assertTrue(by_id[excluded]['excluded'])
        self.assertEqual(media_service.project_image_frames(self.pid + 1), [])


if __name__ == '__main__':
    unittest.main()
