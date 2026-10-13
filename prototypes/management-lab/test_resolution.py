import json
import tempfile
import threading
import time
import unittest
from store import Store,Invalid
from resolution import ResolutionTasks
from official import OfficialLookup
from public_jobs import ZhiyeJobs,role_key
from test_official_results import entry,Model

JID='11111111-1111-4111-8111-111111111111'
OTHER='22222222-2222-4222-8222-222222222222'
BASE='https://fictional.zhiye.com'

class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name)
        row=self.store.preview_text('示例公司 | 产品经理 | https://example.com/article')['candidates'][0]
        self.id=self.store.import_selected([row],[{'id':row['id']}],'fictional-resolution',{})['ids'][0]
    def tearDown(self):self.temp.cleanup()
    def finish(self,tasks):
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            r=tasks.status(self.id)
            if r['status']!='resolving':return r
            time.sleep(.005)
        self.fail('resolution never completed')
    def test_inflight_reentry_reuses_task_and_completed_revision_is_pollable(self):
        gate=threading.Event();entered=threading.Event();calls=[]
        class Lookup:
            def lookup(_,job,progress):
                calls.append(job['id']);entered.set();progress('正在测试公开查询','fixture');gate.wait(2)
                return {'status':'ready','entry':entry()}
        tasks=ResolutionTasks(self.store,Lookup);self.assertEqual(tasks.status(self.id,True)['status'],'resolving');entered.wait(1)
        for _ in range(3):self.assertEqual(tasks.status(self.id,True)['status'],'resolving')
        self.assertEqual(calls,[self.id]);gate.set();result=self.finish(tasks)
        self.assertEqual(result['status'],'ready');self.assertEqual(result['job']['official_url_status'],'verified');self.assertEqual(self.store.get(self.id)['source_url'],'https://example.com/article')
    def test_edit_during_search_cannot_write_old_entry(self):
        gate=threading.Event();finished=threading.Event()
        class Lookup:
            def lookup(_,job,progress):gate.wait(2);finished.set();return {'status':'ready','entry':entry()}
        tasks=ResolutionTasks(self.store,Lookup);tasks.status(self.id,True)
        self.store.update(self.id,1,{'role':'另一个岗位'},None);gate.set();finished.wait(1)
        time.sleep(.02)
        self.assertEqual(self.store.get(self.id)['official_url'],'');self.assertEqual(tasks.status(self.id)['status'],'unavailable')
    def test_choice_only_accepts_verified_candidate_from_current_revision(self):
        e=entry();e['verification']='public_pages'
        class Lookup:
            def lookup(_,job,progress):return {'status':'needs_selection','candidates':[e]}
        tasks=ResolutionTasks(self.store,Lookup);tasks.status(self.id,True);self.finish(tasks)
        with self.assertRaises(Invalid):tasks.choose(self.id,'https://attacker.invalid/')
        self.assertEqual(tasks.choose(self.id,e['url'])['status'],'ready')
    def test_verified_entry_skips_source_read_and_model(self):
        e=entry();j={'company':e['company'],'role':e['role'],'source_url':'https://example.com/slow','official_url':e['url'],'official_url_status':'verified','official_entry':e}
        def reject(_):self.fail('should not fetch a source before resuming verified job')
        self.assertEqual(OfficialLookup(reader=reject).lookup(j)['status'],'ready')
    def test_direct_role_mismatch_requires_explicit_choice_preserves_source_and_status(self):
        e={**entry(),'verification':'public_pages','official_role':'增长产品经理'}
        class Lookup:
            def lookup(_,job,progress):return {'status':'identity_mismatch','candidates':[e]}
        tasks=ResolutionTasks(self.store,Lookup);tasks.status(self.id,True);self.finish(tasks)
        before=self.store.get(self.id)
        with self.assertRaises(Invalid):tasks.choose(self.id,e['url'])
        r=tasks.choose(self.id,e['url'],True);j=r['job']
        self.assertEqual(j['role'],'增长产品经理');self.assertEqual(j['source_url'],before['source_url']);self.assertEqual(j['application_status'],before['application_status']);self.assertEqual(j['timeline'],[])
        self.assertEqual(tasks.status(self.id)['status'],'ready')
    def test_search_failure_reason_is_visible(self):
        class Failure(Exception):code='capacity'
        class Lookup:
            def call(self,*_):raise Failure()
        result=OfficialLookup(Lookup(),lambda _:{}).lookup({'company':'示例公司','role':'产品经理'})
        self.assertEqual(result['reason'],'capacity');self.assertIn('繁忙',result['message'])
    def test_source_timeout_does_not_block_company_search(self):
        gate=threading.Event()
        def read(_):gate.wait(3);return {'body':'','links':[]}
        t=time.monotonic();r=OfficialLookup(Model({'candidates':[]}),read).lookup({'company':'示例公司','role':'产品经理','source_url':'https://example.com/slow'})
        gate.set();self.assertLess(time.monotonic()-t,2.6);self.assertFalse(r['source_analysis']['readable'])
    def test_native_search_snippets_alone_do_not_verify_company(self):
        lookup=OfficialLookup(reader=lambda _: (_ for _ in ()).throw(ValueError()))
        pages=[{'url':'https://example.com/careers','title':'示例公司','opened':False},{'url':BASE,'title':'示例公司招聘','opened':False}]
        self.assertFalse(lookup.discovery_verified({'company':'示例公司'},pages[0]['url'],BASE,{'web_pages':pages}))
        for p in pages:p['opened']=True
        self.assertTrue(lookup.discovery_verified({'company':'示例公司'},pages[0]['url'],BASE,{'web_pages':pages}))

