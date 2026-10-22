import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from check_project import validate, validate_diff
from project_handoff import sync


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write('package.json', {'version': '0.2.0'})
        self.write('package-lock.json', {'version': '0.2.0', 'packages': {'': {'version': '0.2.0'}}})
        for name in ['GOVERNANCE.md', 'docs/AGENT_PLAYBOOK.md', 'src.py', 'test.py', 'doc.md']:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fictional fixture\n', encoding='utf-8')
        self.cap = dict(id='demo', status='partial', summary='demo', limitations='limited',
                        acceptance='verify', depends_on=[], sources=['src.py'], tests=['test.py'], docs=['doc.md'])
        self.write_catalog([self.cap])
        self.name = '.changes/20261015T000000Z-fixture.json'
        self.item = dict(id=Path(self.name).stem, kind='test', summary='fictional', capabilities=['demo'],
                         files=['src.py'], validation='fixture only', compatibility='unchanged', release=None,
                         handoff={'task':'fixture', 'status':'complete', 'next':'none', 'docs':[], 'docs_reason':'No contract change'})
        self.write(self.name, self.item)
        sync(self.root)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def write_catalog(self, caps):
        self.write('docs/CAPABILITIES.json', {'schema_version': 1, 'capabilities': caps})

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.DEVNULL).decode().strip()

    def base(self):
        self.git('init')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('add', '.')
        self.git('commit', '-m', 'fixture base')
        return self.git('rev-parse', 'HEAD')

    def commit(self):
        self.git('add', '-A'); self.git('commit', '-m', 'fixture change')

    def add_record(self, files):
        name = '.changes/20261015T000001Z-change.json'
        self.write(name, {**self.item, 'id': Path(name).stem, 'files': files})

    def test_valid_catalog_and_record(self):
        self.assertEqual(validate(self.root)[0], [])

    def test_package_version_drift_rejected(self):
        self.write('package-lock.json', {'version': '0.1.0', 'packages': {'': {'version': '0.1.0'}}})
        self.assertTrue(validate(self.root)[0])

    def test_missing_source_rejected(self):
        (self.root / 'src.py').unlink()
        self.assertTrue(validate(self.root)[0])

    def test_duplicate_ids_and_cycles_rejected(self):
        self.write_catalog([self.cap, self.cap])
        self.assertTrue(validate(self.root)[0])
        self.write_catalog([{**self.cap, 'depends_on': ['demo']}])
        self.assertIn('Capability dependency cycle', validate(self.root)[0])

    def test_unknown_dependency_rejected(self):
        self.write_catalog([{**self.cap, 'depends_on': ['missing']}])
        self.assertTrue(validate(self.root)[0])

    def test_unsafe_path_and_unknown_capability_rejected(self):
        self.write(self.name, {**self.item, 'files': ['../private'], 'capabilities': ['missing']})
        self.assertEqual(len(validate(self.root)[0]), 2)

    def test_malformed_record_rejected(self):
        self.write(self.name, [])
        self.assertTrue(validate(self.root)[0])

    def test_diff_requires_new_record(self):
        base = self.base()
        (self.root / 'src.py').write_text('changed', encoding='utf-8')
        self.commit()
        self.assertTrue(validate_diff(self.root, base, validate(self.root)[1]))

    def test_diff_requires_all_changed_paths(self):
        base = self.base()
        (self.root / 'src.py').write_text('changed', encoding='utf-8')
        self.add_record(['doc.md']); self.commit()
        self.assertTrue(validate_diff(self.root, base, validate(self.root)[1]))

    def test_diff_covers_whole_pr_and_deletion(self):
        base = self.base()
        (self.root / 'src.py').write_text('changed', encoding='utf-8')
        self.commit()
        (self.root / 'doc.md').unlink()
        self.add_record(['src.py', 'doc.md']); self.commit()
        # Catalog reference checks separately reject deleted docs; diff coverage must still handle deletion.
        self.assertEqual(validate_diff(self.root, base, validate(self.root)[1]), [])

    def test_existing_record_cannot_be_rewritten(self):
        base = self.base()
        self.write(self.name, {**self.item, 'summary': 'rewritten'})
        self.add_record([self.name]); self.commit()
        self.assertTrue(validate_diff(self.root, base, validate(self.root)[1]))

    def test_release_assignment_allowed_once(self):
        base = self.base()
        self.write(self.name, {**self.item, 'release': '0.2.1'})
        self.add_record([self.name]); self.commit()
        self.assertEqual(validate_diff(self.root, base, validate(self.root)[1]), [])
        base = self.git('rev-parse', 'HEAD')
        self.write(self.name, {**self.item, 'release': '0.2.2'})
        other = '.changes/20261015T000002Z-release.json'
        self.write(other, {**self.item, 'id': Path(other).stem, 'files': [self.name]})
        self.commit()
        self.assertTrue(validate_diff(self.root, base, validate(self.root)[1]))

    def test_invalid_base_rejected(self):
        self.assertTrue(validate_diff(self.root, '--unsafe', {}))


if __name__ == '__main__':
    unittest.main()
