import copy
import tempfile
import unittest
from lab import Lab, LabError, find
from profile_library import ProfileLibrary, token
from profile_migration import prepare, state_hash
from profile_pending import resolve, view
from profile_contract import current_values
from profile_trash import archive, expire, RETENTION


class PendingChoices(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name)
        old=self.lab.state();entry=next(e for e in old['entries'] if e['category']=='basic')
        entry['values']['name']='旧姓名甲'
        old['answer_versions'].append(dict(id='old_name',entry_id=entry['id'],field_id='name',content='旧姓名乙',revision=1,source={},name='旧值'))
        self.lab.mutate(lambda s:s.update(prepare(old,1000)[0]));self.eid=entry['id']
    def tearDown(self):self.lab.db.close();self.tmp.cleanup()
    def args(self, **extra):
        item=next(p for p in view(self.lab.state()) if p.get('field_id')=='name')
        return dict(request_id='choose-name',id=item['id'],edit_token=item['edit_token'],confirmed=True,value='确认姓名',**extra)
    def test_explicit_choice_preserves_evidence_replay_and_stale_guard(self):
        before=self.lab.state();args=self.args()
        result=self.lab.mutate(lambda s:resolve(s,args))
        self.assertEqual(result,self.lab.mutate(lambda s:resolve(s,args)))
        after=self.lab.state();self.assertEqual(before['profile_legacy_evidence'],after['profile_legacy_evidence'])
        self.assertEqual(current_values(after,find(after['entries'],self.eid))['name'],'确认姓名')
        with self.assertRaises(LabError):self.lab.mutate(lambda s:resolve(s,{**args,'request_id':'different'}))
    def test_concurrent_current_edit_cannot_be_overwritten_by_old_choice(self):
        args=self.args();before=self.lab.state();e=find(before['entries'],self.eid)
        ProfileLibrary(self.lab).save(dict(request_id='manual',entry_id=e['id'],edit_token=token(before,e),values={'name':'后来更正'}))
        stable=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.lab.mutate(lambda s:resolve(s,args))
        self.assertEqual(state_hash(self.lab.state()),stable)
    def test_preserve_does_not_choose_answer(self):
        self.lab.mutate(lambda s:resolve(s,self.args(action='preserve')))
        state=self.lab.state();self.assertEqual(current_values(state,find(state['entries'],self.eid))['name'],'')
    def test_old_write_endpoints_fail_without_mutation(self):
        before=state_hash(self.lab.state())
        for fn in [lambda:self.lab.save_profile([dict(entry_id=self.eid,field_id='name',value='绕过')]),lambda:self.lab.create_version(self.eid,'name','绕过'),lambda:self.lab.set_default(self.eid,'name','old_name'),lambda:self.lab.select_version('none','old_name')]:
            with self.assertRaises(LabError):fn()
            self.assertEqual(state_hash(self.lab.state()),before)
    def test_custom_field_scope_and_full_catalog_duplicate_lookup(self):
        state=self.lab.state();e=find(state['entries'],self.eid)
        args=dict(entry_id=e['id'],edit_token=token(state,e),label='虚构新属性',confirmed_new_attribute=True,type='text')
        field=self.lab.add_field(args);self.assertEqual(field['entry_id'],e['id']);self.assertEqual(field['value_role'],'fact')
        state=self.lab.state();e=find(state['entries'],self.eid)
        with self.assertRaises(LabError):self.lab.add_field({**args,'edit_token':token(state,e),'label':'姓名'})
    def test_expired_object_disappears_from_flat_view(self):
        library=ProfileLibrary(self.lab)
        record=library.save(dict(request_id='object',category='education',values={'school':'虚构学校'}))['record']
        def delete(state):
            e=find(state['entries'],record['id']);archive(state,dict(entry_id=e['id'],archived=True,edit_token=token(state,e)),now=1000);expire(state,now=1000+RETENTION)
        self.lab.mutate(delete)
        self.assertNotIn(record['id'],[e['id'] for e in library.view()['records']])

    def legacy_record(self, category='language', archived=False):
        old=self.lab.state()
        old.pop('profile_contract',None);old['profile_pending']=[]
        old['entries']=[dict(id='unknown',category=category,record_type='unknown',profile_archived=archived,
                             values={'exam_name':'虚构考试','language_score':'520','exam_level':'优秀'} if category=='language' else {},sources={},default_versions={})]
        old['answer_versions']=[dict(id='other_score',entry_id='unknown',field_id='language_score',content='580',revision=1,source={},name='旧结果')]
        self.lab.mutate(lambda s:s.update(prepare(old,1000)[0]))
        item=next(p for p in view(self.lab.state()) if p['kind']=='record_type')
        return dict(request_id='classify',id=item['id'],edit_token=item['edit_token'],confirmed=True,record_type='exam' if category=='language' else 'work')

    def test_confirmed_type_defers_exam_results_and_preserves_unrelated_state(self):
        args=self.legacy_record();before=self.lab.state()
        result=self.lab.mutate(lambda s:resolve(s,args))
        self.assertEqual(result,self.lab.mutate(lambda s:resolve(s,args)))
        state=self.lab.state();entry=find(state['entries'],'unknown')
        self.assertEqual(current_values(state,entry)['language_score'],'')
        self.assertEqual(current_values(state,entry)['exam_level'],'')
        self.assertEqual(state['profile_legacy_evidence'],before['profile_legacy_evidence'])
        self.assertEqual(state['fields'],before['fields'])
        self.assertEqual([e for e in state['entries'] if e['id']!='unknown'],[e for e in before['entries'] if e['id']!='unknown'])
        sitting=next(p for p in view(state) if p['kind']=='exam_sitting')
        self.assertEqual(len(sitting['bundles']),2)
        self.lab.mutate(lambda s:resolve(s,dict(request_id='result',id=sitting['id'],edit_token=sitting['edit_token'],confirmed=True,bundle_id='field:other_score')))
        state=self.lab.state();self.assertEqual(current_values(state,find(state['entries'],'unknown'))['language_score'],'580')

    def test_type_confirmation_cannot_supply_answers_to_bypass_pending_choice(self):
        args=self.legacy_record();before=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.lab.mutate(lambda s:resolve(s,{**args,'values':{'language_score':'999'}}))
        self.assertEqual(state_hash(self.lab.state()),before)

    def test_unknown_portfolio_type_requires_choice(self):
        args=self.legacy_record(category='portfolio');self.lab.mutate(lambda s:resolve(s,args))
        entry=find(self.lab.state()['entries'],'unknown')
        self.assertEqual(entry['record_type'],'work');self.assertFalse(entry.get('legacy_only'))

    def test_archived_type_choice_does_not_restore_and_enters_retention(self):
        args=self.legacy_record(archived=True);self.lab.mutate(lambda s:resolve(s,args))
        state=self.lab.state();self.assertTrue(find(state['entries'],'unknown')['profile_archived'])
        self.assertEqual(len([p for p in state['profile_trash'] if p.get('entry_id')=='unknown']),1)
        self.assertNotIn('unknown',[e['id'] for e in ProfileLibrary(self.lab).view()['records'] if not e.get('profile_archived')])

    def test_each_historical_attempt_is_checked_even_when_latest_has_evidence(self):
        old=self.lab.state();old.pop('profile_contract',None);old['profile_pending']=[]
        proven=dict(id='proven',confirmed_materials={'values':{'fiction':'actual'}})
        old['sessions']=[dict(id='history',preparation=dict(execution=proven,execution_history=[dict(id='missing',status='complete'),dict(id='earlier',confirmed_materials={'values':{'fiction':'earlier'}})]))]
        before=copy.deepcopy(old);state,_=prepare(old,1000)
        pending=[p for p in state['profile_pending'] if p['kind']=='historical_evidence']
        self.assertEqual(len(pending),1);self.assertEqual(pending[0]['attempt_key'],'history:0')
        self.assertEqual(len(state['sessions'][0]['profile_historical_materials']),2)
        self.assertEqual(old,before)
        entry=find(state['entries'],self.eid);entry.update(profile_archived=True)
        state['profile_trash']=[dict(id='object:'+self.eid,kind='object',entry_id=self.eid,deleted_at=1,expires_at=2)]
        expire(state,now=3)
        self.assertFalse(entry.get('purged'));self.assertTrue(state['profile_trash'][0].get('cleanup_blocked'))

    def test_missing_history_holds_only_objects_present_at_migration(self):
        old=self.lab.state();old.pop('profile_contract',None);old['profile_pending']=[]
        old['sessions']=[dict(id='history',preparation=dict(execution=dict(id='missing',status='failed')))]
        state,_=prepare(old,1000)
        old_entry=find(state['entries'],self.eid)
        new_entry=copy.deepcopy(old_entry);new_entry['id']='created_after_migration'
        state['entries'].append(new_entry)
        for entry in (old_entry,new_entry):
            entry['profile_archived']=True
            state.setdefault('profile_trash',[]).append(dict(id='object:'+entry['id'],kind='object',entry_id=entry['id'],deleted_at=1,expires_at=2))
        expire(state,now=3)
        self.assertFalse(old_entry.get('purged'))
        self.assertTrue(new_entry.get('purged'))

    def test_retired_category_custom_definitions_remain_evidence_not_new_catalog(self):
        from resume_skill import catalog
        old=self.lab.state();old.pop('profile_contract',None)
        old['fields'].append(dict(id='old_social_custom',category='social',label='旧平台扩展',type='text',aliases=[],options=[]))
        state,_=prepare(old,1000)
        self.assertTrue(find(state['fields'],'old_social_custom')['legacy_preserved'])
        self.assertNotIn('old_social_custom',{f['id'] for f in catalog(state['fields'])})
        self.assertIn('old_social_custom',{f['id'] for f in state['profile_legacy_evidence']['fields']})


if __name__=='__main__':unittest.main()
