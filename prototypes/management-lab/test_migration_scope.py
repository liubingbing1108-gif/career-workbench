import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from feishu import candidates
from migration import correct_scope, migrate, MIGRATION_ID
from store import Store, Conflict
from test_http import fixture


class MigrationScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.profile=Path(self.tmp.name)/'lab.sqlite'
        self.snap=fixture()
        self.snap['tables'].append({'kind':'opportunities','name':'虚构机会池','count':4,'records':[
            {'record_id':'pool-'+str(i),'fields':{'公司':'虚构公司','岗位名称':'虚构岗位',
             '投递链接':'https://example.com/job','投递状态':[status]}}
            for i,status in enumerate(('未判断','高优投递','不投递','已投递'))]})
    def tearDown(self):self.tmp.cleanup()
    def original_import(self):
        with patch('migration.selected_candidates',side_effect=candidates):
            result=migrate(self.store,self.snap)
        self.ids=result['ids']
        state={'shared':['虚构共享资料'],'sessions':[
            {'id':'history','management_job_id':self.ids[0]},
            {'id':'accidental-test','management_job_id':self.ids[2]},
            {'id':'independent'}]}
        with sqlite3.connect(self.profile) as db:
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)')
            db.execute('INSERT INTO state VALUES (1,?)',(json.dumps(state),))
            db.execute('CREATE TABLE files(id TEXT PRIMARY KEY,body BLOB)')
            db.execute('INSERT INTO files VALUES (?,?)',('fictional-file',b'unchanged'))
        return state
    def baseline(self):
        with self.store.connect() as db:jobs=[tuple(r) for r in db.execute('SELECT * FROM jobs ORDER BY id')]
        with sqlite3.connect(self.profile) as db:body=db.execute('SELECT body FROM state').fetchone()[0]
        return jobs,body
    def test_new_migration_excludes_pool_even_if_priority_is_high(self):
        result=migrate(self.store,self.snap)
        self.assertEqual(result['count'],3);self.assertEqual(result['excluded_source_rows'],3)
        self.assertTrue(all(j['application_status']=='已投递' for j in self.store.list_jobs()))
        self.assertIn('二面',[j['legacy_status'] for j in self.store.list_jobs()])
        self.assertEqual({j['source_record_id'] for j in self.store.list_jobs()},
            {'fictional-single','fictional-summary','pool-3'})
    def test_correction_preserves_applied_history_manual_intent_and_shared_data(self):
        before=self.original_import()
        new=self.store.create_link('https://example.com/future','fixture-explicit-future')
        expected=self.baseline()
        result=correct_scope(self.store,self.snap,self.profile,*expected)
        self.assertEqual((result['removed'],result['removed_preparations']),(3,1))
        self.assertEqual({j['id'] for j in self.store.list_jobs()},set(self.ids[:2]+[self.ids[5],new['id']]))
        jobs,body=self.baseline();after=json.loads(body)
        self.assertEqual(after['shared'],before['shared']);self.assertEqual([s['id'] for s in after['sessions']],['history','independent'])
        self.assertEqual(jobs,[r for r in expected[0] if r[0] not in result['removed_ids']])
        with sqlite3.connect(self.profile) as db:self.assertEqual(db.execute('SELECT body FROM files').fetchone()[0],b'unchanged')
        self.assertTrue(correct_scope(self.store,self.snap,self.profile,*expected)['replayed'])
        self.assertEqual(migrate(self.store,self.snap)['count'],3)
        self.assertEqual(len(self.store.list_jobs()),4)
    def test_manual_changes_to_an_accidental_row_block_bulk_correction(self):
        self.original_import()
        self.store.update(self.ids[2],1,{'role':'人工维护的新岗位'},None)
        expected=self.baseline()
        with self.assertRaises(Conflict):correct_scope(self.store,self.snap,self.profile,*expected)
        self.assertEqual(self.baseline(),expected)
    def test_changes_after_backup_block_correction(self):
        self.original_import();expected=self.baseline()
        self.store.create_link('https://example.com/new','fixture-after-backup')
        current=self.baseline()
        with self.assertRaises(Conflict):correct_scope(self.store,self.snap,self.profile,*expected)
        self.assertEqual(self.baseline(),current)
    def test_failed_delete_rolls_back_both_databases_and_ledger(self):
        self.original_import()
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER reject_fixture_delete BEFORE DELETE ON jobs BEGIN SELECT RAISE(ABORT,'fictional failure'); END")
        expected=self.baseline()
        with sqlite3.connect(self.store.path) as db:ledger=db.execute('SELECT payload FROM migrations WHERE id=?',(MIGRATION_ID,)).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):correct_scope(self.store,self.snap,self.profile,*expected)
        self.assertEqual(self.baseline(),expected)
        with sqlite3.connect(self.store.path) as db:self.assertEqual(db.execute('SELECT payload FROM migrations WHERE id=?',(MIGRATION_ID,)).fetchone()[0],ledger)


if __name__=='__main__':unittest.main(verbosity=2)
