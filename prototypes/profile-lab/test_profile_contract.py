"""Fictional, isolated acceptance of the refactored storage contract."""
import copy
import tempfile
import unittest
from lab import Lab, LabError, validate_value
from profile_library import ProfileLibrary, token
from profile_contract import catalog, current_values, fields_for
from profile_migration import prepare, state_hash
from profile_current import save_values, link_exams
from profile_trash import archive, version_action, expire, RETENTION


class CurrentProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.lab = Lab(self.temp.name)
        self.lab.mutate(lambda state:state.update(prepare(state, 1000)[0]))
        self.library = ProfileLibrary(self.lab)
        self.sequence = 0

    def tearDown(self):
        self.lab.db.close();self.temp.cleanup()

    def save(self, cat='employment', values=None, entry=None, **kwargs):
        self.sequence += 1
        data = dict(request_id=str(self.sequence), category=cat, values=values or {}, **kwargs)
        if entry:data.update(entry_id=entry['id'], edit_token=token(self.lab.state(), next(e for e in self.lab.state()['entries'] if e['id']==entry['id'])))
        return self.library.save(data)['record']

    def test_catalog_decision_audit_covers_all_262_rows_and_active_fields(self):
        import json
        from pathlib import Path
        audit=json.loads(Path(__file__).with_name('profile_catalog_audit.json').read_text())['rows']
        self.assertEqual(len(audit),262);self.assertEqual(len({r['audit_id'] for r in audit}),262)
        targets={f for row in audit for f in row['current_fields']}
        self.assertFalse({f['id'] for f in catalog()}-targets)
        for row in audit:
            if row['status']=='excluded':self.assertEqual(row['current_fields'],[])

    def test_catalog_removed_presets_and_date_semantics(self):
        fields = {f['id']:f for f in catalog()}
        for fid in ['exam_date','education_description','project_process','project_tools','backup_phone','statement_content','doi']:
            self.assertNotIn(fid, fields)
        self.assertEqual(fields['exam_level']['label'], '报考级别')
        self.assertIn('obtained_date', fields)
        self.assertEqual(sum(f['value_role']=='expression' for f in fields.values()), 7)
        self.assertEqual([f['id'] for f in fields.values() if f['category']=='language' and f['record_types']==['ability']],
                         ['language_name','language_level','listening','speaking','reading','writing','is_native'])

    def test_shared_facts_partial_expression_and_type_change(self):
        e=self.save(values={'company':'示例单位','employment_type':'实习','description':'完整','responsibilities':'职责A','achievements':'成果A'})
        e=self.save(entry=e, values={'responsibilities':'职责B'}, mode='new', set_id='default', name='精简')
        version=e['record_versions'][-1]['id']
        e=self.save(entry=e,values={'company':'更正单位','employment_type':'全职','achievements':'成果B'},set_id=version)
        state=self.lab.state();entry=next(x for x in state['entries'] if x['id']==e['id'])
        self.assertEqual(len(e['record_versions']),2)
        self.assertEqual(current_values(state,entry,'default')['responsibilities'],'职责A')
        self.assertEqual(current_values(state,entry,version)['description'],'完整')
        self.assertEqual(current_values(state,entry,version)['achievements'],'成果B')
        self.assertEqual(current_values(state,entry,'default')['company'],'更正单位')
        self.assertEqual(entry['profile_default_set_id'],'default')

    def test_empty_version_does_not_borrow_and_missing_default_is_empty(self):
        e=self.save(values={'description':'完整','achievements':'成果'})
        # Explicit blank version: no source ID, default deliberately cleared first.
        self.library.default(dict(entry_id=e['id'],edit_token=e['edit_token'],set_id=None))
        e=self.save(entry=e,mode='new',values={},name='空白')
        version=e['record_versions'][-1]['id'];state=self.lab.state();entry=next(x for x in state['entries'] if x['id']==e['id'])
        self.assertEqual(current_values(state,entry,version)['description'],'')
        self.assertEqual(current_values(state,entry)['description'],'')
        with self.assertRaises(LabError):self.save(entry=e,values={'description':'不能猜版本'})

    def test_nonversioned_and_stable_blank_type(self):
        e=self.save('honors',{'award_name':'示例奖项','award_details':'旧说明'})
        with self.assertRaises(LabError):self.save('honors',{'award_details':'新说明'},entry=e,mode='new')
        e=self.save('honors',{'award_details':'新说明'},entry=e)
        self.assertFalse(e['versions_enabled'])
        e=self.save('language',{},record_type='exam')
        self.assertEqual(e['record_type'],'exam')
        self.assertFalse(any(f['id']=='language_level' for f in fields_for(self.lab.state(),e)))

    def test_idempotent_and_concurrent_save(self):
        request=dict(request_id='same',category='projects',values={'project_name':'样例项目'})
        result=self.library.save(request)
        self.assertEqual(self.library.save(request),result)
        with self.assertRaises(LabError):self.library.save({**request,'values':{'project_name':'另一个'}})
        e=result['record'];self.save('projects',{'project_name':'更正'},entry=e)
        with self.assertRaises(LabError):self.library.save(dict(request_id='stale',entry_id=e['id'],edit_token=e['edit_token'],values={'project_name':'过期'}))

    def test_unique_documents_and_exams(self):
        self.save('identity_documents',{'identity_type':'护照'})
        with self.assertRaises(LabError):self.save('identity_documents',{'identity_type':'护照'})
        self.save('language',{'exam_name':'CET6','language_score':'520.5'},record_type='exam')
        with self.assertRaises(LabError):self.save('language',{'exam_name':'CET6','language_score':'600'},record_type='exam')

    def test_types_and_blank_optional(self):
        fields={f['id']:f for f in catalog()}
        validate_value(fields['identity_valid_until'],'长期有效')
        validate_value(fields['skill_years'],'2.5')
        validate_value(fields['project_team_size'],'')
        with self.assertRaises(LabError):validate_value(fields['project_team_size'],'2.5')
        with self.assertRaises(LabError):validate_value(fields['language_level'],'优秀')
        validate_value(fields['exam_components'],'[{"name":"听力","score":"120.5","scale":"249"}]')
        with self.assertRaises(LabError):validate_value(fields['exam_components'],'[{"score":"NaN"}]')

    def test_atomic_exam_links_and_updates(self):
        exam=self.save('language',{'exam_name':'CET6','exam_language':'英语','language_score':'500'},record_type='exam')
        ability=self.save('language',{'language_name':'英语'},record_type='ability',exam_ids=[exam['id']],links_revision=0)
        with self.assertRaises(LabError):self.save('language',{'language_name':'法语'},entry=ability)
        self.assertEqual(len([l for l in self.lab.state()['language_exam_links'] if l['active']]),1)
        before=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.save('language',{'language_level':'熟练'},entry=ability,exam_ids=[exam['id']],links_revision=1,confirm_exam_updates=True,exam_edits=[{'entry_id':exam['id'],'edit_token':'stale','values':{'language_score':'600'}}])
        self.assertEqual(state_hash(self.lab.state()),before)

    def test_new_exam_and_ability_save_are_atomic_and_duplicate_rolls_back(self):
        ability=self.save('language',{'language_name':'英语'},record_type='ability')
        args=dict(entry=ability,exam_ids=[],links_revision=0,confirm_exam_updates=True,new_exams=[{'exam_name':'示例考试','exam_language':'英语','language_score':'520'}])
        saved=self.save('language',{'language_level':'熟练'},**args)
        state=self.lab.state();exams=[e for e in state['entries'] if e.get('record_type')=='exam']
        self.assertEqual(len(exams),1);self.assertTrue(any(l['active'] and l['exam_id']==exams[0]['id'] for l in state['language_exam_links']))
        before=state_hash(state)
        with self.assertRaises(LabError):self.save('language',{'language_level':'精通'},**{**args,'entry':saved,'links_revision':1})
        self.assertEqual(state_hash(self.lab.state()),before)

    def test_delete_default_and_restore_never_choose_remaining(self):
        e=self.save(values={'description':'原版'})
        e=self.save(entry=e,values={'description':'新版'},mode='new',set_id='default')
        def remove(state):
            entry=next(x for x in state['entries'] if x['id']==e['id'])
            version_action(state,entry,dict(version_id='default',action='delete',edit_token=token(state,entry)),now=10)
            self.assertIsNone(entry['profile_default_set_id'])
            version_action(state,entry,dict(version_id='default',action='restore',edit_token=token(state,entry)),now=11)
            self.assertIsNone(entry['profile_default_set_id'])
        self.lab.mutate(remove)

    def test_trash_exact_deadline_repeat_no_extension(self):
        e=self.save('honors',{'award_name':'样例'})
        state=self.lab.state()
        args=dict(entry_id=e['id'],archived=True,edit_token=token(state,next(x for x in state['entries'] if x['id']==e['id'])))
        archive(state,args,now=10);archive(state,args,now=20)
        self.assertEqual(state['profile_trash'][0]['expires_at'],10+RETENTION)
        entry=next(x for x in state['entries'] if x['id']==e['id'])
        with self.assertRaises(LabError):archive(state,dict(entry_id=e['id'],archived=False,edit_token=token(state,entry)),now=10+RETENTION)
        expire(state,now=10+RETENTION)
        self.assertTrue(entry['purged'])

    def test_migration_preserves_custom_and_quarantines_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy=Lab(directory)
            state=legacy.state();entry=next(e for e in state['entries'] if e['category']=='basic')
            state['fields'].append(dict(id='custom_x',category='basic',label='自定义事实',type='text',options=[],aliases=[]))
            entry['values']['custom_x']='保留'
            state['answer_versions'].extend([dict(id='a',entry_id=entry['id'],field_id='name',content='旧名',revision=1),dict(id='b',entry_id=entry['id'],field_id='name',content='新名',revision=1)])
            before=copy.deepcopy(state);migrated,report=prepare(state,100)
            self.assertEqual(state,before)
            person=next(e for e in migrated['entries'] if e['id']==entry['id'])
            self.assertEqual(current_values(migrated,person)['custom_x'],'保留')
            self.assertEqual(current_values(migrated,person)['name'],'')
            self.assertTrue(any(p.get('field_id')=='name' for p in migrated['profile_pending']))
            self.assertEqual(prepare(migrated,200)[0],migrated)
            legacy.db.close()


if __name__ == '__main__':unittest.main()
