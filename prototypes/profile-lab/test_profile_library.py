"""P1–P24 regressions: all records/files are fictional, temporary and local."""
import copy
import tempfile
import unittest
import uuid
from lab import Lab,LabError,find,default_version
from profile_library import ProfileLibrary
from profile_schema import FIELDS,fields_for,install

class ProfileLibraryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.lab=Lab(self.temp.name);self.library=ProfileLibrary(self.lab)
 def tearDown(self):self.lab.db.close();self.temp.cleanup()
 def create(self,cat='employment',record_type='',**values):
  fields=fields_for(self.lab.state(),dict(category=cat,record_type=record_type,values={}))
  return self.library.save(dict(request_id=str(uuid.uuid4()),category=cat,record_type=record_type,values={f['id']:values.get(f['id'],'') for f in fields}))['record']
 def request(self,entry,**patch):
  values={f['id']:(default_version(self.lab.state(),entry,f['id']) or {}).get('content',entry['values'].get(f['id'],'')) for f in fields_for(self.lab.state(),entry)}
  values.update(patch)
  return dict(request_id=str(uuid.uuid4()),entry_id=entry['id'],edit_token=entry['edit_token'],values=values,field_versions=entry.get('default_versions',{}))
 def test_contract_is_complete_idempotent_and_retains_existing_data(self):
  state=self.lab.state();self.assertEqual(len(state['profile_modules']),14);self.assertGreater(len(FIELDS),200)
  e=self.create(company='虚构甲',description='完整描述\n第二段 20%')
  before=self.lab.state();self.lab.mutate(install);after=self.lab.state()
  for key in ('entries','versions','answer_versions','files','sessions'):self.assertEqual(before[key],after[key])
  ids={f['id'] for f in after['fields']};self.assertTrue({'id_photo','life_photo','double_degree','graduation_date'}<=ids)
  self.assertFalse(any('预计毕业'==f['label'] for f in after['fields']))
 def test_atomic_save_only_one_record_stale_update_and_idempotent_retry(self):
  a=self.create(company='虚构甲');b=self.create(company='虚构乙')
  body=self.request(a,role='岗位更新');self.library.save(body);self.library.save(body)
  self.assertEqual(find(self.lab.state()['entries'],b['id'])['values']['company'],'虚构乙')
  before=self.lab.state()
  with self.assertRaises(LabError):self.library.save(self.request(a,role='过期页面'))
  self.assertEqual(self.lab.state(),before)
  current=next(e for e in self.library.view()['records'] if e['id']==a['id']);body=self.request(current,role='不应保存',started='2027-02-30')
  with self.assertRaises(LabError):self.library.save(body)
  self.assertEqual(self.lab.state(),before)
 def test_new_version_keeps_defaults_and_explicit_default_works(self):
  a=self.create(company='虚构甲',description='原文');body=self.request(a,description='新表达');body['mode']='new'
  saved=self.library.save(body);entry=find(self.lab.state()['entries'],a['id'])
  self.assertEqual(entry['default_versions'],a['default_versions'])
  self.assertEqual(default_version(self.lab.state(),entry,'description')['content'],'原文')
  refs=entry['set_versions'][-1]['field_versions']
  self.library.default(dict(entry_id=a['id'],edit_token=saved['record']['edit_token'],field_versions=refs))
  self.assertEqual(default_version(self.lab.state(),find(self.lab.state()['entries'],a['id']),'description')['content'],'新表达')
 def test_new_draft_is_not_a_record_and_survives_reopen(self):
  before=self.lab.state()['entries'];key='draft_example/default'
  result=self.library.draft(dict(key=key,body=dict(isNew=True,category='employment',values={'company':'未确认'}),revision=0))
  self.lab.db.close();self.lab=Lab(self.temp.name);self.library=ProfileLibrary(self.lab)
  self.assertEqual(self.lab.state()['entries'],before);self.assertIn(key,self.library.view()['drafts'])
  with self.assertRaises(LabError):self.library.draft(dict(key=key,body={},revision=0))
  self.library.draft(dict(key=key,discard=True,revision=result['revision']));self.assertNotIn(key,self.library.view()['drafts'])
 def test_field_version_does_not_save_other_fields_and_rejects_stale_token(self):
  entry=self.create(company='虚构甲',description='完整原文')
  result=self.library.field_version(dict(entry_id=entry['id'],edit_token=entry['edit_token'],field_id='description',content='另一版完整原文',name='岗位版'))
  current=find(self.lab.state()['entries'],entry['id'])
  self.assertEqual(current['default_versions'],entry['default_versions'])
  self.assertEqual(current['values'],entry['values'])
  self.assertEqual(result['version']['content'],'另一版完整原文')
  with self.assertRaises(LabError):self.library.field_version(dict(entry_id=entry['id'],edit_token=entry['edit_token'],field_id='company',content='过期写入'))
 def test_legacy_scalar_mapping_preserves_original_record_and_archived_reference(self):
  from application import Application
  old=self.create('preferences',preferred_role='旧岗位意向')
  self.create('preferences',preferred_role='新增意向')
  session=self.lab.new_session()
  def legacy(state):
   state['profile_legacy_single_entries']={'preferences':[old['id']]}
   find(state['sessions'],session['id'])['website']={'contract_version':2,'url':'https://example.com','fields':[{'id':'intent','label':'意向岗位','required':True}],'mappings':[{'website_id':'intent','status':'mapped','category':'preferences','field_id':'preferred_role','requirement':None}]}
  self.lab.mutate(legacy)
  app=Application(self.lab);before=copy.deepcopy(self.lab.state()['sessions'])
  self.assertEqual(app.plan(session['id'])['payload'][0]['value'],'旧岗位意向')
  self.assertEqual(before,self.lab.state()['sessions'])
  self.library.archive(dict(entry_id=old['id'],edit_token=old['edit_token'],archived=True))
  self.assertEqual(app.plan(session['id'])['payload'][0]['value'],'旧岗位意向')
  self.assertIn(old['id'],find(self.lab.state()['sessions'],session['id'])['archived_profile_refs'])
 def test_fulltime_conversion_does_not_infer_unknown_or_double_degree(self):
  from application import website_value
  self.assertEqual(website_value('全日制','is_full_time'),'是')
  self.assertEqual(website_value('非全日制','is_full_time'),'否')
  self.assertEqual(website_value('未知','is_full_time'),'')
  self.assertEqual(website_value('辅修','is_full_time'),'')
 def test_subtypes_boolean_and_independent_photos(self):
  ability=self.create('language','ability',language_name='法语');exam=self.create('language','exam',exam_name='虚构考试',language_score='88')
  self.assertNotEqual(ability['id'],exam['id']);self.assertNotIn('language_score',ability['values']);self.assertNotIn('language_level',exam['values'])
  a=self.create('education',school='虚构大学',double_degree='');self.assertEqual(a['values']['double_degree'],'')
  with self.assertRaises(LabError):self.library.save(self.request(a,double_degree='推测是'))
  one=self.library.upload_attachment('same.png',b'fake image one');two=self.library.upload_attachment('same.png',b'fake image two')
  self.assertNotEqual(one['id'],two['id']);self.assertEqual(self.lab.file_bytes(one['id'])[1],b'fake image one')
  basic=next(e for e in self.library.view()['records'] if e['category']=='basic');saved=self.library.save(self.request(basic,life_photo=one['id'],id_photo=two['id']))
  self.assertEqual(saved['record']['values']['life_photo'],one['id']);self.assertEqual(saved['record']['values']['id_photo'],two['id'])
 def test_archive_restore_preserves_versions_and_new_selection_excludes(self):
  a=self.create(company='虚构甲');versions=copy.deepcopy(self.lab.state()['answer_versions'])
  archived=self.library.archive(dict(entry_id=a['id'],edit_token=a['edit_token'],archived=True))
  self.assertTrue(archived['profile_archived']);self.assertEqual(self.lab.state()['answer_versions'],versions)
  sid=self.lab.new_session()['id'];self.assertEqual(self.lab.materials(sid)['entries']['employment'],[])
  self.library.archive(dict(entry_id=a['id'],edit_token=archived['edit_token'],archived=False))
  self.assertEqual(len(self.lab.materials(sid)['entries']['employment']),1)
 def import_group(self,cat,values):
  from lab import uid
  pid=uid('import')
  def add(state):
   state['imports'].append(dict(id=pid,filename='虚构.txt',semantic=True,status='完成',candidates=[dict(id=uid('candidate'),field_id=k,label=find(state['fields'],k)['label'],type=find(state['fields'],k)['type'],category=cat,group='one',value=v,existing='',status='新增',saved=False,source={'filename':'虚构.txt'}) for k,v in values.items()]))
  self.lab.mutate(add);return find(self.lab.state()['imports'],pid)
 def test_award_missing_date_requires_identity_then_merge_preserves_date(self):
  a=self.create('honors',award_name='虚构奖',award_date='2024');b=self.create('honors',award_name='虚构奖',award_date='2025')
  preview=self.import_group('honors',{'award_name':'虚构奖','award_details':'补充原文'})
  rows=preview['candidates'];self.assertTrue(all(c['identity_review'] for c in rows));self.assertEqual(set(rows[0]['identity_choices']),{a['id'],b['id']})
  with self.assertRaises(LabError):self.lab.resolve_import([dict(candidate_id=c['id'],mode='new') for c in rows],{preview['id']:preview['revision']})
  self.library.import_identity(dict(import_id=preview['id'],group='one',entry_id=a['id'],revision=preview['revision']))
  inc=self.lab.increments();self.lab.resolve_import([dict(candidate_id=c['id'],mode='new') for c in inc['candidates']],inc['revisions'])
  self.assertEqual(len([e for e in self.lab.state()['entries'] if e['category']=='honors']),2)
  self.assertEqual(find(self.lab.state()['entries'],a['id'])['values']['award_date'],'2024')
 def test_employment_end_date_conflict_waits_for_identity_confirmation(self):
  a=self.create(company='虚构甲',role='实习',started='2025-01',ended='2025-03')
  preview=self.import_group('employment',dict(company='虚构甲',role='实习',started='2025-01',ended='2025-04'))
  self.assertTrue(all(c['identity_review'] for c in preview['candidates']))
  self.assertEqual(len([e for e in self.lab.state()['entries'] if e['category']=='employment']),1)

if __name__=='__main__':unittest.main()
