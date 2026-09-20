import sqlite3
import tempfile
import unittest
from pathlib import Path


class ProjectNameTests(unittest.TestCase):
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

    def test_create_stores_unique_slug_from_name(self):
        from app.services.project_service import project_service
        project = project_service.create('Site A – North interceptor', 'CCTV 12 Sep')
        self.assertEqual(project['slug'], 'site-a-north-interceptor')
        listed = project_service.list()
        self.assertEqual(listed[0]['slug'], 'site-a-north-interceptor')
        loaded = project_service.get('site-a-north-interceptor')
        self.assertEqual(loaded['id'], project['id'])
        self.assertEqual(project_service.resolve_id(str(project['id'])), project['id'])

    def test_duplicate_names_are_rejected(self):
        from app.services.project_service import project_service
        project_service.create('Riverside trunk')
        with self.assertRaises(ValueError) as raised:
            project_service.create('riverside trunk')
        self.assertIn('already exists', str(raised.exception))

    def test_migrate_backfills_slug_on_existing_rows(self):
        from app.core.db import initialize_db
        from app.core.settings import settings
        from app.services.project_service import project_service
        conn = sqlite3.connect(settings.db_path)
        conn.execute("INSERT INTO projects(name,description) VALUES ('Legacy job','')")
        conn.commit()
        conn.close()
        initialize_db()
        loaded = project_service.get('legacy-job')
        self.assertEqual(loaded['name'], 'Legacy job')

    def test_slug_collision_from_different_names_gets_suffix(self):
        from app.services.project_service import project_service
        first = project_service.create('Site A')
        second = project_service.create('Site-A')
        self.assertEqual(first['slug'], 'site-a')
        self.assertEqual(second['slug'], 'site-a-2')
        self.assertEqual(project_service.get('site-a-2')['id'], second['id'])


if __name__ == '__main__':
    unittest.main()
