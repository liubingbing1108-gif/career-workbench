import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from lab import Lab,LabError
from application import Application
from preparation import Preparation
from site_scan import scan_analysis,SiteScan
from executor_bridge import ExecutorBridge
from server import make_server


def snapshot(url='https://example.com/apply'):
    return {'schemaVersion':1,'page':{'url':url,'title':'虚构职位'},'sections':[{'sectionId':'education','label':'教育经历','canAdd':True,'count':2}],
            'fields':[{'fieldId':f'education[{i}].school','label':'学校','kind':'text','sectionId':'education','recordId':str(i),'required':True,'currentValue':'官网已有值不可导入','options':{'items':[]}} for i in range(2)]}


class UnifiedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(Path(self.tmp.name)/'profile');self.app=Application(self.lab);self.prep=Preparation(self.lab,self.app)
    def tearDown(self):self.lab.db.close();self.tmp.cleanup()
    def test_same_job_reuses_preparation_but_other_jobs_keep_independent_materials(self):
        s=self.prep.open_target('https://example.com/apply','虚构职位','job-1');before=copy.deepcopy(self.lab.state()['entries'])
        again=self.prep.open_target('https://example.com/apply','虚构','job-1')
        other=self.prep.open_target('https://example.com/apply','虚构','job-2')
        self.assertEqual(s['id'],again['id']);self.assertNotEqual(s['id'],other['id'])
        self.assertEqual(again['management_job_id'],'job-1');self.assertEqual(before,self.lab.state()['entries'])
        self.assertEqual(again['preparation']['scan_status'],'waiting_browser')
    def test_preference_requirement_preserves_session_but_blocks_automatic_filling(self):
        s=self.prep.open_target('https://example.com/apply',requires_preference=True)
        self.assertIn('志愿',s['manual_reason'])
        with self.assertRaisesRegex(LabError,'志愿'):self.prep.start(s['id'],'unused')
    def test_restart_requires_new_confirmation_for_old_running_task(self):
        session=self.prep.open_target('https://example.com/apply')
        self.lab.mutate(lambda state:next(s for s in state['sessions'] if s['id']==session['id'])['preparation'].update(execution={'status':'running','filled':3,'verified':2}))
        ExecutorBridge(self.lab)
        job=next(s for s in self.lab.state()['sessions'] if s['id']==session['id'])['preparation']['execution']
        self.assertEqual(job['status'],'paused');self.assertEqual(job['filled'],3);self.assertEqual(job['verified'],2)
    def test_invalid_link_does_not_create_session(self):
        before=self.lab.state()
        for url in ['javascript:alert(1)','http://example.com','https://u:p@example.com']:
            with self.assertRaises(LabError):self.prep.open_target(url)
        self.assertEqual(before,self.lab.state())
    def test_spa_application_fragment_is_preserved(self):
        url='https://example.com/index.html#/main/apply?job=fictional'
        self.assertEqual(self.prep.open_target(url)['target']['url'],url)
    def test_snapshot_contains_only_metadata_and_record_structure(self):
        s=scan_analysis(snapshot(),'https://example.com/apply');section=s['sections'][0]
        self.assertTrue(section['repeatable']);self.assertEqual(len(section['fields']),1)
        self.assertEqual(section['fields'][0]['id'],'education[].school')
        self.assertNotIn('官网已有值',json.dumps(s,ensure_ascii=False))
        with self.assertRaises(LabError):scan_analysis(snapshot(),'https://other.example.com/')
    def test_unsectioned_fields_and_actual_group_instructions_are_preserved(self):
        raw=snapshot();raw['sections'][0]['description']='请从本科起填写全部教育经历'
        raw['fields'].extend([{'fieldId':key,'label':label,'kind':'text','sectionId':'page','recordId':key,'required':True,'currentValue':'不可导入'} for key,label in [('name','姓名'),('email','邮箱')]])
        a=scan_analysis(raw,'https://example.com/apply')
        self.assertEqual(a['sections'][0]['note'],'请从本科起填写全部教育经历')
        scalar=next(s for s in a['sections'] if s['id']=='page')
        self.assertFalse(scalar['repeatable']);self.assertEqual(scalar['fields'][0]['id'],'name')
        self.assertNotIn('不可导入',json.dumps(a,ensure_ascii=False))
        raw['sections']=[];raw['fields']=raw['fields'][-2:]
        self.assertEqual(scan_analysis(raw,'https://example.com/apply')['sections'][0]['fields'][0]['id'],'name')
    def test_flat_repeated_fields_share_schema_only_when_each_record_has_one_match(self):
        raw=snapshot();raw['fields']=[dict(fieldId='flat-'+str(i),label='学校',kind='text',sectionId='education',recordId='row-'+str(i),currentValue='不可导入',context={'componentIndex':0}) for i in range(2)]
        fields=scan_analysis(raw,'https://example.com/apply')['sections'][0]['fields']
        self.assertEqual(len(fields),1);self.assertEqual(fields[0]['executor_field_ids'],['flat-0','flat-1'])
        raw['fields'].append({**raw['fields'][0],'fieldId':'duplicate'})
        self.assertEqual(len(scan_analysis(raw,'https://example.com/apply')['sections'][0]['fields']),3)
    def test_paired_browser_scan_maps_new_target_and_preserves_original_facts(self):
        s=self.prep.open_target('https://example.com/apply');before=self.lab.state()['entries']
        class Mapper:
            def map(self,fields,profile):
                return {'mappings':[{'website_id':'education','status':'mapped','category':'education','field_id':None,'requirement':{'group':'education','selection':'all','filters':[],'rank':None,'required_values':[],'min_items':None,'max_items':None,'summary':'完整教育经历'},'members':[{'website_id':'education[].school','field_id':'school'}]}]}
        prep=Preparation(self.lab,Application(self.lab,Mapper()));scan=SiteScan(self.lab,prep);bridge=ExecutorBridge(self.lab,scan.accept);origin='chrome-extension://'+'a'*32
        token=bridge.call('connect',origin,{'url':'https://example.com/apply','code':bridge.code})['connection']
        bridge.call('scan',origin,{'url':'https://example.com/apply','connection':token,'snapshot':snapshot()})
        for thread in scan.threads:thread.join(3)
        session=next(x for x in self.lab.state()['sessions'] if x['id']==s['id'])
        self.assertEqual(session['preparation']['scan_status'],'ready');self.assertTrue(session['website']);self.assertEqual(before,self.lab.state()['entries']);self.assertNotIn('execution',session['preparation'])
    def test_single_listener_mounts_management_with_token_and_origin_checks(self):
        root=Path(__file__).resolve().parents[1]/'management-lab';sys.path.insert(0,str(root))
        spec=importlib.util.spec_from_file_location('unified_management_test',root/'server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        app=module.App(Path(self.tmp.name)/'management');server=make_server(self.lab,management_app=app,management_handler=module.handler(app));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
        try:
            self.assertTrue(json.load(urlopen(base+'/api/health'))['management'])
            bootstrap=json.load(urlopen(base+'/management/api/bootstrap'));self.assertEqual(bootstrap['jobs'],[])
            self.assertIn('integration.js',urlopen(base+'/management/').read().decode())
            self.assertEqual(urlopen(base+'/management/integration.js').status,200)
            data=json.dumps({'text':'虚构公司 | 分析师 | https://example.com/job'}).encode()
            req=Request(base+'/management/api/preview/text',data=data,headers={'Content-Type':'application/json','X-Management-Token':bootstrap['token'],'Origin':base})
            self.assertEqual(urlopen(req).status,200)
            req=Request(base+'/management/api/preview/text',data=data,headers={'Content-Type':'application/json','X-Management-Token':bootstrap['token'],'Origin':'https://evil.example'})
            with self.assertRaises(HTTPError) as err:urlopen(req)
            self.assertEqual(err.exception.code,403);self.assertEqual(app.store.list_jobs(),[])
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
