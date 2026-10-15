"""P28 regressions for deleted placeholders, partial saves and recoverable drafts."""
import copy,uuid,unittest
import test_profile_group_versions as helpers
from profile_library import token
from profile_hierarchy import record_layout,active_fields
from lab import LabError,find
class RecoveryTests(unittest.TestCase):
 setUp=helpers.GroupVersionTests.setUp
 tearDown=helpers.GroupVersionTests.tearDown
 create=helpers.GroupVersionTests.create
 save=helpers.GroupVersionTests.save
 def placeholder(self,layout,archived=True):
  layout['groups'].append(dict(id='unused',label='',archived=archived,fields=[dict(id='local_unused',label='')]))
 def test_deleted_blank_group_does_not_block_save_or_create_field(self):
  e=self.create('language',record_type='ability',language_name='虚构语言');l=record_layout(self.lab.state(),e);self.placeholder(l)
  e=self.save(e,{'language_name':'已编辑语言'},layout=l,field_definitions=[dict(id='local_unused',label='',type='text')])
  self.assertEqual(e['values']['language_name'],'已编辑语言');self.assertNotIn('local_unused',[f['id'] for f in self.lab.state()['fields']])
 def test_deleted_blank_field_does_not_block(self):
  e=self.create();l=record_layout(self.lab.state(),e);l['groups'][0]['fields'].append(dict(id='local_deleted',label='',archived=True))
  self.save(e,{'company':''},layout=l)
 def test_partial_save_ignores_unfinished_other_group(self):
  e=self.create(company='原值');l=record_layout(self.lab.state(),e);self.placeholder(l,False);g=next(g for g in l['groups'] if any(f['id']=='company' for f in g['fields']))
  e=self.save(e,{'company':'组内保存'},layout=l,scope=dict(kind='group',id=g['id']))
  self.assertEqual(e['values']['company'],'组内保存');self.assertNotIn('unused',[g['id'] for g in record_layout(self.lab.state(),e)['groups']])
 def test_visible_blank_name_gives_precise_error_and_keeps_state(self):
  e=self.create();l=record_layout(self.lab.state(),e);self.placeholder(l,False);before=self.lab.state()
  with self.assertRaisesRegex(LabError,'请填写信息组名称'):self.save(e,{},layout=l)
  self.assertEqual(before,self.lab.state())
 def test_new_blank_version_is_complete_and_preserves_original(self):
  e=self.create(company='原公司',description='原描述');l=record_layout(self.lab.state(),e)
  e=self.save(e,{fid:'' for fid in active_fields(l)},mode='new',layout=l)
  self.assertEqual(len(e['record_versions']),2);self.assertEqual(e['values']['company'],'原公司')
  for fid,vid in e['record_versions'][-1]['field_versions'].items():
   if fid in active_fields(l):
    version=next(v for v in self.lab.state()['versions']+self.lab.state()['answer_versions'] if v['id']==vid)
    self.assertEqual(version['content'],'')
 def test_archive_restore_keeps_draft_saveable_without_reviving_prior_deletions(self):
  e=self.create('language',record_type='ability',language_name='旧内容');other=self.create('language',record_type='ability')
  self.library.archive(dict(entry_id=other['id'],edit_token=other['edit_token'],archived=True))
  body=dict(id=e['id'],entry_id=e['id'],edit_token=e['edit_token'],layout=record_layout(self.lab.state(),e),values={'language_name':'编辑中'},field_versions={})
  self.library.draft(dict(key=e['id']+'/default',body=body,revision=0))
  for action in ('archive','restore'):
   self.library.tree(dict(id='language',action=action,revision=self.library.view()['tree']['revision']))
  state=self.lab.state();d=state['profile_drafts'][e['id']+'/default'];self.assertEqual(d['body']['values'],body['values']);self.assertTrue(find(state['entries'],other['id'])['profile_archived'])
  self.assertEqual(d['body']['edit_token'],token(state,find(state['entries'],e['id'])))
  saved=self.library.save(dict(**d['body'],request_id=str(uuid.uuid4())))['record'];self.assertEqual(saved['values']['language_name'],'编辑中')
if __name__=='__main__':unittest.main()
