import copy
import tempfile
import unittest
from lab import Lab, LabError, find, default_version
from application import Application
from profile_migration import prepare,state_hash
from profile_library import ProfileLibrary
from profile_contract import current_values
from resume_current import resolve_selected
from resume_import import record_token
from mapping_relations import update
from test_mapping_skill import StubMapper


class CurrentWritebackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.lab=Lab(self.temp.name)
        self.lab.mutate(lambda s:s.update(prepare(s,1000)[0]));self.sid=self.lab.new_session()['id'];self.app=Application(self.lab)
    def tearDown(self):self.lab.db.close();self.temp.cleanup()
    def test_new_session_attribute_leaves_no_shared_definition_or_entry(self):
        manifest=dict(url='https://example.test/apply',fields=[dict(id='q',label='虚构补充属性')])
        mapping=dict(website_id='q',category='additional',status='new',field_id=None,requirement=None,new_field=dict(label='虚构补充属性',category='additional',type='text'))
        self.app.install_mapping(self.sid,manifest,dict(mappings=[mapping]))
        before=self.lab.state()
        self.app.edit_answer(self.sid,'q','仅本次虚构回答','session')
        after=self.lab.state()
        for key in ('fields','entries','versions','answer_versions'):self.assertEqual(before[key],after[key])
        self.assertEqual(self.app.plan(self.sid)['payload'][0]['value'],'仅本次虚构回答')
        self.assertEqual(self.app.plan(self.sid)['payload'][0]['mapping']['status'],'mapped')
    def test_nonversioned_explicit_update_and_stale_ref(self):
        library=ProfileLibrary(self.lab);basic=next(e for e in self.lab.state()['entries'] if e['category']=='basic')
        from profile_library import token
        library.save(dict(request_id='name',entry_id=basic['id'],edit_token=token(self.lab.state(),basic),values={'name':'示例姓名'}))
        self.app.install_mapping(self.sid,dict(url='https://example.test/form',fields=[dict(id='name',label='姓名')]),dict(mappings=[dict(website_id='name',category='basic',status='mapped',field_id='name',requirement=None)]))
        state=self.lab.state();basic=find(state['entries'],basic['id']);version=default_version(state,basic,'name')
        result=self.app.edit_answer(self.sid,'name','更正姓名','update',version['id'],version['revision'],request_id='write-name')
        self.assertEqual(result['mode'],'update')
        self.assertEqual(current_values(self.lab.state(),find(self.lab.state()['entries'],basic['id']))['name'],'更正姓名')
        self.assertEqual(result,self.app.edit_answer(self.sid,'name','更正姓名','update',version['id'],version['revision'],request_id='write-name'))
        with self.assertRaises(LabError):self.app.edit_answer(self.sid,'name','过期姓名','update',version['id'],version['revision'],request_id='new-request')
        with self.assertRaises(LabError):self.app.edit_answer(self.sid,'name','改写回放','update',version['id'],version['revision'],request_id='write-name')
    def test_partial_import_preserves_unselected_and_no_award_versions(self):
        record=ProfileLibrary(self.lab).save(dict(request_id='award',category='honors',values={'award_name':'示例奖项','award_details':'原说明','award_date':'2024'}))['record']
        state=self.lab.state();target=find(state['entries'],record['id'])
        rows=[dict(id=f'c{i}',field_id=fid,value=value,category='honors',group='honors:0',entry_id=target['id'],target_token=record_token(state,target),source={'kind':'import'},status='差异',type='text') for i,(fid,value) in enumerate([('award_details','新说明'),('award_date','2025')])]
        state['imports'].append(dict(id='import_test',filename='fiction.txt',candidates=rows,parser_contract='resume-material-parser/v1'))
        before=copy.deepcopy(state)
        with self.assertRaises(LabError):resolve_selected(self.lab,state,[dict(candidate_id='c0',mode='new')])
        state=before
        result=resolve_selected(self.lab,state,[dict(candidate_id='c0',mode='replace')])
        values=current_values(state,find(state['entries'],target['id']))
        self.assertEqual(result['saved'],1);self.assertEqual(values['award_details'],'新说明');self.assertEqual(values['award_date'],'2024')
        self.assertFalse(rows[1].get('saved',False))
    def test_scalar_preview_token_guards_session_changes_and_new_definition_writeback(self):
        from application_current import answer_preview
        manifest=dict(url='https://example.test/apply',fields=[dict(id='q',label='虚构补充属性')])
        mapping=dict(website_id='q',category='additional',status='new',field_id=None,requirement=None,new_field=dict(label='虚构补充属性',category='additional',type='text'))
        self.app.install_mapping(self.sid,manifest,dict(mappings=[mapping]))
        self.app.edit_answer(self.sid,'q','本次内容','session')
        args=dict(session_id=self.sid,website_id='q',value='明确同步')
        preview=answer_preview(self.app,self.lab.state(),args);self.assertTrue(preview['new_definition'])
        self.app.edit_answer(self.sid,'q','之后的本次内容','session')
        stable=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.app.edit_answer(self.sid,'q','明确同步','update',request_id='sync',preview_token=preview['token'])
        self.assertEqual(state_hash(self.lab.state()),stable)
        fresh=answer_preview(self.app,self.lab.state(),args)
        result=self.app.edit_answer(self.sid,'q','明确同步','update',request_id='sync',preview_token=fresh['token'])
        state=self.lab.state();field=find(state['fields'],result['field']['id']);entry=find(state['entries'],result['entry_id'])
        self.assertEqual(current_values(state,entry)[field['id']],'明确同步')
        self.assertFalse(find(state['sessions'],self.sid).get('session_fields'))
    def test_relation_reuse_restart_disable_and_stale_confirmation(self):
        mapper=StubMapper({'name':'name'});app=Application(self.lab,mapper)
        manifest=dict(url='https://example.test/form',tenant='fiction-tenant',form_key='application',fields=[dict(id='name',label='姓名')])
        app.scan(self.sid,manifest)
        args=dict(request_id='confirm1',operation='confirm',session_id=self.sid,question_id='name',expected_relation_revision=0,expected_revision=0,confirmed=True)
        before=self.lab.state();result=self.lab.mutate(lambda s:update(s,args));after=self.lab.state()
        for key in ('fields','entries','versions','answer_versions','files'):self.assertEqual(before[key],after[key])
        replay=self.lab.mutate(lambda s:update(s,args));self.assertTrue(replay['replayed'])
        with self.assertRaises(LabError):self.lab.mutate(lambda s:update(s,{**args,'request_id':'stale'}))
        self.lab.db.close();self.lab=Lab(self.temp.name)
        app=Application(self.lab,mapper);app.scan(self.sid,manifest);self.assertEqual(len(mapper.calls),1)
        r=result['relation']
        self.lab.mutate(lambda s:update(s,dict(request_id='disable1',operation='disable',relation_id=r['id'],expected_revision=1,expected_relation_revision=1,confirmed=True)))
        # The same model suggestion cannot revive a target rejected by the user.
        with self.assertRaises(LabError):app.scan(self.sid,manifest)
        self.assertEqual(find(self.lab.state()['profile_relations'],r['id'])['state'],'disabled')

    def test_joint_definition_answer_relation_writeback_rolls_back_and_replays(self):
        from application_current import answer_preview
        manifest=dict(url='https://example.test/apply',fields=[dict(id='q',label='虚构独立属性')])
        mapping=dict(website_id='q',category='additional',status='new',field_id=None,requirement=None,new_field=dict(label='虚构独立属性',category='additional',type='text'))
        self.app.install_mapping(self.sid,manifest,dict(mappings=[mapping]));self.app.edit_answer(self.sid,'q','虚构答案','session')
        preview=answer_preview(self.app,self.lab.state(),dict(session_id=self.sid,website_id='q',value='回库答案'))
        args=dict(request_id='joint',preview_token=preview['token'],relation_options=dict(scope='site',confirmed=True))
        before=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.app.edit_answer(self.sid,'q','回库答案','update',**args)
        self.assertEqual(state_hash(self.lab.state()),before)
        args['relation_options']['scope']='general'
        result=self.app.edit_answer(self.sid,'q','回库答案','update',**args)
        after=state_hash(self.lab.state());self.assertEqual(result,self.app.edit_answer(self.sid,'q','回库答案','update',**args));self.assertEqual(state_hash(self.lab.state()),after)
        state=self.lab.state();self.assertEqual(len(state['profile_relations']),1)
        self.assertEqual(state['profile_relations'][0]['field_ids'],[result['field']['id']])
        self.assertNotIn('回库答案',str(state['profile_relations']))
        self.assertEqual(current_values(state,find(state['entries'],result['entry_id']))[result['field']['id']],'回库答案')

    def test_explicit_relation_correction_changes_no_answers_and_excludes_wrong_target(self):
        mapper=StubMapper({'q':'surname'});app=Application(self.lab,mapper)
        manifest=dict(url='https://example.test/form',tenant='fiction-tenant',form_key='application',fields=[dict(id='q',label='姓名')])
        app.scan(self.sid,manifest)
        r=self.lab.mutate(lambda s:update(s,dict(request_id='wrong',operation='confirm',session_id=self.sid,question_id='q',expected_relation_revision=0,expected_revision=0,confirmed=True)))['relation']
        before=self.lab.state();args=dict(request_id='correct',operation='correct',relation_id=r['id'],session_id=self.sid,question_id='q',field_ids=['name'],plan_kind='alias',scope='site',expected_revision=1,expected_relation_revision=1,confirmed=True)
        result=self.lab.mutate(lambda s:update(s,args));after=self.lab.state()
        for key in ('fields','entries','versions','answer_versions','files'):self.assertEqual(before[key],after[key])
        self.assertEqual(result['relation']['supersedes'],r['id']);self.assertEqual(result['relation']['field_ids'],['name'])
        self.assertEqual(after['profile_relation_exclusions'][0]['field_ids'],['surname'])
        self.assertTrue(find(after['sessions'],self.sid)['mapping_relations_stale'])
        self.assertTrue(self.lab.mutate(lambda s:update(s,args))['replayed'])
        app.scan(self.sid,manifest);self.assertEqual(len(mapper.calls),1)
        self.assertFalse(find(self.lab.state()['sessions'],self.sid).get('mapping_relations_stale'))
        self.assertEqual(find(self.lab.state()['sessions'],self.sid)['website']['mappings'][0]['field_id'],'name')

    def test_relation_correction_cannot_change_scope_or_select_foreign_fields(self):
        app=Application(self.lab,StubMapper({'q':'surname','other':'name'}))
        app.scan(self.sid,dict(url='https://example.test/form',tenant='fiction-tenant',form_key='application',fields=[dict(id='q',label='姓名'),dict(id='other',label='另一问题')]))
        r=self.lab.mutate(lambda s:update(s,dict(request_id='wrong',operation='confirm',session_id=self.sid,question_id='q',expected_relation_revision=0,expected_revision=0,confirmed=True)))['relation']
        args=dict(request_id='correct',operation='correct',relation_id=r['id'],session_id=self.sid,question_id='q',field_ids=['name'],plan_kind='alias',scope='site',expected_revision=1,expected_relation_revision=1,confirmed=True)
        stable=state_hash(self.lab.state())
        for change in ({'scope':'general'},{'field_ids':['school']},{'question_id':'other'},{'field_ids':['surname']},{'field_ids':['name','surname']},{'plan_kind':'month'}):
            with self.assertRaises(LabError):self.lab.mutate(lambda s:update(s,{**args,**change}))
            self.assertEqual(state_hash(self.lab.state()),stable)


if __name__=='__main__':unittest.main()
