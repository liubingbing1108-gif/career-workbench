import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('init_workbench', Path(__file__).with_name('init_workbench.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FirstRunTests(unittest.TestCase):
    def test_empty_database_and_repeat_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            config = module.initialize(folder)
            profile = Path(folder) / '.runtime/profile/lab.sqlite'
            with sqlite3.connect(profile) as db:
                import json
                state = json.loads(db.execute('SELECT body FROM state').fetchone()[0])
            self.assertFalse(state['files'])
            self.assertFalse(state['sessions'])
            self.assertTrue(all(not e['values'] for e in state['entries']))
            before = profile.read_bytes(), config.read_bytes()
            with self.assertRaises(ValueError):module.initialize(folder)
            self.assertEqual(before, (profile.read_bytes(), config.read_bytes()))

    def test_partial_installation_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / '.runtime/profile').mkdir(parents=True)
            with self.assertRaises(ValueError):module.initialize(folder)
            self.assertFalse((Path(folder) / '.runtime/locations.json').exists())
