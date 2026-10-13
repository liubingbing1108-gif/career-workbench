import copy
import json
import tempfile
import unittest
from feishu import candidate
from migration import reclassify_results
from official import OfficialLookup
from store import Store,Invalid,Conflict


def entry():
    return {'company':'示例公司','role':'产品经理','location':'上海市',
            'company_url':'https://example.com/','recruitment_url':'https://example.com/careers',
            'url':'https://jobs.example.com/role/1','verification':'browser',
            'evidence':[{'url':'https://example.com/','quote':'示例公司'},
                        {'url':'https://jobs.example.com/role/1','quote':'产品经理'}]}


class Model:
    def __init__(self,result):self.result=result;self.prompts=[]
    def call(self,prompt,*_):self.prompts.append(prompt);return self.result,{}


class OfficialResultsTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def add(self,notes='群面/一面挂'):
        f={'公司名称':'示例公司','岗位名称':'产品经理','投递链接':'https://example.com/news','面试进度':'流程结束','面试记录及复盘':notes}
        c=candidate({'kind':'applications','name':'测试表'},{'record_id':'fictional-id','fields':f})
        c.update(legacy_interview_review=notes,recruitment_stage='流程结束');c.pop('official_url_status');c['source_url']=''
        return self.store.import_selected([c],[{'id':c['id']}],'fictional-outcome-source',{})['ids'][0]
    def raw(self):
        with self.store.connect() as d:return [tuple(r) for r in d.execute('SELECT * FROM jobs ORDER BY id')]
    def test_whole_result_is_stage_and_long_note_is_not_guessed(self):
        for value in ['简历挂','笔试挂','一面挂','面试挂','用人部门简历挂','群面/一面挂']:
            c=candidate({'kind':'applications','name':'测试表'},{'record_id':'fictional','fields':{'公司名称':'示例公司','岗位名称':'甲、乙','面试记录及复盘':value}})
            self.assertEqual(c['recruitment_stage'],value);self.assertTrue(c['role_summary']);self.assertEqual(c['legacy_fields']['面试记录及复盘'],value)
        c=candidate({'kind':'applications','name':'测试表'},{'record_id':'fictional','fields':{'公司名称':'示例公司','岗位名称':'甲','面试记录及复盘':'一面挂，下一批重新准备'}})
        self.assertEqual(c['recruitment_stage'],'');self.assertFalse(c['outcome_from_legacy_notes'])
    def test_real_correction_preserves_raw_notes_dates_and_replays(self):
        jid=self.add();before=self.store.get(jid);expected=self.raw()
        r=reclassify_results(self.store,expected);after=self.store.get(jid)
        self.assertEqual(r['classified'],1);self.assertEqual(after['recruitment_stage'],'群面/一面挂')
        self.assertEqual(after['legacy_interview_review'],'');self.assertEqual(after['legacy_fields'],before['legacy_fields'])
        self.assertEqual(after['source_url'],before['url']);self.assertEqual(after['timeline'],before['timeline'])
        self.assertTrue(reclassify_results(self.store,expected)['replayed'])
    def test_correction_rejects_changes_since_backup(self):
        jid=self.add();expected=self.raw();self.store.update(jid,1,{'recruitment_stage':'本人维护的进度'},None)
        with self.assertRaises(Conflict):reclassify_results(self.store,expected)
        r=reclassify_results(self.store,self.raw());self.assertEqual(r['classified'],0)
        self.assertEqual(self.store.get(jid)['recruitment_stage'],'本人维护的进度')
    def test_classification_preserves_edited_role_when_stage_was_untouched(self):
        jid=self.add('简历挂');self.store.update(jid,1,{'role':'用户修正岗位'},None)
        r=reclassify_results(self.store,self.raw());j=self.store.get(jid)
        self.assertEqual(r['classified'],1);self.assertEqual(j['role'],'用户修正岗位')
        self.assertEqual(j['recruitment_stage'],'简历挂')
    def test_official_entry_preserves_source_and_rejects_role_switch_or_stale_edit(self):
        jid=self.add();j=self.store.get(jid);e=entry()
        with self.assertRaises(Invalid):self.store.set_official(jid,j['revision'],{**e,'role':'AI产品经理'})
        saved=self.store.set_official(jid,j['revision'],e)
        self.assertEqual(saved['official_url'],e['url']);self.assertEqual(saved['url'],'https://example.com/news');self.assertEqual(saved['source_url'],'https://example.com/news')
        self.assertEqual(saved['timeline'],[]);self.assertEqual(saved['application_status'],'已投递')
        with self.assertRaises(Conflict):self.store.set_official(jid,j['revision'],e)
        changed=self.store.update(jid,saved['revision'],{'url':'https://example.com/new'},None)
        self.assertEqual(changed['official_url_status'],'unverified');self.assertNotIn('official_entry',changed)
    def test_search_needs_public_authority_chain_and_never_receives_personal_notes(self):
        e=entry();model=Model({'candidates':[e]})
        pages={e['company_url']:{'body':'示例公司','links':[e['recruitment_url']]},
               e['recruitment_url']:{'body':'示例公司招聘','links':[e['url']]},
               e['url']:{'body':'产品经理 上海市','links':[]}}
        job={'company':'示例公司','role':'产品经理','interview_notes':'private-should-not-send','source_url':'https://mp.weixin.qq.com/s/blocked'}
        r=OfficialLookup(model,pages.__getitem__).lookup(job)
        self.assertEqual(r['status'],'ready');self.assertNotIn('private-should-not-send',model.prompts[0]);self.assertIn('/s/blocked',model.prompts[0])
        pages[e['company_url']]['links']=[]
        self.assertEqual(OfficialLookup(model,pages.__getitem__).lookup(job)['status'],'needs_review')
        e['role']='AI产品经理';self.assertEqual(OfficialLookup(model,pages.__getitem__).lookup(job)['status'],'needs_selection')
    def test_search_answer_without_readable_role_and_untrusted_source_never_launches(self):
        e=entry();model=Model({'candidates':[e]});job={'company':'示例公司','role':'产品经理'}
        self.assertEqual(OfficialLookup(model,lambda u:{'body':'登录页','links':[]}).lookup(job)['status'],'needs_review')
        jid=self.add();e['url']='https://mp.weixin.qq.com/s/information'
        with self.assertRaises(Invalid):self.store.set_official(jid,1,e)


if __name__=='__main__':unittest.main()
