import tempfile
import unittest
from lab import Lab, LabError
from executor_bridge import ExecutorBridge


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name)
        self.session=self.lab.new_session();self.url='https://example.com/apply';self.origin='chrome-extension://'+'a'*32
        self.lab.mutate(lambda s:s['sessions'][0].update(website={'url':self.url}))
        self.bridge=ExecutorBridge(self.lab)
    def tearDown(self):self.lab.db.close();self.tmp.cleanup()
    def connect(self):
        return self.bridge.call('connect',self.origin,dict(code=self.bridge.code,url=self.url))['connection']
    def test_origin_code_and_target_must_all_match(self):
        for origin,data in [('https://evil.example',dict(code=self.bridge.code,url=self.url)),(self.origin,dict(code='invalid',url=self.url)),(self.origin,dict(code=self.bridge.code,url='https://other.example/apply'))]:
            with self.assertRaises(LabError):self.bridge.call('connect',origin,data)
    def test_code_single_use_and_unconfirmed_materials_not_disclosed(self):
        code=self.bridge.code;token=self.connect()
        with self.assertRaises(LabError):self.bridge.call('connect',self.origin,dict(code=code,url=self.url))
        result=self.bridge.call('poll',self.origin,dict(connection=token,url=self.url))
        self.assertIsNone(result['job']);self.assertTrue(self.bridge.status(self.url)['connected'])
    def test_confirmed_job_claimed_once_and_reports_must_own_job(self):
        token=self.connect();base=dict(connection=token,url=self.url)
        self.lab.mutate(lambda s:s['sessions'][0].update(preparation={'execution':{'id':'test-job','status':'awaiting_executor','confirmed_materials':{'url':self.url,'rows':[]}}}))
        first=self.bridge.call('poll',self.origin,base);second=self.bridge.call('poll',self.origin,base)
        self.assertEqual(first['job']['id'],'test-job');self.assertIsNone(second['job'])
        with self.assertRaises(LabError):self.bridge.call('report',self.origin,{**base,'job_id':'unknown','status':'complete','filled':1,'verified':1,'message':'done'})
        self.bridge.call('report',self.origin,{**base,'job_id':'test-job','status':'needs_attention','filled':2,'verified':2,'message':'请检查','issues':['附件待上传']})
        job=self.lab.state()['sessions'][0]['preparation']['execution'];self.assertEqual(job['verified'],2);self.assertEqual(job['status'],'needs_attention')
    def test_connection_cannot_be_reused_by_another_extension_or_page(self):
        token=self.connect()
        for origin,url in [('chrome-extension://'+'b'*32,self.url),(self.origin,'https://other.example')]:
            with self.assertRaises(LabError):self.bridge.call('poll',origin,dict(connection=token,url=url))
    def test_lost_connection_does_not_claim_fill_complete(self):
        token=self.connect()
        self.lab.mutate(lambda s:s['sessions'][0].update(preparation={'execution':{'id':'job','status':'running','connection':token,'filled':2,'verified':2}}))
        self.bridge.connections[token]['seen']-=31
        self.assertFalse(self.bridge.status(self.url)['connected'])
        self.assertEqual(self.lab.state()['sessions'][0]['preparation']['execution']['status'],'failed')
    def test_only_confirmed_selected_attachment_is_transferred_unchanged(self):
        reads=[]
        self.lab.file_bytes=lambda fid:(reads.append(fid) or {'name':'fictional.pdf'},b'original fictional bytes')
        token=self.connect();base=dict(connection=token,url=self.url)
        self.bridge.call('poll',self.origin,base);self.assertEqual(reads,[])
        self.lab.mutate(lambda s:s['sessions'][0].update(preparation={'execution':{'id':'attachment-job','status':'awaiting_executor','confirmed_materials':{'url':self.url,'rows':[],'attachment':{'id':'selected','name':'fictional.pdf'}}}}))
        result=self.bridge.call('poll',self.origin,base)
        import base64
        self.assertEqual(reads,['selected']);self.assertEqual(base64.b64decode(result['job']['materials']['attachment']['base64']),b'original fictional bytes')
        self.bridge.call('report',self.origin,{**base,'job_id':'attachment-job','status':'needs_attention','filled':0,'verified':2,'message':'done','saved':True,'attachment_verified':True})
        job=self.lab.state()['sessions'][0]['preparation']['execution'];self.assertTrue(job['saved']);self.assertTrue(job['attachment_verified'])

    def test_manual_fields_remain_attention_after_executor_finishes(self):
        token=self.connect();base=dict(connection=token,url=self.url)
        self.lab.mutate(lambda s:s['sessions'][0].update(preparation={'execution':{'id':'manual-job','status':'awaiting_executor','confirmed_materials':{'url':self.url,'rows':[],'manual':[{'label':'虚构待补项'}]}}}))
        self.bridge.call('poll',self.origin,base)
        self.bridge.call('report',self.origin,{**base,'job_id':'manual-job','status':'complete','filled':2,'verified':2,'message':'独立字段完成','issues':[]})
        job=self.lab.state()['sessions'][0]['preparation']['execution']
        self.assertEqual(job['status'],'needs_attention');self.assertIn('虚构待补项',job['issues'][0])