class PublicJobsTests(unittest.TestCase):
    def detail(self,id=JID,title='27届校招-产品经理(J12345)',status=1,city='上海市'):
        return {'Code':200,'Data':{'Id':id,'JobAdName':title,'Status':status,'CategoryId':'2','LocNames':[city]}}
    def test_private_source_yields_only_public_job_queries(self):
        calls=[]
        def request(url,body=None):calls.append((url,body));return self.detail()
        j={'company':'示例公司','role':'产品经理','location':'上海','source_url':BASE+'/form?jobAdId='+JID+'&userId=private&token=secret'}
        r=ZhiyeJobs(request).candidates(j,BASE+'/home','https://example.com/careers')
        self.assertEqual(len(r),1);self.assertIn('/campus/detail?',r[0]['url']);self.assertNotIn('private',str(calls));self.assertNotIn('secret',str(calls));self.assertEqual(r[0]['official_role'],'27届校招-产品经理(J12345)')
    def test_plain_company_role_uses_list_and_preserves_multiple_matches(self):
        def request(url,body=None):
            if body:return {'Data':[self.detail()['Data'],self.detail(OTHER,'【27校招】产品经理(J23456)')['Data']],'Count':2}
            return self.detail(OTHER,'【27校招】产品经理(J23456)') if OTHER in url else self.detail()
        r=ZhiyeJobs(request).candidates({'company':'示例公司','role':'产品经理'},BASE,'https://example.com/')
        self.assertEqual(len(r),2);self.assertNotEqual(r[0]['url'],r[1]['url'])
    def test_different_role_closed_job_wrong_id_and_location_are_not_accepted(self):
        j={'company':'示例公司','role':'产品经理','location':'上海','source_url':BASE+'/detail?jobAdId='+JID}
        for data in [self.detail(title='AI产品经理'),self.detail(city='北京')]:
            self.assertEqual(ZhiyeJobs(lambda *a:data).candidates(j,BASE,'https://example.com/'),[])
        for data in [self.detail(status=2),self.detail(id=OTHER)]:
            with self.assertRaises(Invalid):ZhiyeJobs(lambda *a:data).candidates(j,BASE,'https://example.com/')
        self.assertNotEqual(role_key('AI产品经理'),role_key('产品经理'))
    def test_company_authority_and_role_api_both_required(self):
        class Search:
            def call(self,*_):return {'company_url':'https://example.com/careers','recruitment_url':BASE,'candidates':[]},{'web_pages':[{'url':'https://example.com/careers','title':'示例公司','opened':True},{'url':BASE,'title':'示例公司招聘','opened':True}]}
        j={'company':'示例公司','role':'产品经理','source_url':BASE+'/form?jobAdId='+JID+'&userId=secret'}
        lookup=OfficialLookup(Search(),lambda _: (_ for _ in ()).throw(ValueError()),ZhiyeJobs(lambda *a:self.detail()))
        r=lookup.lookup(j);self.assertEqual(r['status'],'ready');self.assertEqual(r['entry']['verification_method'],'public_web_and_ats_api')

if __name__=='__main__':unittest.main()
