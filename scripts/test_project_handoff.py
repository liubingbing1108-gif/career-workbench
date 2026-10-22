import json
from pathlib import Path
import tempfile
import unittest

from check_project import validate
from project_handoff import begin, record, status, sync, index_errors, release_errors, locked, snapshot


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name in ['GOVERNANCE.md', 'docs/AGENT_PLAYBOOK.md', 'src.py', 'test.py', 'doc.md']:
            self.write(name, 'fixture')
        self.json('package.json', {'version':'0.2.0'})
        self.json('package-lock.json', {'version':'0.2.0','packages':{'':{'version':'0.2.0'}}})
        self.json('docs/CAPABILITIES.json', {'schema_version':1,'capabilities':[
            dict(id='demo',status='partial',summary='fixture',limitations='limited',acceptance='test',
                 sources=['src.py'],tests=['test.py'],docs=['doc.md'],depends_on=[])]})
        self.payload = dict(kind='test',summary='Fictional update',capabilities=['demo'],
                            validation='Fixture checks only',compatibility='Unchanged',
                            handoff=dict(task='one',status='complete',next='None',docs=[],docs_reason='No normative change'))
        seed = {**self.payload,'id':'20261016T000000Z-seed','files':['src.py'],'release':None}
        self.json('.changes/' + seed['id'] + '.json', seed)
        sync(self.root)

    def write(self, name, text):
        p=self.root/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding='utf-8')

    def json(self, name, value):
        self.write(name,json.dumps(value))

    def test_record_detects_edits_additions_and_deletions_and_syncs(self):
        self.write('work/a.py','old'); self.write('work/b.py','old')
        begin(self.root,'one',['work'])
        self.write('work/a.py','new'); (self.root/'work/b.py').unlink(); self.write('work/c.py','new')
        self.assertEqual(len(status(self.root)[0]['unrecorded']),3)
        entry=record(self.root,'one',self.payload)
        self.assertEqual(entry['files'],['work/a.py','work/b.py','work/c.py'])
        self.assertEqual(index_errors(self.root),[])
        self.assertEqual(validate(self.root)[0],[])
        self.assertEqual(release_errors(self.root),[])

    def test_overlapping_claim_rejected_and_independent_allowed(self):
        begin(self.root,'one',['work'])
        with self.assertRaisesRegex(ValueError,'overlaps'): begin(self.root,'two',['work/file.py'])
        begin(self.root,'three',['other.py'])

    def test_writer_lock_cannot_be_stolen(self):
        with locked(self.root):
            with self.assertRaisesRegex(ValueError,'writer'): begin(self.root,'one',['src.py'])

    def test_invalid_metadata_preserves_active_state_and_old_records(self):
        begin(self.root,'one',['src.py']); self.write('src.py','changed')
        before=list((self.root/'.changes').glob('*.json'))
        with self.assertRaises(ValueError): record(self.root,'one',{**self.payload,'capabilities':['missing']})
        self.assertEqual(list((self.root/'.changes').glob('*.json')),before)
        self.assertTrue(status(self.root)[0]['active'])
        self.assertEqual(status(self.root)[0]['unrecorded'],['src.py'])

    def test_stale_index_fails_existing_check(self):
        self.write('docs/PROJECT_ACTIVITY.md','stale')
        self.assertTrue(validate(self.root)[0]); sync(self.root)
        self.assertEqual(validate(self.root)[0],[])

    def test_partial_then_final_status_records_without_fake_source_edit(self):
        begin(self.root,'one',['src.py']); self.write('src.py','changed')
        partial={**self.payload,'handoff':{**self.payload['handoff'],'status':'in_progress','next':'Finish validation'}}
        self.assertTrue(release_errors(self.root))
        first=record(self.root,'one',partial)
        self.assertFalse(release_errors(self.root))
        self.assertTrue(status(self.root)[0]['active'])
        second=record(self.root,'one',self.payload)
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(second['files'],['docs/PROJECT_ACTIVITY.md'])
        self.assertFalse(status(self.root)[0]['active'])
        with self.assertRaises(ValueError):record(self.root,'one',self.payload)

    def test_completed_claim_does_not_accuse_later_task(self):
        begin(self.root,'one',['src.py']); record(self.root,'one',self.payload)
        begin(self.root,'two',['src.py']); self.write('src.py','next task')
        self.assertEqual(status(self.root)[0]['unrecorded'],[])
        self.assertEqual(status(self.root)[1]['unrecorded'],['src.py'])

    def test_forbidden_scopes_and_symlinks(self):
        for scope in ['../outside','.runtime','config/local.json','.env','/tmp','.', 'work/../src.py']:
            with self.subTest(scope=scope),self.assertRaises(ValueError):begin(self.root,'one',[scope])
        self.write('.runtime/private.json','private')
        self.assertEqual(snapshot(self.root,['.runtime']),{})
        try:(self.root/'link.py').symlink_to(self.root/'src.py')
        except OSError:return
        with self.assertRaises(ValueError):begin(self.root,'one',['link.py'])

    def test_private_overlay_and_deletion_mapping_no_private_names_exported(self):
        overlay=self.root/'release/public';overlay.mkdir(parents=True)
        for name in ['GOVERNANCE.md','docs','.changes']:
            (self.root/name).rename(overlay/name)
        self.write('docs/private-handoff.md','private engineering note')
        self.write('scripts/start_workbench.py','fixture source')
        # The private exporter is available only in the author's tree, not in public clones.
        if not (Path(__file__).parent/'export_source.py').exists():
            self.skipTest('Private exporter is deliberately absent from public clone')
        begin(self.root,'one',['docs/private-handoff.md','scripts/start_workbench.py'])
        self.write('docs/private-handoff.md','new note');(self.root/'scripts/start_workbench.py').unlink()
        entry=record(self.root,'one',self.payload)
        self.assertEqual(entry['files'],['scripts/start_workbench.py'])
        self.assertNotIn('private-handoff',json.dumps(entry))
        receipt=json.loads((self.root/'.project-local/tasks/one.json').read_text())
        self.assertIn('docs/private-handoff.md',receipt['records'][0]['local_files'])

    def test_new_fragment_requires_handoff_metadata(self):
        seed=json.loads(next((self.root/'.changes').glob('*.json')).read_text())
        del seed['handoff'];self.json('.changes/'+seed['id']+'.json',seed)
        self.assertTrue(any('handoff' in e for e in validate(self.root)[0]))

    def test_malformed_status_is_rejected_without_partial_record(self):
        begin(self.root,'one',['src.py'])
        with self.assertRaises(ValueError):
            record(self.root,'one',{**self.payload,'handoff':{**self.payload['handoff'],'status':[]}})
        self.assertEqual(len(list((self.root/'.changes').glob('*.json'))),1)


if __name__=='__main__':unittest.main()
