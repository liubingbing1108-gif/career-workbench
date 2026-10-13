"""Regression for a single managed flow and complete record/version visibility."""
import copy
import unittest
from pathlib import Path
from test_product_fixture import make_fixture
from job_sessions import JobSessions
from executor_bridge import ExecutorBridge
from lab import LabError

class FlowTests(unittest.TestCase):
    def setUp(self):
        self.fixture,self.management,self.module=make_fixture()
        self.lab=self.fixture.lab;self.app=self.fixture.app;self.prep=self.fixture.prep
        self.jobs=JobSessions(self.lab,self.management.store,self.prep)
    def tearDown(self):self.fixture.tearDown()
    def test_public_role_reopens_reviewed_applicant_form_and_keeps_all_choices(self):
        job=self.management.store.list_jobs()[0];sid=next(s['id'] for s in self.lab.state()['sessions'] if s.get('management_job_id')==job['id'])
        # Same verified role, and a later stale empty preparation with its public URL.
        role='https://example.com/campus/detail?jobAdId=fictional';form='https://example.com/form?jobAdId=fictional&userId=fictional'
        self.management.store.update(job['id'],job['revision'],{'url':role},None)
        current=self.management.store.get(job['id']);self.management.store.set_official(job['id'],current['revision'],{'company':job['company'],'role':job['role'],'url':role,'company_url':role,'recruitment_url':role,'verification':'browser','evidence':[{'url':role,'quote':'fictional role'}]})
        def alter(state):
            session=next(s for s in state['sessions'] if s['id']==sid);session['website']['url']=form
            session.setdefault('preparation',{})['execution']={'status':'needs_attention','filled':10,'verified':10}
        self.lab.mutate(alter);self.prep.open_target(role,job_id=job['id'])
        before=self.lab.state();chosen=self.jobs.open({'job_id':job['id']})
        self.assertEqual(chosen['id'],sid);self.assertEqual(before,self.lab.state())
        self.assertTrue(chosen['group_choices'])
    def test_unknown_scope_record_and_all_versions_remain_visible_but_cannot_be_filled(self):
        sid=self.fixture.sid;session=next(s for s in self.lab.state()['sessions'] if s['id']==sid)
        target=next(e for e in self.lab.state()['entries'] if e['category']=='employment' and e['values'].get('company')=='示例丙科技')
        self.lab.save_profile([{'entry_id':target['id'],'field_id':'employment_type','value':''}])
        def rule(state):
            item=next(m for m in next(s for s in state['sessions'] if s['id']==sid)['website']['mappings'] if m['website_id']=='internships')
            item['requirement']['filters']=[{'field_id':'employment_type','domain':'employment_type','op':'in','values':['internship']}]
        self.lab.mutate(rule);plan=self.app.plan(sid);item=next(i for i in plan['decisions'] if i['website_field']['id']=='internships')
        record=next(e for e in item['catalog'] if e['id']==target['id'])
        self.assertEqual(record['eligibility'],'needs_scope')
        self.assertEqual(len(next(c for c in record['choices'] if c['field']['id']=='description')['versions']),2)
        self.assertNotIn(target['id'],[e['id'] for e in item['selected']])
        with self.assertRaises(LabError):self.app.select_entries(sid,'employment',[target['id']],'internships')
    def test_nonselected_version_can_be_selected_and_preview_keeps_each_record(self):
        sid=self.fixture.sid;plan=self.app.plan(sid);item=next(i for i in plan['decisions'] if i['website_field']['id']=='internships')
        records=item['catalog'];last=records[-1];desc=next(c for c in last['choices'] if c['field']['id']=='description');version=desc['versions'][-1]
        self.app.select_version(sid,'internships',version['id'],entry_id=last['id'],field_id='description')
        self.app.select_entries(sid,'employment',[e['id'] for e in records],'internships')
        preview=self.prep.current(sid);rows=next(r for r in preview['rows'] if r['website_id']=='internships')['records']
        self.assertEqual(len(rows),3);self.assertEqual(next(v for v in rows[-1]['values'] if v['website_id']=='description')['value'],version['content'])
    def test_adopt_only_same_verified_job_form(self):
        origin='chrome-extension://'+'a'*32;role='https://example.com/campus/detail?jobAdId=fictional'
        session=self.prep.open_target(role,job_id='managed-fictional');bridge=ExecutorBridge(self.lab)
        code=bridge.setup(session['id'])['code']
        with self.assertRaises(LabError):bridge.call('connect',origin,{'code':code,'url':'https://example.com/form?jobAdId=other'})
        form='https://example.com/form?jobAdId=fictional&userId=example'
        result=bridge.call('connect',origin,{'code':code,'url':form});self.assertTrue(result['connection'])
        saved=next(s for s in self.lab.state()['sessions'] if s['id']==session['id'])
        self.assertEqual(saved['target']['url'],form);self.assertEqual(saved['target']['public_url'],role)

    def test_source_article_never_becomes_execution_target(self):
        job=self.management.store.list_jobs()[0]
        job=self.management.store.update(job['id'],job['revision'],{'source_url':'https://example.com/news/source'},None)
        with self.assertRaises(LabError):self.jobs.open({'job_id':job['id']})
        official='https://example.com/campus/detail?jobAdId=new-role'
        self.management.store.set_official(job['id'],job['revision'],{'company':job['company'],'role':job['role'],'url':official,'company_url':'https://example.com/','recruitment_url':official,'verification':'browser','evidence':[{'url':official,'quote':job['role']}]})
        session=self.jobs.open({'job_id':job['id']});self.assertEqual(session['target']['url'],official)
        self.jobs.validate_destination(session['id'])
        saved=self.management.store.get(job['id']);self.assertEqual(saved['source_url'],'https://example.com/news/source')
        self.management.store.update(job['id'],saved['revision'],{'source_url':'https://example.com/news/changed'},None)
        with self.assertRaises(LabError):self.jobs.validate_destination(session['id'])

if __name__=='__main__':unittest.main()
