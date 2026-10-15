import tempfile
import unittest
from unittest.mock import patch
from store import Store, Invalid, Conflict
from test_management import sample
from progress_query import ProgressQueries
from official import OfficialLookup
from direct_entry import classify
from test_official_results import Model

FORM='https://app.mokahr.com/campus_apply/fictional/123#/candidateHome/resume'

class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        c=sample(role='产品经理',stage='',kind='opportunities')
        self.jid=self.store.import_selected([c],[{'id':c['id']}],'fictional-progress',{})['ids'][0]
        self.original=self.store.get(self.jid)
        self.job=self.store.set_application_url(self.jid,self.original['revision'],FORM)
        self.queries=ProgressQueries(self.store)
    def tearDown(self):self.tmp.cleanup()
    def observation(self,**kw):return dict(status='records',url=FORM,records=[{'role':'产品经理','stage':'面试中'}],**kw)
    def test_manual_form_preserves_source_dates_status_and_is_ready_without_search(self):
        for key in ('source_url','timeline','application_status'):self.assertEqual(self.job[key],self.original[key])
        self.assertEqual(self.job['official_url'],FORM)
        model=Model({})
        self.assertEqual(OfficialLookup(model).lookup(self.job)['status'],'ready');self.assertEqual(model.prompts,[])
        with self.assertRaises(Conflict):self.store.set_application_url(self.jid,self.original['revision'],FORM)
    def test_direct_hash_form_and_unverified_official_skip_search(self):
        self.assertEqual(classify(FORM),'application_form')
        model=Model({});job={**self.original,'official_url':FORM,'official_url_status':'unverified'}
        self.assertEqual(OfficialLookup(model).lookup(job)['status'],'needs_inspection');self.assertEqual(model.prompts,[])
    def test_bad_manual_urls_cannot_replace_good_target(self):
        for url in ['http://example.com/form','https://localhost/form','https://127.0.0.1/form','https://u:p@example.com/form','javascript:alert(1)']:
            with self.assertRaises(Invalid):self.store.set_application_url(self.jid,self.job['revision'],url)
        self.assertEqual(self.store.get(self.jid),self.job)
    def test_one_confirmed_stage_updates_only_stage_and_is_idempotent(self):
        task=self.queries.start(self.jid);self.assertIs(task,self.queries.start(self.jid))
        result=self.queries.accept(task,self.observation());self.assertEqual(result['status'],'complete');self.assertTrue(result['changed'])
        job=self.store.get(self.jid);self.assertEqual(job['recruitment_stage'],'面试中')
        for key in ('timeline','application_status','source_url','official_url','interview_notes'):self.assertEqual(job[key],self.job[key])
        self.queries.accept(task,self.observation());self.assertEqual(self.store.get(self.jid)['revision'],job['revision'])
    def test_other_company_same_platform_rejected(self):
        obs=self.observation();obs['url']=FORM.replace('/fictional/','/other/')
        with self.assertRaises(Invalid):self.queries.accept(self.queries.start(self.jid),obs)
        self.assertEqual(self.store.get(self.jid),self.job)
    def test_missing_other_role_duplicate_login_never_changes_job(self):
        observations=[{'status':'needs_user'},{'status':'unavailable'},dict(status='records',url=FORM,records=[]),dict(status='records',url=FORM,records=[{'role':'其他产品经理','stage':'Offer'}]),dict(status='records',url=FORM,records=self.observation()['records']*2)]
        for obs in observations:
            self.queries.accept(self.queries.start(self.jid),obs);self.assertEqual(self.store.get(self.jid),self.job)
    def test_concurrent_manual_edit_wins(self):
        task=self.queries.start(self.jid);edited=self.store.update(self.jid,self.job['revision'],{'recruitment_stage':'本人确认的阶段'},None)
        self.assertEqual(self.queries.accept(task,self.observation())['status'],'unavailable');self.assertEqual(self.store.get(self.jid),edited)
    def test_expired_query_never_writes(self):
        task=self.queries.start(self.jid);task['started']-=101
        self.assertEqual(self.queries.status(self.jid)['status'],'unavailable')
        with self.assertRaises(Conflict):self.queries.accept(task,self.observation())
        self.assertEqual(self.store.get(self.jid),self.job)

    def test_explicit_preference_label_is_role_prefix_not_a_different_position(self):
        obs=self.observation();obs['records'][0]['role']='第 1 志愿 产品经理'
        self.assertEqual(self.queries.accept(self.queries.start(self.jid),obs)['status'],'complete')
