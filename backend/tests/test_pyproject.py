import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PyprojectTests(unittest.TestCase):
    def setUp(self):
        self.data = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))

    def test_requires_image_python(self):
        self.assertEqual(self.data['project']['requires-python'], '>=3.11,<3.13')

    def test_uv_uses_system_python(self):
        self.assertFalse(self.data['tool']['uv']['package'])
        self.assertEqual(self.data['tool']['uv']['python-preference'], 'system')

    def test_runtime_dependencies_declared(self):
        names = {
            dep.split('=')[0].split('>')[0].split('[')[0].strip().lower()
            for dep in self.data['project']['dependencies']
        }
        for required in (
            'fastapi',
            'uvicorn',
            'huggingface-hub',
            'numpy',
            'pillow',
            'pydantic',
            'pydantic-settings',
            'python-multipart',
            'opencv-python-headless',
        ):
            self.assertIn(required, names)


if __name__ == '__main__':
    unittest.main()
