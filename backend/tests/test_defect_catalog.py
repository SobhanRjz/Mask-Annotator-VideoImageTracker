import tempfile
import unittest
from pathlib import Path


class DefectCatalogTests(unittest.TestCase):
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

    def test_new_project_copies_builtin_labels_until_a_catalog_is_saved(self):
        from app.services.project_service import DEFAULT_DEFECT_LABELS, project_service

        view = project_service.defect_labels()
        self.assertFalse(view['custom'])
        self.assertEqual([(row['name'], row['color']) for row in view['labels']], list(DEFAULT_DEFECT_LABELS))
        project = project_service.create('Before catalog')
        self.assertEqual(
            [(row['name'], row['color']) for row in _defects(project['labels'])],
            list(DEFAULT_DEFECT_LABELS),
        )

    def test_saving_the_catalog_forces_every_project_onto_that_set(self):
        from app.services.project_service import project_service

        existing = project_service.create('Already open')
        saved = project_service.save_defect_labels([
            {'name': 'Root', 'color': '#112233'},
            {'name': 'Crack', 'color': '#112233'},
            {'name': '  Joint  ', 'color': ''},
        ])
        self.assertTrue(saved['custom'])
        self.assertEqual([row['name'] for row in saved['labels']], ['Root', 'Crack', 'Joint'])
        self.assertNotEqual(saved['labels'][0]['color'], saved['labels'][1]['color'])
        self.assertTrue(saved['labels'][2]['color'].startswith('#'))

        created = project_service.create('After catalog')
        expected = [(row['name'], row['color']) for row in saved['labels']]
        self.assertEqual(
            [(row['name'], row['color']) for row in _defects(created['labels'])],
            expected,
        )
        kept = project_service.get(existing['id'])
        self.assertEqual([(row['name'], row['color']) for row in _defects(kept['labels'])], expected)

    def test_removed_defect_masks_return_when_the_same_name_is_added(self):
        from app.core.db import db
        from app.services.annotation_service import annotation_service
        from app.services.project_service import project_service

        first = project_service.create('North')
        second = project_service.create('South')
        crack = next(row for row in first['labels'] if row['name'] == 'Crack')
        root = next(row for row in first['labels'] if row['name'] == 'Root')
        media_id, mask_path, annotation_id = self._mask(first['id'], crack['id'], frame=1, track='sam2-9')
        root_media, _root_mask, root_annotation = self._mask(first['id'], root['id'], frame=0)
        with db() as conn:
            conn.execute(
                'INSERT INTO healthy_frames(media_id, frame) VALUES (?,?)',
                (media_id, 1),
            )

        project_service.save_defect_labels([
            {'name': 'Root', 'color': '#225588'},
        ])
        hidden = project_service.get(first['id'])
        self.assertEqual([row['name'] for row in _defects(hidden['labels'])], ['Root'])
        self.assertEqual([row['name'] for row in _defects(project_service.get(second['id'])['labels'])], ['Root'])
        self.assertEqual(annotation_service.list(media_id), [])
        self.assertTrue(mask_path.is_file())
        self.assertEqual(annotation_service.list(root_media)[0]['id'], root_annotation)
        with db() as conn:
            parked = conn.execute('SELECT COUNT(*) n FROM archived_annotations').fetchone()['n']
        self.assertEqual(parked, 1)

        restored_catalog = project_service.save_defect_labels([
            {'name': 'Root', 'color': '#225588'},
            {'name': ' crack ', 'color': '#ABCDEF'},
        ])
        brought_back = project_service.get(first['id'])
        self.assertEqual(
            [(row['name'], row['color']) for row in _defects(brought_back['labels'])],
            [(row['name'], row['color']) for row in restored_catalog['labels']],
        )
        masks = annotation_service.list(media_id)
        self.assertEqual(len(masks), 1)
        self.assertEqual(masks[0]['label_name'], 'crack')
        self.assertEqual(masks[0]['frame'], 1)
        self.assertEqual(masks[0]['source'], 'manual')
        self.assertEqual(masks[0]['track_group'], 'sam2-9')
        self.assertEqual(masks[0]['mask_path'], str(mask_path))
        self.assertTrue(mask_path.is_file())
        self.assertEqual(mask_path.read_bytes(), b'crack-mask')
        with db() as conn:
            healthy = conn.execute(
                'SELECT COUNT(*) n FROM healthy_frames WHERE media_id=? AND frame=?',
                (media_id, 1),
            ).fetchone()['n']
            parked = conn.execute('SELECT COUNT(*) n FROM archived_annotations').fetchone()['n']
        self.assertEqual(healthy, 0)
        self.assertEqual(parked, 0)
        self.assertEqual(annotation_service.list(root_media)[0]['id'], root_annotation)

    def test_parked_masks_survive_backup_and_return_with_the_name(self):
        from pathlib import Path

        from app.services.annotation_service import annotation_service
        from app.services.backup_service import backup_service
        from app.services.project_service import project_service

        project = project_service.create('Recover me')
        crack = next(row for row in project['labels'] if row['name'] == 'Crack')
        _media_id, mask_path, _annotation_id = self._mask(project['id'], crack['id'], frame=2, track='sam2-3')
        project_service.save_defect_labels([{'name': 'Root', 'color': '#112233'}])
        zip_path = backup_service.build(project['id'])
        project_service.delete(project['id'])
        self.assertFalse(mask_path.exists())

        restored = backup_service.restore(zip_path)
        media_id = restored['media'][0]['id']
        self.assertEqual([row['name'] for row in _defects(restored['labels'])], ['Root'])
        self.assertEqual(annotation_service.list(media_id), [])

        project_service.save_defect_labels([
            {'name': 'Root', 'color': '#112233'},
            {'name': 'Crack', 'color': '#445566'},
        ])
        masks = annotation_service.list(media_id)
        self.assertEqual([(row['label_name'], row['frame'], row['track_group']) for row in masks], [('Crack', 2, 'sam2-3')])
        self.assertEqual(Path(masks[0]['mask_path']).read_bytes(), b'crack-mask')

    def _mask(self, project_id, label_id, frame, track=None):
        from app.core.db import db
        from app.core.settings import settings

        media_path = settings.media_root / str(project_id) / f'clip-{label_id}.bin'
        media_path.parent.mkdir(parents=True, exist_ok=True)
        media_path.write_bytes(b'video')
        with db() as conn:
            cur = conn.execute(
                '''INSERT INTO media(
                    project_id,name,kind,path,width,height,frame_count,fps,extract_status
                ) VALUES (?,?,?,?,?,?,?,?,?)''',
                (project_id, media_path.name, 'video', str(media_path), 8, 8, 4, 1.0, 'ready'),
            )
            media_id = cur.lastrowid
            mask_path = settings.mask_root / str(media_id) / 'mask.png'
            mask_path.parent.mkdir(parents=True, exist_ok=True)
            mask_path.write_bytes(b'crack-mask' if frame else b'root-mask')
            cur = conn.execute(
                '''INSERT INTO annotations(
                    media_id,frame,label_id,mask_path,source,track_group
                ) VALUES (?,?,?,?,?,?)''',
                (media_id, frame, label_id, str(mask_path), 'manual', track),
            )
            return media_id, mask_path, cur.lastrowid

    def test_duplicate_catalog_names_are_rejected(self):
        from app.services.project_service import project_service

        with self.assertRaises(ValueError):
            project_service.save_defect_labels([
                {'name': 'Crack', 'color': '#E45B5B'},
                {'name': ' crack ', 'color': '#51B56D'},
            ])

    def test_clearing_the_catalog_restores_builtin_labels_for_later_projects(self):
        from app.services.project_service import DEFAULT_DEFECT_LABELS, project_service

        before = project_service.create('Before clear')
        project_service.save_defect_labels([{'name': 'Only', 'color': '#ABCDEF'}])
        cleared = project_service.save_defect_labels([])
        self.assertFalse(cleared['custom'])
        self.assertEqual(
            [(row['name'], row['color']) for row in _defects(project_service.get(before['id'])['labels'])],
            list(DEFAULT_DEFECT_LABELS),
        )
        project = project_service.create('Back to defaults')
        self.assertEqual(
            [(row['name'], row['color']) for row in _defects(project['labels'])],
            list(DEFAULT_DEFECT_LABELS),
        )


def _defects(labels):
    return [row for row in labels if row.get('kind') != 'full']


if __name__ == '__main__':
    unittest.main()
