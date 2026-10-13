"""D76: sources remain evidence; destinations require verification."""
import json
import tempfile
import unittest
from pathlib import Path
from official import OfficialLookup
from store import Store
from migration import separate_links
from test_official_results import entry, Model

class SourceLinksTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name))
        row=self.store.preview_text('示例公司 | 产品经理 | https://example.com/news/article')['candidates'][0]
        self.jid=self.store.import_selected([row],[{'id':row['id']}],'fictional-source-links',{})['ids'][0]
    def tearDown(self):self.temp.cleanup()
    def test_new_source_never_assumes_official_destination(self):
        j=self.store.get(self.jid);self.assertEqual(j['source_url'],'https://example.com/news/article');self.assertEqual(j['official_url'],'')
    def test_destination_never_overwrites_source(self):
        before=self.store.get(self.jid);after=self.store.set_official(self.jid,before['revision'],entry())
        self.assertEqual(after['source_url'],before['source_url']);self.assertEqual(after['official_url'],entry()['url']);self.assertEqual(after['url'],before['url'])
    def test_source_or_role_change_invalidates_destination(self):
        for patch in [{'source_url':'https://example.com/news/new'},{'role':'不同岗位'}]:
            j=self.store.get(self.jid);j=self.store.set_official(self.jid,j['revision'],entry());j=self.store.update(self.jid,j['revision'],patch,None)
            self.assertEqual(j['official_url_status'],'unverified');self.assertEqual(j['official_url'],'');self.assertNotIn('official_entry',j)
    def test_manual_official_input_requires_verification(self):
        j=self.store.get(self.jid);j=self.store.update(self.jid,j['revision'],{'official_url':'https://example.com/candidate'},None)
        self.assertEqual(j['official_url_status'],'unverified');self.assertEqual(j['official_url'],'https://example.com/candidate')
    def test_source_read_precedes_search_and_excludes_private_notes(self):
        e=entry();events=[];source='https://example.com/news/article'
        pages={e['company_url']:{'body':'示例公司','links':[e['recruitment_url']]},e['recruitment_url']:{'body':'示例公司招聘','links':[e['url']]},e['url']:{'body':'产品经理 上海市','links':[]},source:{'body':'示例公司 产品经理 招聘资讯 原文线索','links':[e['recruitment_url']]}}
        class Search(Model):
            def call(inner,prompt,schema):events.append('search');return super().call(prompt,schema)
        def read(url):events.append(url);return pages[url]
        model=Search({'candidates':[e]});lookup=OfficialLookup(model,read);job={**self.store.get(self.jid),'interview_notes':'private candidate notes'}
        summary=lookup.source_summary(job);self.assertEqual(summary['kind'],'recruitment_info');self.assertNotIn('document',summary)
        result=lookup.lookup(job);self.assertEqual(events[0],source);self.assertLess(events.index(source),events.index('search'));self.assertEqual(events.count(source),1)
        self.assertEqual(result['status'],'ready');self.assertIn('原文线索',model.prompts[0]);self.assertIn(source,model.prompts[0]);self.assertNotIn('private candidate notes',model.prompts[0])
    def test_blocked_article_never_becomes_application_destination(self):
        def blocked(url):raise ValueError('blocked')
        result=OfficialLookup(Model({'candidates':[]}),blocked).lookup({'company':'示例公司','role':'产品经理','source_url':'https://mp.weixin.qq.com/s/example'})
        self.assertEqual(result['source_analysis']['kind'],'recruitment_info');self.assertFalse(result['source_analysis']['readable']);self.assertNotEqual(result['status'],'ready')
    def test_company_site_and_role_links_are_distinguished(self):
        lookup=OfficialLookup(reader=lambda u:{'body':'示例公司官网','links':[],'final_url':u})
        for url,kind in [('https://example.com/','company_site'),('https://example.com/campus/detail?jobAdId=fictional','job_detail')]:
            self.assertEqual(lookup.source_summary({'company':'示例公司','role':'产品经理','source_url':url})['kind'],kind)
    def test_migration_preserves_values_and_replays(self):
        with self.store.connect() as db:
            raw=json.loads(db.execute('SELECT payload FROM jobs WHERE id=?',(self.jid,)).fetchone()[0]);raw.pop('official_url');raw['url']='https://example.com/official';raw['source_url']='https://example.com/news/article';raw['official_url_status']='verified';raw['official_entry']={'url':raw['url']};db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(raw),self.jid))
            before=[tuple(r) for r in db.execute('SELECT * FROM jobs ORDER BY id')]
        result=separate_links(self.store,before);self.assertEqual(result['official_verified'],1)
        after=self.store.get(self.jid);self.assertEqual(after['source_url'],raw['source_url']);self.assertEqual(after['official_url'],raw['url'])
        for key,value in raw.items():self.assertEqual(after[key],value)
        self.assertTrue(separate_links(self.store,before)['replayed'])

    def test_personal_application_source_keeps_public_job_identity_without_personal_query(self):
        calls=[];model=Model({'candidates':[]});lookup=OfficialLookup(model,lambda u:calls.append(u))
        result=lookup.lookup({'company':'示例公司','role':'产品经理','source_url':'https://example.com/form?jobAdId=public-role&userId=private-user&token=secret'})
        self.assertEqual(calls,[]);self.assertIn('public-role',model.prompts[0]);self.assertNotIn('private-user',model.prompts[0]);self.assertNotIn('secret',model.prompts[0])
        self.assertEqual(result['source_analysis']['kind'],'job_detail')
