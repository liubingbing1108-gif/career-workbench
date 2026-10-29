import copy
import tempfile
import unittest
from application import Application
from lab import Lab,LabError,find
from mapping_relations import update as relation_update
from profile_contract import current_values,fields_for
from profile_current import add_custom_field
from profile_fields import preview,update
from profile_library import ProfileLibrary,token
from profile_migration import prepare,state_hash
from test_mapping_skill import StubMapper


class FieldTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name)
        self.lab.mutate(lambda s:s.update(prepare(s,1000)[0]));self.sid=self.lab.new_session()['id']
        self.eid=next(e['id'] for e in self.lab.state()['entries'] if e['category']=='basic')
        state=self.lab.state();self.source=self.lab.mutate(lambda s:add_custom_field(s,dict(entry_id=self.eid,edit_token=token(state,find(state['entries'],self.eid)),label='原称谓',type='text',confirmed_new_attribute=True)))['id']
        state=self.lab.state();ProfileLibrary(self.lab).save(dict(request_id='values',entry_id=self.eid,edit_token=token(state,find(state['entries'],self.eid)),values={self.source:'虚构新姓名','name':'虚构原姓名'}))
    def tearDown(self):self.lab.db.close();self.tmp.cleanup()
    def relation(self,fid):
        mapper=StubMapper({'q':fid});app=Application(self.lab,mapper)
        manifest=dict(url='https://fictional.example/form',tenant='fictional',form_key='application',fields=[dict(id='q',label='姓名',object_context=dict(category='basic',entry_id=self.eid))])
        app.scan(self.sid,manifest)
        saved=self.lab.mutate(lambda s:relation_update(s,dict(request_id='relation-'+fid,operation='confirm',session_id=self.sid,question_id='q',scope='site',expected_revision=0,expected_relation_revision=s.get('profile_relation_revision',0),confirmed=True)))
        return app,mapper,manifest,saved['relation']
    def command(self,operation='merge',**extra):
        args={'operation':operation,'field_id':self.source,**extra}
        if operation=='merge':args.setdefault('target_id','name')
        shown=preview(self.lab.state(),args)
        return dict(request_id='field-'+operation,token=shown['token'],confirmed_equivalent=True,value_choice='source',**args)
    def test_rename_keeps_id_meaning_values_and_reusable_relations_after_restart(self):
        app,mapper,manifest,relation=self.relation('name');before=self.lab.state()
        args=self.command('rename',field_id='name',label='本人姓名')
        result=self.lab.mutate(lambda s:update(s,args));self.assertEqual(result['field']['id'],'name')
        after=self.lab.state()
        for key in ('entries','versions','answer_versions','files'):self.assertEqual(after[key],before[key])
        self.assertEqual(find(after['fields'],'name')['meaning'],find(before['fields'],'name')['label'])
        self.assertTrue(self.lab.mutate(lambda s:update(s,args))['replayed'])
        self.lab.db.close();self.lab=Lab(self.tmp.name)
        self.assertEqual(find(self.lab.state()['fields'],'name'),find(after['fields'],'name'))
        Application(self.lab,mapper).scan(self.sid,manifest);self.assertEqual(len(mapper.calls),1)
    def test_merge_selects_current_value_redirects_relation_and_preserves_evidence_and_drafts(self):
        app,mapper,manifest,relation=self.relation(self.source)
        self.lab.mutate(lambda s:s['profile_drafts'].update({'draft':dict(body={'values':{self.source:'独立未保存草稿'}},revision=1)}))
        before=self.lab.state();args=self.command()
        self.lab.mutate(lambda s:update(s,args));after=self.lab.state();entry=find(after['entries'],self.eid)
        self.assertEqual(current_values(after,entry)['name'],'虚构新姓名');self.assertNotIn(self.source,current_values(after,entry))
        self.assertEqual(entry['values'][self.source],'虚构新姓名');self.assertEqual(after['answer_versions'][:len(before['answer_versions'])],before['answer_versions'])
        self.assertEqual(after['profile_field_redirects'][self.source],'name')
        self.assertEqual(find(after['profile_relations'],relation['id'])['field_ids'],['name'])
        self.assertEqual(after['profile_drafts']['draft']['body'],before['profile_drafts']['draft']['body']);self.assertTrue(after['profile_drafts']['draft']['reference_invalid'])
        self.assertTrue(find(after['sessions'],self.sid)['mapping_relations_stale'])
        self.assertEqual(after['profile_field_history'][-1]['target_value'],'虚构原姓名')
        self.assertNotIn('原称谓',find(after['fields'],'name')['aliases'])
        self.assertTrue(self.lab.mutate(lambda s:update(s,args))['replayed'])
        self.lab.db.close();self.lab=Lab(self.tmp.name)
        Application(self.lab,mapper).scan(self.sid,manifest);self.assertEqual(len(mapper.calls),1)
        with self.assertRaises(LabError):preview(self.lab.state(),dict(field_id=self.source))
    def test_merge_preserves_selected_target_and_negative_relation_exclusion(self):
        _,_,_,relation=self.relation(self.source)
        self.lab.mutate(lambda s:relation_update(s,dict(request_id='disable',operation='disable',relation_id=relation['id'],expected_revision=1,expected_relation_revision=1,confirmed=True)))
        args=self.command();args['value_choice']='target';self.lab.mutate(lambda s:update(s,args))
        state=self.lab.state();self.assertEqual(current_values(state,find(state['entries'],self.eid))['name'],'虚构原姓名')
        self.assertEqual(state['profile_relation_exclusions'][0]['field_ids'],['name'])
        self.assertEqual(state['profile_exclusion_redirects'][0]['field_ids'],[self.source])
    def test_stale_merge_and_type_or_scope_mismatch_do_not_write(self):
        args=self.command();state=self.lab.state()
        ProfileLibrary(self.lab).save(dict(request_id='concurrent',entry_id=self.eid,edit_token=token(state,find(state['entries'],self.eid)),values={'name':'后来内容'}))
        stable=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.lab.mutate(lambda s:update(s,args))
        for tid in ('school','height_cm'):
            with self.assertRaises(LabError):self.command(target_id=tid)
        with self.assertRaises(LabError):self.command(field_id='name',target_id=self.source)
        self.assertEqual(state_hash(self.lab.state()),stable)
    def test_merge_requires_choice_and_explicit_blank_clear(self):
        state=self.lab.state();ProfileLibrary(self.lab).save(dict(request_id='blank',entry_id=self.eid,edit_token=token(state,find(state['entries'],self.eid)),values={self.source:''}))
        args=self.command();stable=state_hash(self.lab.state())
        for change in ({'confirmed_equivalent':False},{'value_choice':None},{}):
            with self.assertRaises(LabError):self.lab.mutate(lambda s:update(s,{**args,**change}))
        self.assertEqual(state_hash(self.lab.state()),stable)
        self.lab.mutate(lambda s:update(s,{**args,'confirmed_clear':True}))
        self.assertEqual(current_values(self.lab.state(),find(self.lab.state()['entries'],self.eid))['name'],'')
    def test_active_use_blocks_merge_and_rename_collision_is_rejected(self):
        self.relation(self.source)
        self.lab.mutate(lambda s:find(s['sessions'],self.sid).update(preparation={'execution':{'status':'running'}}))
        args=self.command();stable=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.lab.mutate(lambda s:update(s,args))
        rename=self.command('rename',label='姓名')
        with self.assertRaises(LabError):self.lab.mutate(lambda s:update(s,rename))
        self.assertEqual(state_hash(self.lab.state()),stable)


if __name__=='__main__':unittest.main()
