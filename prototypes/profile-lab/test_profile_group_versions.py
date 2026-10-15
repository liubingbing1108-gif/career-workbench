"""P27 record-sized saves and immutable version isolation."""
import copy,uuid,unittest
import test_profile_library as helpers
from profile_library import view_record
from profile_hierarchy import record_layout
from lab import find,LabError,default_version
class GroupVersionTests(unittest.TestCase):
 setUp=helpers.ProfileLibraryTests.setUp
 tearDown=helpers.ProfileLibraryTests.tearDown
 create=helpers.ProfileLibraryTests.create
 def save(self,e,values,**extra):
  return self.library.save(dict(request_id=str(uuid.uuid4()),entry_id=e['id'],edit_token=e['edit_token'],values=values,**extra))['record']
 def test_ordinary_and_group_saves_never_append_versions(self):
  e=self.create(company='初始公司',description='完整原文');self.assertEqual(len(e['record_versions']),1)
  for i in range(4):
   layout=record_layout(self.lab.state(),e);g=next(g for g in layout['groups'] if any(f['id']=='company' for f in g['fields']))
   e=self.save(e,{'company':'公司'+str(i)},layout=layout,scope={'kind':'group','id':g['id']})
   self.assertEqual(len(e['record_versions']),1);self.assertEqual(len(e.get('set_versions',[])),0)
  self.assertEqual(e['values']['company'],'公司3')
 def test_new_is_whole_record_and_updates_are_isolated(self):
  e=self.create(company='同一公司',description='第一版');e=self.save(e,{'description':'第二版'},mode='new');vid=e['set_versions'][-1]['id']
  self.assertEqual(default_version(self.lab.state(),e,'description')['content'],'第一版')
  e=self.save(e,{'company':'仅第二版改名'},set_id=vid)
  self.assertEqual(len(e['record_versions']),2);self.assertEqual(e['values']['company'],'同一公司')
  e=self.save(e,{'description':'第一版更新'})
  second=find(e['record_versions'],vid)
  self.assertEqual(find(self.lab.state()['versions'],second['field_versions']['description'])['content'],'第二版')
  self.assertEqual(find(self.lab.state()['answer_versions'],second['field_versions']['company'])['content'],'仅第二版改名')
 def test_new_structure_is_scoped_to_record_version(self):
  e=self.create(company='公司');layout=record_layout(self.lab.state(),e);g=next(g for g in layout['groups'] if any(f['id']=='company' for f in g['fields']));g['label']='新版组名';g['fields']=[{**f,'archived':f['id']=='company'} for f in g['fields']]
  e=self.save(e,{},mode='new',layout=layout);other=e['set_versions'][-1]
  self.assertEqual(next(item for item in other['layout']['groups'] if item['id']==g['id'])['label'],'新版组名')
  baseline=record_layout(self.lab.state(),e)
  self.assertFalse(any(f.get('archived') for g in baseline['groups'] for f in g['fields'] if f['id']=='company'))
 def test_stable_modules_have_no_versions_and_reject_new(self):
  for cat,typ in [('education',''),('language','ability'),('skills',''),('honors',''),('family','')]:
   e=self.create(cat,record_type=typ);self.assertFalse(e['versions_enabled']);self.assertEqual(e['record_versions'],[])
   e=self.save(e,{});self.assertFalse(e.get('set_versions'))
   before=self.lab.state()
   with self.assertRaises(LabError):self.save(e,{},mode='new')
   self.assertEqual(self.lab.state(),before)
 def test_only_allowed_modules_and_default_identity(self):
  for cat in ['employment','projects','campus','preferences','subjective']:
   e=self.create(cat);self.assertTrue(e['versions_enabled']);e=self.save(e,{},mode='new');vid=e['set_versions'][-1]['id']
   e=self.library.default(dict(entry_id=e['id'],edit_token=e['edit_token'],set_id=vid))
   self.assertEqual(e['profile_default_set_id'],vid)
 def test_fixed_major_rejects_new_but_child_can_be_added(self):
  tree=self.library.view()['tree']
  with self.assertRaises(LabError):self.library.tree(dict(action='create',kind='major',label='新大模块',revision=tree['revision']))
  result=self.library.tree(dict(action='create',kind='module',parent='personal',label='新子模块',revision=tree['revision']))
  self.assertEqual(result['node']['parent'],'personal')
 def test_deleting_current_default_selects_remaining_group(self):
  e=self.create(company='原公司');e=self.save(e,{'company':'新版公司'},mode='new');vid=e['set_versions'][-1]['id']
  e=self.library.default(dict(entry_id=e['id'],edit_token=e['edit_token'],set_id=vid))
  e=self.library.version(dict(entry_id=e['id'],edit_token=e['edit_token'],action='delete',version_id=vid))['record']
  self.assertEqual(e['profile_default_set_id'],'default');self.assertEqual(e['values']['company'],'原公司')
 def test_information_group_save_rejects_other_group_values(self):
  e=self.create(company='原公司',description='原描述');layout=record_layout(self.lab.state(),e);g=next(g for g in layout['groups'] if any(f['id']=='company' for f in g['fields']));before=self.lab.state()
  with self.assertRaises(LabError):self.save(e,{'description':'不应提交'},layout=layout,scope={'kind':'group','id':g['id']})
  self.assertEqual(self.lab.state(),before)
if __name__=='__main__':unittest.main()
