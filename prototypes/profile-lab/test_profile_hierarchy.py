import copy
import unittest
import uuid
import test_profile_library as helpers
from profile_hierarchy import record_layout,mapping_fields,visible
from lab import find,LabError

class HierarchyTests(unittest.TestCase):
 setUp=helpers.ProfileLibraryTests.setUp
 tearDown=helpers.ProfileLibraryTests.tearDown
 create=helpers.ProfileLibraryTests.create
 request=helpers.ProfileLibraryTests.request
 def body(self,entry,layout,**values):
  return dict(request_id=str(uuid.uuid4()),entry_id=entry['id'],view_id=entry['id'],edit_token=entry['edit_token'],values=values,layout=layout,field_versions=entry['default_versions'])
 def local(self,entry,label='社交账号'):
  layout=record_layout(self.lab.state(),entry);fid='local_'+uuid.uuid4().hex
  layout['groups'].append(dict(id='custom',label='社交平台',fields=[dict(id=fid,label=label)]))
  body=self.body(entry,layout,**{fid:'虚构微信号'})
  body['field_definitions']=[dict(id=fid,label=label,type='text',aliases=['微信号'])]
  return body,fid
 def test_record_local_fields_names_and_partial_save(self):
  a=self.create(company='虚构甲',role='保留职位');b=self.create(company='虚构乙')
  body,fid=self.local(a);body['scope']={'kind':'group','id':'custom'};saved=self.library.save(body)
  state=self.lab.state();other=find(state['entries'],b['id'])
  self.assertEqual(find(state['entries'],a['id'])['values']['role'],'保留职位')
  self.assertFalse(visible(state,other,fid));self.assertNotIn(fid,other['values'])
  metadata=next(f for f in mapping_fields(state) if f['id']==fid)
  self.assertEqual(metadata['entry_id'],a['id']);self.assertEqual(metadata['record_contexts'][0]['path'][-1],'社交平台')
  self.assertNotIn('虚构微信号',str(metadata))
  self.assertNotEqual(saved['record']['edit_token'],a['edit_token'])
 def test_new_global_definition_does_not_reject_existing_draft(self):
  a=self.create(company='原公司');body=self.request(a,company='更新公司')
  self.lab.add_field(dict(label='新的结构字段',category='employment',type='text'))
  self.library.save(body)
  self.assertEqual(find(self.lab.state()['entries'],a['id'])['values']['company'],'更新公司')
 def test_deleting_group_preserves_versions_and_other_records(self):
  a=self.create(company='原公司');b=self.create(company='另一公司');layout=record_layout(self.lab.state(),a)
  target=next(g for g in layout['groups'] if any(f['id']=='company' for f in g['fields']));target['archived']=True
  before=copy.deepcopy(self.lab.state()['answer_versions']);self.library.save(self.body(a,layout))
  state=self.lab.state();self.assertEqual(state['answer_versions'],before)
  self.assertFalse(visible(state,find(state['entries'],a['id']),'company'));self.assertTrue(visible(state,find(state['entries'],b['id']),'company'))
 def test_contact_two_views_do_not_duplicate_facts(self):
  source=next(e for e in self.lab.state()['entries'] if e['category']=='contact')
  records=[e for e in self.library.view()['records'] if e['source_entry_id']==source['id']]
  self.assertEqual({e['layout']['title'] for e in records},{'联系方式','地址'})
  address=next(e for e in records if e['layout']['title']=='地址')
  body=self.body({**source,'edit_token':address['edit_token']},address['layout'],residence_city='虚构城市');body.update(edit_token=address['edit_token'],view_id=address['id'])
  self.library.save(body);self.assertEqual(find(self.lab.state()['entries'],source['id'])['values']['residence_city'],'虚构城市')
 def test_custom_modules_survive_restart_and_new_record_under_contact(self):
  tree=self.library.view()['tree'];major=dict(node={'id':'personal'},tree=tree)
  module=self.library.tree(dict(action='create',kind='module',parent=major['node']['id'],label='自定义子模块',revision=major['tree']['revision']))
  body=dict(request_id=str(uuid.uuid4()),category='additional',layout=dict(module_id=module['node']['id'],title='新资料',groups=[]),values={})
  saved=self.library.save(body);self.assertEqual(self.library.view()['records'][-1]['layout']['module_id'],module['node']['id'])
  self.library.tree(dict(action='archive',id=module['node']['id'],revision=module['tree']['revision']))
  self.assertTrue(find(self.lab.state()['entries'],saved['record']['id'])['profile_archived'])
  from profile_schema import install
  self.lab.mutate(install);self.assertTrue(find(self.lab.state()['profile_tree']['nodes'],module['node']['id'])['archived'])
 def test_parent_save_is_atomic_on_bad_child(self):
  a=self.create(company='原甲');b=self.create(company='原乙');one=self.body(a,record_layout(self.lab.state(),a),company='更新甲');two=self.body(b,record_layout(self.lab.state(),b),started='2025-99')
  before=self.lab.state()
  with self.assertRaises(LabError):self.library.tree(dict(action='save',id='employment',label='实习经历',revision=0,records=[one,two]))
  self.assertEqual(self.lab.state(),before)

 def test_custom_field_semantic_mapping_reads_and_writes_its_owner(self):
  from application import Application
  first=next(e for e in self.lab.state()['entries'] if e['category']=='additional')
  entry=self.library.save(dict(request_id=str(uuid.uuid4()),category='additional',values={},layout=dict(module_id='contact',title='社交信息',custom=True,groups=[])))['record']
  body,fid=self.local(entry);self.library.save(body)
  seen={}
  class Mapper:
   def map(self,website,fields):
    seen['field']=next(f for f in fields if f['id']==fid)
    return {'mappings':[{'website_id':'wechat','status':'mapped','category':'additional','field_id':fid,'members':[],'requirement':None}]}
  app=Application(self.lab,Mapper());session=self.lab.new_session()
  app.scan(session['id'],{'url':'https://example.com','fields':[{'id':'wechat','label':'微信号','required':True}]})
  self.assertEqual(app.plan(session['id'])['payload'][0]['value'],'虚构微信号')
  self.assertEqual(seen['field']['record_contexts'][0]['path'][1],'联系与地址')
  app.edit_answer(session['id'],'wechat','新的虚构微信号',mode='update')
  self.assertNotIn(fid,find(self.lab.state()['entries'],first['id'])['values'])
  self.assertEqual(find(self.lab.state()['entries'],entry['id'])['values'][fid],'虚构微信号')
  self.assertEqual(app.plan(session['id'])['payload'][0]['value'],'新的虚构微信号')
 def test_save_first_field_of_new_record_keeps_its_module(self):
  fid='local_'+uuid.uuid4().hex
  data=dict(request_id=str(uuid.uuid4()),category='additional',values={fid:'虚构值'},layout=dict(module_id='contact',title='新联系方式',custom=True,groups=[dict(id='custom',label='社交平台',fields=[dict(id=fid,label='微信号')])]),field_definitions=[dict(id=fid,label='微信号',type='text')],scope=dict(kind='field',id=fid))
  result=self.library.save(data)
  record=next(e for e in self.library.view()['records'] if e['id']==result['view_id'])
  self.assertEqual(record['layout']['module_id'],'contact')
  self.assertEqual(record['layout']['title'],'新联系方式')

 def test_pre_hierarchy_draft_token_survives_metadata_only_upgrade(self):
  import hashlib,json
  entry=self.create(company='旧记录');state=self.lab.state();raw=find(state['entries'],entry['id'])
  versions=[v for store in ('versions','answer_versions') for v in state[store] if v['entry_id']==entry['id']]
  body=self.request(entry,company='旧草稿继续保存')
  body['edit_token']=hashlib.sha256(json.dumps([raw,versions],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
  self.library.save(body)
  self.assertEqual(find(self.lab.state()['entries'],entry['id'])['values']['company'],'旧草稿继续保存')

if __name__=='__main__':unittest.main()
