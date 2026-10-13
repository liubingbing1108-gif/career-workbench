import unittest
from intake import PageText
from direct_entry import DirectEntry, classify, feishu_identity
from official import OfficialLookup
from test_official_results import Model

BASE='https://fictional.jobs.feishu.cn'
ID='1111111111111111111'
FORM=BASE+'/campus/resume/'+ID+'/apply'
DETAIL=BASE+'/campus/position/detail/'+ID

class DirectEntryTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.job={'company':'示例','role':'产品经理','source_url':FORM}
        self.page={'body':'示例校招官网','metadata':{'tenant_name':'示例公司','website_path':'campus'},'links':['https://example.com/']}
        self.detail={'code':0,'data':{'job_post_detail':{'id':ID,'title':'校招-产品经理','city_list':[{'name':'上海'}],'channel_online_status':1}}}
        def read(url):self.calls.append(url);return self.page
        def request(url):self.calls.append(url);return self.detail
        self.direct=DirectEntry(read,request)
    def test_classifies_messages_home_detail_and_form(self):
        for url,kind in [(FORM,'application_form'),(DETAIL,'job_detail'),('https://example.com/form?jobAdId=x','application_form'),('https://example.com/apply','application_form'),('https://mp.weixin.qq.com/s/fictional','recruitment_info'),('https://example.com/',None)]:self.assertEqual(classify(url),kind)
    def test_public_tenant_and_exact_job_read_skip_search_and_keep_application(self):
        model=Model({});lookup=OfficialLookup(model,lambda _:self.page,direct=self.direct)
        result=lookup.lookup(self.job)
        self.assertEqual(result['status'],'ready');self.assertEqual(model.prompts,[])
        self.assertEqual(result['entry']['url'],DETAIL);self.assertEqual(result['entry']['application_url'],FORM)
        self.assertNotIn(FORM,self.calls)
    def test_mismatch_never_adopts_similar_title(self):
        self.detail['data']['job_post_detail']['title']='AI产品经理'
        r=self.direct.inspect(self.job);self.assertEqual(r['status'],'identity_mismatch');self.assertEqual(r['candidates'][0]['role'],'产品经理')
    def test_company_mismatch_stops_before_job_query(self):
        self.page['metadata']['tenant_name']='其他示例公司'
        self.assertEqual(self.direct.inspect(self.job)['reason'],'company_mismatch');self.assertEqual(len(self.calls),1)
    def test_closed_or_wrong_id_never_becomes_ready(self):
        for patch in [{'id':'2222222222222222222'},{'channel_online_status':0}]:
            old=dict(self.detail['data']['job_post_detail']);self.detail['data']['job_post_detail'].update(patch)
            self.assertEqual(self.direct.inspect(self.job)['status'],'needs_review');self.detail['data']['job_post_detail']=old
    def test_personal_query_is_never_sent_to_public_reader(self):
        self.direct.inspect({**self.job,'source_url':FORM+'?userId=private&token=secret'})
        self.assertNotIn('private',str(self.calls));self.assertNotIn('secret',str(self.calls))
    def test_platform_suffix_credentials_and_site_path_are_checked(self):
        for url in [FORM.replace('feishu.cn','feishu.cn.attacker.invalid'),FORM.replace('https://','https://u:p@')]:self.assertIsNone(feishu_identity(url))
        self.page['metadata']['website_path']='other';self.assertEqual(self.direct.inspect(self.job)['reason'],'company_mismatch')
    def test_generic_application_requires_read_only_inspection_no_model(self):
        model=Model({});r=OfficialLookup(model,lambda _:{}).lookup({**self.job,'source_url':'https://example.com/apply'})
        self.assertEqual(r['status'],'needs_inspection');self.assertEqual(model.prompts,[])
    def test_browser_identity_needs_exact_role_and_employer_authority(self):
        known={'company':'示例','recruitment_url':'https://example.com/careers','company_url':'https://employer.example/','verification':'browser'}
        lookup=OfficialLookup(reader=lambda _: {},known_entries=lambda:[known])
        job={**self.job,'source_url':'https://example.com/apply'}
        obs={'url':job['source_url'],'headings':['AI产品经理'],'employer_links':[]}
        self.assertEqual(lookup.inspect_browser(job,obs)['status'],'needs_review')
        obs['headings']=['产品经理'];self.assertEqual(lookup.inspect_browser(job,obs)['status'],'ready')
        self.assertEqual(OfficialLookup(reader=lambda _:{}).inspect_browser(job,obs)['status'],'needs_review')
    def test_public_website_bootstrap_retains_only_identity(self):
        parser=PageText();parser.feed('<script id="js-websiteInfo" type="text/json">{"tenant_info":{"tenant_name":"示例"}}</script><p>正文</p>')
        self.assertEqual(parser.parts,['正文']);self.assertIn('tenant_name',parser.website_json)
