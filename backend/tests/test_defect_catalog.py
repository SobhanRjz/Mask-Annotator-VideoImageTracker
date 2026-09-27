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
            [(row['name'], row['color']) for row in project['labels']],
            list(DEFAULT_DEFECT_LABELS),
        )

    def test_new_project_copies_the_saved_catalog_and_keeps_older_projects(self):
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
        self.assertEqual(
            [(row['name'], row['color']) for row in created['labels']],
            [(row['name'], row['color']) for row in saved['labels']],
        )
        kept = project_service.get(existing['id'])
        self.assertEqual([row['name'] for row in kept['labels']], [row['name'] for row in existing['labels']])

    def test_duplicate_catalog_names_are_rejected(self):
        from app.services.project_service import project_service

        with self.assertRaises(ValueError):
            project_service.save_defect_labels([
                {'name': 'Crack', 'color': '#E45B5B'},
                {'name': ' crack ', 'color': '#51B56D'},
            ])

    def test_clearing_the_catalog_restores_builtin_labels_for_later_projects(self):
        from app.services.project_service import DEFAULT_DEFECT_LABELS, project_service

        project_service.save_defect_labels([{'name': 'Only', 'color': '#ABCDEF'}])
        cleared = project_service.save_defect_labels([])
        self.assertFalse(cleared['custom'])
        project = project_service.create('Back to defaults')
        self.assertEqual(
            [(row['name'], row['color']) for row in project['labels']],
            list(DEFAULT_DEFECT_LABELS),
        )


if __name__ == '__main__':
    unittest.main()
