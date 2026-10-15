"""P26 version metadata/deletion regressions, isolated fictional records."""
import copy
import unittest
import test_profile_library as helpers
from lab import LabError,find,default_version

class ProfileVersionTests(unittest.TestCase):
 setUp=helpers.ProfileLibraryTests.setUp
 tearDown=helpers.ProfileLibraryTests.tearDown
 create=helpers.ProfileLibraryTests.create
 def operation(self,entry,action,version_id,**kwargs):
  return self.library.version(dict(entry_id=entry['id'],edit_token=entry['edit_token'],action=action,version_id=version_id,**kwargs))['record']
 def test_rename_record_and_field_versions_only_changes_metadata(self):
  e=self.create(company='虚构公司',description='原始完整描述');e=self.library.save(dict(request_id='new-rename',entry_id=e['id'],edit_token=e['edit_token'],values={},mode='new'))['record'];before=copy.deepcopy(self.lab.state())
  e=self.operation(e,'rename','default',name='通用版')
  self.assertEqual(e['record_versions'][0]['name'],'通用版')
  e=self.operation(e,'rename',e['set_versions'][0]['id'],name='产品版')
  e=self.operation(e,'rename',e['default_versions']['description'],field_id='description',name='简洁版')
  after=self.lab.state();self.assertEqual(e['values'],find(before['entries'],e['id'])['values'])
  self.assertEqual(e['default_versions'],find(before['entries'],e['id'])['default_versions'])
  self.assertEqual([v['content'] for v in after['versions']],[v['content'] for v in before['versions']])
 def test_delete_record_choices_preserves_field_facts_and_original_refs(self):
  e=self.create(company='虚构公司');e=self.library.save(dict(request_id='new-delete',entry_id=e['id'],edit_token=e['edit_token'],values={},mode='new'))['record'];sets=copy.deepcopy(e['set_versions']);values=copy.deepcopy(e['values'])
  e=self.operation(e,'delete',sets[0]['id']);e=self.operation(e,'delete','default')
  self.assertEqual([v for v in e['record_versions'] if not v['id'].startswith('field:')],[])
  self.assertEqual(e['values'],values);self.assertEqual(e['set_versions'][0]['field_versions'],sets[0]['field_versions'])
 def test_delete_default_field_falls_back_then_clears_last_and_keeps_explicit_reference(self):
  e=self.create(company='虚构公司');original=e['default_versions']['company']
  result=self.library.field_version(dict(entry_id=e['id'],edit_token=e['edit_token'],field_id='company',content='备用公司',name='版本2'));e=result['record']
  sid=self.lab.new_session()['id']
  self.lab.mutate(lambda s:find(s['sessions'],sid).update(website={'contract_version':2,'mappings':[{'website_id':'company','category':'employment','requirement':{'group':'job'}}]}))
  e=self.operation(e,'delete',original,field_id='company');s=self.lab.state()
  self.assertEqual(default_version(s,e,'company')['content'],'备用公司')
  self.assertEqual(find(s['sessions'],sid)['scoped_versions']['job'][e['id']+'/company'],original)
  e=self.operation(e,'delete',result['version']['id'],field_id='company')
  self.assertIsNone(default_version(self.lab.state(),e,'company'));self.assertEqual(e['values']['company'],'')
  self.assertEqual(len([v for v in self.lab.state()['answer_versions'] if v['field_id']=='company' and v['entry_id']==e['id']]),2)
 def test_stale_token_wrong_owner_and_empty_name_rejected_atomically(self):
  e=self.create(company='甲');other=self.create(company='乙');before=self.lab.state()
  for payload in (dict(version_id=other['default_versions']['company'],field_id='company',action='delete'),dict(version_id='default',action='rename',name=' '),dict(version_id='default',action='delete',edit_token='stale')):
   with self.assertRaises(LabError):self.library.version(dict(entry_id=e['id'],edit_token=e['edit_token'])|payload)
   self.assertEqual(self.lab.state(),before)
if __name__=='__main__':unittest.main()
