"""Fictional regressions for synonymous fields and pre-library scalar answers."""
import copy
import json
import tempfile
import threading
import unittest
import urllib.request
from application import Application
from lab import Lab, LabError, find
from requirements import requirement
from server import make_server

class MappingCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.lab=Lab(self.temp.name);self.app=Application(self.lab)
        self.sid=self.lab.new_session()['id']
    def tearDown(self):self.lab.db.close();self.temp.cleanup()
    def legacy(self):
        entry=self.lab.mutate(lambda s:self.lab.new_entry(s,'subjective'))
        def seed(s):
            s['profile_legacy_single_entries']={'subjective':[entry['id']]}
            find(s['sessions'],self.sid)['website']={'contract_version':2,'url':'https://example.com/apply','title':'虚构申请','fields':[dict(id='evaluation',label='自我评价')],
                'mappings':[dict(website_id='evaluation',category='subjective',status='new',field_id=None,requirement=None,new_field=dict(label='自我评价',category='subjective',type='versioned_text'),members=[])]}
        self.lab.mutate(seed)
        return entry
    def test_legacy_empty_evaluation_reads_and_saves_same_record(self):
        entry=self.legacy();before=copy.deepcopy(self.lab.state()['entries'])
        missing=self.app.plan(self.sid)['missing'][0]
        self.assertEqual(missing['entry_id'],entry['id']);self.assertTrue(missing['editable'])
        self.assertEqual(missing['kind'],'value')
        result=self.app.edit_answer(self.sid,'evaluation','虚构的本人确认评价','session',entry_id=entry['id'])
        self.assertEqual(result['entry_id'],entry['id'])
        self.assertEqual(self.app.plan(self.sid)['payload'][0]['value'],'虚构的本人确认评价')
        self.assertEqual(self.lab.state()['entries'],before)
        self.lab.mutate(lambda s:self.lab.new_entry(s,'subjective'))
        self.assertEqual(self.app.plan(self.sid)['payload'][0]['entry_id'],entry['id'])
    def test_self_evaluation_save_endpoint_returns_success(self):
        entry=self.legacy();server=make_server(self.lab);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)
            body=dict(session_id=self.sid,website_id='evaluation',entry_id=entry['id'],value='虚构评价',mode='session')
            request=urllib.request.Request(base+'/api/website/answer',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':base})
            with urllib.request.urlopen(request) as response:self.assertEqual(response.status,200)
            self.assertEqual(self.app.plan(self.sid)['payload'][0]['value'],'虚构评价')
        finally:server.shutdown();server.server_close();worker.join()

    def test_rematching_legacy_scalar_preserves_draft_and_upgrades_scope(self):
        entry=self.legacy();eid=entry['id'];key=self.sid+'/evaluation/'+eid+'/evaluation'
        self.lab.mutate(lambda s:find(s['sessions'],self.sid).update(preparation={'drafts':{key:dict(value='未确认评价草稿',revision=2)}}))
        website=copy.deepcopy(find(self.lab.state()['sessions'],self.sid)['website'])
        mappings=website.pop('mappings')
        self.app.install_mapping(self.sid,website,dict(mappings=mappings))
        self.assertEqual(self.app.plan(self.sid)['missing'][0]['entry_id'],eid)
        self.assertEqual(find(self.lab.state()['sessions'],self.sid)['preparation']['drafts'][key]['value'],'未确认评价草稿')
    def test_synonyms_reuse_fields_within_the_right_record(self):
        entry=self.lab.mutate(lambda s:self.lab.new_entry(s,'projects'))
        self.lab.save_profile([dict(entry_id=entry['id'],field_id='project_role',value='虚构项目负责人')])
        self.lab.mutate(lambda s:self.lab.new_entry(s,'employment'))
        for label in ['项目角色','本人角色','担任角色']:
            with self.subTest(label=label):
                field=dict(id='project',label='项目经历',collection=True,children=[dict(id='role',label=label,required=True)])
                mapping=dict(website_id='project',field_id=None,category='projects',status='mapped',requirement=requirement('projects'),members=[dict(website_id='role',field_id=None,new_field=dict(label=label,category='projects',type='text'))])
                self.app.install_mapping(self.sid,dict(url='https://example.com/apply',fields=[field]),dict(mappings=[mapping]))
                plan=self.app.plan(self.sid)
                self.assertEqual(plan['payload'][0]['value'],[{'project_role':'虚构项目负责人'}])
                self.assertEqual(plan['website']['mappings'][0]['members'][0]['field_id'],'project_role')
        self.assertIsNone(self.app._existing_field(self.lab.state(),dict(category='projects',label='工作职责')))
    def test_old_new_field_edit_reuses_synonymous_definition(self):
        entry=self.lab.mutate(lambda s:self.lab.new_entry(s,'projects'))
        self.lab.save_profile([dict(entry_id=entry['id'],field_id='project_name',value='虚构项目')])
        def seed(s):
            find(s['sessions'],self.sid)['website']={'contract_version':2,'url':'https://example.com','fields':[dict(id='project',label='项目',collection=True,children=[dict(id='role',label='项目角色')])],
                'mappings':[dict(website_id='project',category='projects',status='mapped',field_id=None,requirement=requirement('projects'),members=[dict(website_id='role',field_id=None,new_field=dict(label='项目角色',category='projects',type='text'))])]}
        self.lab.mutate(seed);before=len(self.lab.state()['fields'])
        result=self.app.edit_answer(self.sid,'project','虚构负责角色','session',entry_id=entry['id'],child_id='role')
        self.assertEqual(result['field']['id'],'project_role');self.assertEqual(len(self.lab.state()['fields']),before)

    def test_rebinding_keeps_confirmed_text_drafts_and_optional_decisions(self):
        self.lab.add_field(dict(id='old_role',label='项目角色',category='projects',type='text'))
        entry=self.lab.mutate(lambda s:self.lab.new_entry(s,'projects'));eid=entry['id']
        self.lab.save_profile([dict(entry_id=eid,field_id='old_role',value='已确认的虚构角色')])
        field=dict(id='project',label='项目经历',collection=True,children=[dict(id='role',label='项目角色')])
        mapping=dict(website_id='project',category='projects',field_id=None,status='mapped',requirement=requirement('projects'),members=[dict(website_id='role',field_id='old_role')])
        manifest=dict(url='https://example.com/apply',fields=[field])
        self.app.install_mapping(self.sid,manifest,dict(mappings=[mapping]))
        old_key=self.sid+'/projects/'+eid+'/old_role';new_key=self.sid+'/projects/'+eid+'/project_role'
        def draft(s):find(s['sessions'],self.sid)['preparation']={'drafts':{old_key:{'value':'尚未确认的虚构编辑','revision':3}},'omitted_optional':['project/'+eid+'/role/old_role/value']}
        self.lab.mutate(draft);before=copy.deepcopy(self.lab.state()['entries'])
        mapping['members'][0]['field_id']='project_role'
        self.app.install_mapping(self.sid,manifest,dict(mappings=[mapping]))
        plan=self.app.plan(self.sid);prep=find(self.lab.state()['sessions'],self.sid)['preparation']
        self.assertEqual(plan['payload'][0]['value'][0]['project_role'],'已确认的虚构角色')
        self.assertEqual(prep['drafts'][new_key]['value'],'尚未确认的虚构编辑')
        self.assertIsNone(prep['drafts'][old_key]['value'])
        self.assertIn('project/'+eid+'/role/project_role/value',prep['omitted_optional'])
        self.assertEqual(self.lab.state()['entries'],before)
