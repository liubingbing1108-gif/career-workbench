"""Offline migration/rollback verification with synthetic original bytes."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototypes/profile-lab'))
from lab import Lab
from migrate_profile_refactor import rehearsal,review,apply,rollback,blob_digest,read_state,database,database_digest
from profile_migration import state_hash


class ProfileMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        lab=Lab(self.root/'source')
        with lab.db:
            lab.db.execute('INSERT INTO files VALUES (?,?)',('fiction-original',b'fictional original bytes\x00\xff'))
        self.original=lab.state();lab.db.close()
        self.source=self.root/'source/lab.sqlite';self.output=self.root/'rehearsal'
    def tearDown(self):self.temp.cleanup()
    def state(self):
        with database(self.source) as db:return read_state(db)
    def test_rehearsal_does_not_mutate_source_and_copies_originals(self):
        report=rehearsal(self.source,self.output,timestamp=1000)
        self.assertEqual(self.state(),self.original)
        with database(self.output/'candidate.sqlite') as candidate,database(self.source) as original:
            self.assertEqual(blob_digest(candidate),blob_digest(original))
            self.assertEqual(candidate.execute('SELECT body FROM files').fetchone()[0],b'fictional original bytes\x00\xff')
        self.assertEqual(report['status'],'rehearsed')
    def test_switch_replay_and_rollback(self):
        rehearsal(self.source,self.output,timestamp=1000)
        self.assertEqual(apply(self.output)['status'],'applied')
        self.assertEqual(self.state()['profile_contract'],30)
        self.assertEqual(apply(self.output)['status'],'already_applied')
        self.assertEqual(rollback(self.output)['status'],'rolled_back')
        self.assertEqual(self.state(),self.original)
        self.assertEqual(rollback(self.output)['status'],'already_rolled_back')
    def test_reject_source_change_after_rehearsal(self):
        rehearsal(self.source,self.output,timestamp=1000)
        with database(self.source) as db:
            state=read_state(db);state['fictional_new_write']='preserve me';db.execute('UPDATE state SET body=?',(json.dumps(state),))
        with self.assertRaises(ValueError):apply(self.output)
        self.assertEqual(self.state()['fictional_new_write'],'preserve me')
    def test_rollback_preserves_writes_after_switch(self):
        rehearsal(self.source,self.output,timestamp=1000);apply(self.output)
        with database(self.source) as db:
            state=read_state(db);state['fictional_new_write']='preserve me';db.execute('UPDATE state SET body=?',(json.dumps(state),))
        with self.assertRaises(ValueError):rollback(self.output)
        self.assertEqual(self.state()['fictional_new_write'],'preserve me')
    def test_reject_candidate_or_blob_tampering(self):
        rehearsal(self.source,self.output,timestamp=1000)
        with database(self.output/'candidate.sqlite') as db:db.execute('UPDATE files SET body=?',(b'changed',))
        with self.assertRaises(ValueError):apply(self.output)
        self.assertEqual(self.state(),self.original)
    def test_rehearsal_does_not_overwrite(self):
        rehearsal(self.source,self.output,timestamp=1000)
        with self.assertRaises(ValueError):rehearsal(self.source,self.output,timestamp=1000)
    def test_replay_checks_original_bytes_even_when_state_is_unchanged(self):
        rehearsal(self.source,self.output,timestamp=1000);apply(self.output)
        with database(self.source) as db:db.execute('UPDATE files SET body=?',(b'new original',))
        with self.assertRaises(ValueError):apply(self.output)
        with self.assertRaises(ValueError):rollback(self.output)
    def test_backup_original_tampering_blocks_rollback(self):
        rehearsal(self.source,self.output,timestamp=1000);apply(self.output)
        with database(self.output/'backup.sqlite') as db:db.execute('UPDATE files SET body=?',(b'corrupt backup',))
        with self.assertRaises(ValueError):rollback(self.output)
    def test_missing_or_inconsistent_original_metadata_blocks_rehearsal(self):
        with database(self.source) as db:
            state=read_state(db);state['files'].append(dict(id='absent',size=1));db.execute('UPDATE state SET body=?',(json.dumps(state),))
        with self.assertRaises(ValueError):rehearsal(self.source,self.output,timestamp=1000)

    def test_review_is_hash_bound_atomic_and_replayable(self):
        r=rehearsal(self.source,self.output,timestamp=1000)
        with database(self.output/'candidate.sqlite') as db:s=read_state(db)
        eid=next(e['id'] for e in s['entries'] if e['category']=='basic')
        command=dict(operation='record',data=dict(entry_id=eid,values={'name':'确认示例姓名'}))
        data=dict(request_id='review',confirmed=True,expected_hash=r['candidate_hash'],commands=[command])
        with self.assertRaises(ValueError):review(self.output,{**data,'expected_hash':'stale'})
        with self.assertRaises(ValueError):review(self.output,{**data,'commands':[command,dict(operation='raw-state',data={})]})
        with database(self.output/'candidate.sqlite') as db:self.assertEqual(read_state(db),s)
        self.assertEqual(review(self.output,data)['status'],'reviewed')
        self.assertEqual(review(self.output,data)['status'],'already_reviewed')
        self.assertEqual(self.state(),self.original)
        apply(self.output);self.assertEqual(next(e for e in self.state()['entries'] if e['id']==eid)['values']['name'],'确认示例姓名')
        rollback(self.output);self.assertEqual(self.state(),self.original)

    def test_review_normalizes_startup_and_keeps_restart_rollback_stable(self):
        r=rehearsal(self.source,self.output,timestamp=1000)
        review(self.output,dict(confirmed=True,request_id='normalize',expected_hash=r['candidate_hash'],commands=[dict(operation='normalize_startup')]))
        apply(self.output)
        expected=self.state()
        lab=Lab(self.source.parent);actual=lab.state();lab.db.close()
        self.assertEqual(actual,expected)
        rollback(self.output);self.assertEqual(self.state(),self.original)

    def test_discard_legacy_answer_retains_evidence_and_rejects_current(self):
        r=rehearsal(self.source,self.output,timestamp=1000)
        with database(self.output/'candidate.sqlite') as db:state=read_state(db)
        eid=next(e['id'] for e in state['entries'] if e['category']=='basic')
        def run(request,commands):
            report=json.loads((self.output/'report.json').read_text())
            return review(self.output,dict(confirmed=True,request_id=request,expected_hash=report['candidate_hash'],commands=commands))
        run('first',[dict(operation='record',data=dict(entry_id=eid,values={'name':'Fiction Sample'}))])
        with database(self.output/'candidate.sqlite') as db:
            s=read_state(db);entry=next(e for e in s['entries'] if e['id']==eid);vid=entry['default_versions']['name']
        with self.assertRaises(ValueError):run('current',[dict(operation='discard_legacy_answer',data=dict(version_id=vid))])
        run('second',[dict(operation='record',data=dict(entry_id=eid,values={'name':'Fiction Confirmed'}))])
        run('discard',[dict(operation='discard_legacy_answer',data=dict(version_id=vid))])
        with database(self.output/'candidate.sqlite') as db:
            s=read_state(db);old=next(v for v in s['answer_versions'] if v['id']==vid)
            self.assertTrue(old['profile_deleted']);self.assertEqual(old['content'],'Fiction Sample')
            self.assertEqual(next(e for e in s['entries'] if e['id']==eid)['values']['name'],'Fiction Confirmed')

    def test_management_snapshot_checks_references_and_preserves_all_tables(self):
        management=self.root/'management.sqlite'
        with database(management) as db:
            db.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,payload TEXT)');db.execute('INSERT INTO jobs VALUES (?,?)',('fiction-job','fictional'))
            original=database_digest(db)
        with database(self.source) as db:
            s=read_state(db);s['sessions'].append(dict(id='fiction-session',management_job_id='fiction-job'));db.execute('UPDATE state SET body=?',(json.dumps(s),))
        r=rehearsal(self.source,self.output,timestamp=1000,management_source=management)
        self.assertEqual(r['management']['sha256'],original)
        apply(self.output);rollback(self.output)
        with database(management) as db:self.assertEqual(database_digest(db),original)
        with database(management) as db:db.execute('UPDATE jobs SET payload=?',('later edit',))
        with self.assertRaises(ValueError):apply(self.output)

    def test_missing_management_job_and_active_execution_block_switch(self):
        management=self.root/'management.sqlite'
        with database(management) as db:db.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY)')
        with database(self.source) as db:
            s=read_state(db);s['sessions'].append(dict(id='fiction-session',management_job_id='missing'));db.execute('UPDATE state SET body=?',(json.dumps(s),))
        with self.assertRaises(ValueError):rehearsal(self.source,self.output,timestamp=1000,management_source=management)
        with database(self.source) as db:
            s=read_state(db);s['sessions'][0].update(preparation={'execution':{'status':'running'}});db.execute('UPDATE state SET body=?',(json.dumps(s),))
        second=self.root/'active-rehearsal';rehearsal(self.source,second,timestamp=1000)
        with self.assertRaises(ValueError):apply(second)


if __name__=='__main__':unittest.main()
