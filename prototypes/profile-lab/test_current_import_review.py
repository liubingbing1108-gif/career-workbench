"""Re-run the delivered source-review behavior under the explicit flat contract."""
import copy
import tempfile
import test_import_questions as review
from lab import Lab,LabError,find
from profile_migration import prepare,state_hash
from profile_library import ProfileLibrary,token
from profile_contract import current_values
from resume_current import resolve_selected
from resume_import import record_token
import unittest


class CurrentQuestionTests(review.QuestionTests):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name,review.Engine())
        self.lab.mutate(lambda s:s.update(prepare(s,1000)[0]));self.p=self.lab.upload('fiction.txt',review.TEXT.encode());self.baseline=copy.deepcopy(self.lab.state()['entries'])


class CurrentSourceQuestionTests(review.SourceQuestionTests):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name,review.SourceEngine())
        self.lab.mutate(lambda s:s.update(prepare(s,1000)[0]));self.p=self.lab.upload('source-doubt.txt',(review.TEXT+'\n另一次校级奖').encode())


class CurrentImportAtomicTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name);self.lab.mutate(lambda s:s.update(prepare(s,1000)[0]));self.lib=ProfileLibrary(self.lab)
    def tearDown(self):self.lab.db.close();self.tmp.cleanup()
    def add_candidates(self,entry,values):
        def add(state):
            target=find(state['entries'],entry['id'])
            rows=[dict(id='candidate'+str(i),field_id=fid,value=value,category=entry['category'],record_type=entry.get('record_type',''),entry_id=entry['id'],target_token=record_token(state,target),group=entry['category']+':0',source=dict(kind='import'),status='差异',type='text') for i,(fid,value) in enumerate(values.items())]
            state['imports'].append(dict(id='fiction-import',filename='fiction.txt',candidates=rows,parser_contract='resume-material-parser/v1',identity_decisions={rows[0]['group']:{'entry_id':entry['id']}}))
            return rows
        return self.lab.mutate(add)
    def test_exam_update_requires_whole_candidate_and_clears_unsupplied_old_result(self):
        e=self.lib.save(dict(request_id='exam',category='language',record_type='exam',values={'exam_name':'示例考试','language_score':'500','obtained_date':'2023','exam_components':'[{"name":"听力","score":"150","scale":"249"}]'}))['record']
        rows=self.add_candidates(e,{'language_score':'550','obtained_date':'2024'})
        before=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.lab.mutate(lambda s:resolve_selected(self.lab,s,[dict(candidate_id=rows[0]['id'],mode='replace',confirm_exam_result=True)]))
        self.assertEqual(state_hash(self.lab.state()),before)
        self.lab.mutate(lambda s:resolve_selected(self.lab,s,[dict(candidate_id=r['id'],mode='replace',confirm_exam_result=True) for r in rows]))
        state=self.lab.state();values=current_values(state,find(state['entries'],e['id']));self.assertEqual(values['language_score'],'550');self.assertEqual(values['obtained_date'],'2024');self.assertEqual(values['exam_components'],'')
    def test_new_definition_requires_explicit_adoption_and_is_local(self):
        e=self.lib.save(dict(request_id='education',category='education',values={'school':'示例大学'}))['record']
        rows=self.add_candidates(e,{'fiction_attribute':'新事实'})
        self.lab.mutate(lambda s:find(s['imports'],'fiction-import')['candidates'][0].update(definition=dict(id='fiction_attribute',category='education',label='虚构独立属性',type='text',aliases=[],options=[])))
        before=state_hash(self.lab.state());args=dict(candidate_id=rows[0]['id'],mode='replace')
        with self.assertRaises(LabError):self.lab.mutate(lambda s:resolve_selected(self.lab,s,[args]))
        self.assertEqual(state_hash(self.lab.state()),before)
        self.lab.mutate(lambda s:resolve_selected(self.lab,s,[{**args,'confirm_new_field':True}]))
        self.assertEqual(find(self.lab.state()['fields'],'fiction_attribute')['entry_id'],e['id'])
    def test_deleted_target_cannot_be_restored_by_import_write(self):
        e=self.lib.save(dict(request_id='award',category='honors',values={'award_name':'虚构奖'}))['record']
        self.lib.archive(dict(entry_id=e['id'],edit_token=e['edit_token'],archived=True))
        rows=self.add_candidates(e,{'award_details':'导入文字'})
        before=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.lab.mutate(lambda s:resolve_selected(self.lab,s,[dict(candidate_id=rows[0]['id'],mode='replace')]))
        self.assertEqual(state_hash(self.lab.state()),before)

    def test_partial_employment_import_preserves_expression_and_unselected_values(self):
        e=self.lib.save(dict(request_id='employment',category='employment',values={'company':'虚构公司','description':'A','responsibilities':'B','achievements':'C','leaving_reason':'原离职原因'}))['record']
        rows=self.add_candidates(e,{'department':'研发部','responsibilities':'B新'})
        before=self.lab.state();target=find(before['entries'],e['id']);versions=copy.deepcopy(target['expression_versions'])
        self.lab.resolve_import([dict(candidate_id=rows[0]['id'],mode='replace')])
        state=self.lab.state();target=find(state['entries'],e['id']);values=current_values(state,target)
        self.assertEqual(values['department'],'研发部');self.assertEqual(values['responsibilities'],'B')
        self.assertEqual(target['expression_versions'],versions)
        self.lab.resolve_import([dict(candidate_id=rows[1]['id'],mode='replace')])
        state=self.lab.state();target=find(state['entries'],e['id']);values=current_values(state,target)
        self.assertEqual([values[fid] for fid in ('description','responsibilities','achievements','leaving_reason')],['A','B新','C','原离职原因'])
        self.assertEqual(len(target['expression_versions']),1)
        stable=state_hash(state)
        self.assertEqual(self.lab.resolve_import([dict(candidate_id=rows[1]['id'],mode='replace')])['saved'],0)
        self.assertEqual(state_hash(self.lab.state()),stable)

    def test_explicit_new_expression_copies_selected_set_without_electing_default(self):
        e=self.lib.save(dict(request_id='employment',category='employment',values={'company':'虚构公司','description':'A','responsibilities':'B','achievements':'C','leaving_reason':'事实'}))['record']
        def clear_default(state):
            target=find(state['entries'],e['id']);target['profile_default_set_id']=None
            state['sessions'].append(dict(id='past',profile_historical_materials=[dict(confirmed_materials={'description':'当时文本'})]))
        self.lab.mutate(clear_default)
        state=self.lab.state();original=find(state['entries'],e['id'])['expression_versions'][0];past=copy.deepcopy(state['sessions'])
        rows=self.add_candidates(e,{'responsibilities':'B新'})
        self.lab.resolve_import([dict(candidate_id=rows[0]['id'],mode='new',set_id=original['id'])])
        state=self.lab.state();target=find(state['entries'],e['id']);versions=target['expression_versions']
        self.assertIsNone(target['profile_default_set_id']);self.assertEqual(len(versions),2)
        self.assertEqual(versions[0],original);self.assertEqual(current_values(state,target,versions[1]['id'])['description'],'A')
        self.assertEqual(current_values(state,target,versions[1]['id'])['responsibilities'],'B新')
        self.assertNotIn('leaving_reason',versions[1]['field_versions']);self.assertEqual(state['sessions'],past)
        self.assertNotIn('import_extra',str(state.get('profile_layouts',{})))

    def test_stale_import_and_blank_source_do_not_overwrite_current_facts(self):
        e=self.lib.save(dict(request_id='education',category='education',values={'school':'虚构大学','major':'原专业'}))['record']
        rows=self.add_candidates(e,{'major':'新专业','school':''})
        self.lib.save(dict(request_id='later',entry_id=e['id'],edit_token=e['edit_token'],values={'major':'手动新专业'}))
        stable=state_hash(self.lab.state())
        # An old, unreconciled candidate token cannot bypass concurrent edits.
        stale=copy.deepcopy(self.lab.state());find(stale['imports'],'fiction-import')['candidates'][0]['target_token']='old-token'
        with self.assertRaises(LabError):resolve_selected(self.lab,stale,[dict(candidate_id=rows[0]['id'],mode='replace')])
        self.assertEqual(state_hash(self.lab.state()),stable)
        self.lab.resolve_import([dict(candidate_id=rows[1]['id'],mode='replace')])
        state=self.lab.state();self.assertEqual(current_values(state,find(state['entries'],e['id']))['school'],'虚构大学')

    def test_later_independent_import_is_not_suppressed_by_ignore(self):
        e=self.lib.save(dict(request_id='award',category='honors',values={'award_name':'示例奖','award_details':'原说明'}))['record']
        rows=self.add_candidates(e,{'award_details':'未采用说明'})
        self.lab.resolve_import([dict(candidate_id=rows[0]['id'],mode='ignore')])
        def upload_again(state):
            later=copy.deepcopy(find(state['imports'],'fiction-import'));later['id']='independent-import'
            c=later['candidates'][0];c['id']='independent-candidate';c.pop('disposition',None);c.update(status='差异',selected=True)
            state['imports'].append(later)
        self.lab.mutate(upload_again)
        self.assertEqual(self.lab.resolve_import([dict(candidate_id='independent-candidate',mode='replace')])['saved'],1)
        state=self.lab.state();self.assertEqual(current_values(state,find(state['entries'],e['id']))['award_details'],'未采用说明')

    def test_import_cannot_revive_removed_preset_or_use_other_objects_local_field(self):
        e=self.lib.save(dict(request_id='education',category='education',values={'school':'虚构大学'}))['record']
        other=self.lib.save(dict(request_id='other',category='education',values={'school':'另一大学'}))['record']
        field=self.lab.add_field(dict(entry_id=other['id'],edit_token=other['edit_token'],label='其他对象私有属性',confirmed_new_attribute=True,type='text'))
        for fid in ('education_description',field['id']):
            self.lab.mutate(lambda s:s.update(imports=[]))
            rows=self.add_candidates(e,{fid:'不得串写'})
            stable=state_hash(self.lab.state())
            with self.assertRaises(LabError):self.lab.resolve_import([dict(candidate_id=rows[0]['id'],mode='replace',confirm_new_field=True)])
            self.assertEqual(state_hash(self.lab.state()),stable)

    def test_nonversioned_categories_import_updates_current_without_expression_versions(self):
        cases=[('education','school'),('identity_documents','identity_type'),('certificates','certificate_name'),('skills','skill_name'),('campus','campus_title')]
        for cat,fid in cases:
            with self.subTest(category=cat):
                self.lab.mutate(lambda state:state.update(imports=[]))
                e=self.lib.save(dict(request_id='new-'+cat,category=cat,values={fid:'护照' if cat=='identity_documents' else '虚构旧内容'}))['record']
                value='其他' if cat=='identity_documents' else '虚构修订内容'
                rows=self.add_candidates(e,{fid:value});args=dict(candidate_id=rows[0]['id'],mode='new')
                before=state_hash(self.lab.state())
                with self.assertRaises(LabError):self.lab.resolve_import([args])
                self.assertEqual(state_hash(self.lab.state()),before)
                self.lab.resolve_import([{**args,'mode':'replace'}])
                state=self.lab.state();entry=find(state['entries'],e['id'])
                self.assertEqual(current_values(state,entry)[fid],value)
                self.assertFalse(entry.get('expression_versions'))

    def test_exam_alias_review_updates_existing_result_and_keeps_link(self):
        from resume_import import reconcile,comparison_token,entry_values
        exam=self.lib.save(dict(request_id='exam',category='language',record_type='exam',values={'exam_name':'虚构考试简称','exam_language':'英语','language_score':'500','obtained_date':'2023'}))['record']
        self.lib.save(dict(request_id='ability',category='language',record_type='ability',values={'language_name':'英语'},exam_ids=[exam['id']],links_revision=0))
        rows=self.add_candidates(exam,{'exam_name':'虚构考试全称','language_score':'550','obtained_date':'2024'})
        def suggest(state):
            p=find(state['imports'],'fiction-import');p['identity_decisions']={}
            p['comparison_hints']={'language:0':[dict(target_id=exam['id'],target_token=comparison_token(entry_values(state,find(state['entries'],exam['id']))),reason='可能为同一考试的不同名称',conflict_fields=[])]}
            reconcile(state)
        self.lab.mutate(suggest)
        self.assertTrue(find(self.lab.state()['imports'],'fiction-import')['candidates'][0]['identity_review'])
        decisions=[dict(candidate_id=r['id'],mode='replace',confirm_exam_result=True) for r in rows]
        before=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.lab.resolve_import(decisions)
        self.assertEqual(state_hash(self.lab.state()),before)
        preview=find(self.lab.state()['imports'],'fiction-import')
        self.lib.import_identity(dict(import_id=preview['id'],group='language:0',entry_id=exam['id'],revision=preview.get('revision',0)))
        self.lab.resolve_import(decisions)
        state=self.lab.state();exams=[e for e in state['entries'] if e.get('record_type')=='exam']
        self.assertEqual(len(exams),1);self.assertEqual(current_values(state,exams[0])['language_score'],'550')
        self.assertTrue(any(l['active'] and l['exam_id']==exam['id'] for l in state['language_exam_links']))

    def test_import_after_restore_preserves_hidden_field_and_user_unlinked_exam(self):
        from profile_current import visibility
        exam=self.lib.save(dict(request_id='exam',category='language',record_type='exam',values={'exam_name':'虚构考试','exam_language':'英语','language_score':'500'}))['record']
        ability=self.lib.save(dict(request_id='ability',category='language',record_type='ability',values={'language_name':'英语'},exam_ids=[exam['id']],links_revision=0))['record']
        self.lib.save(dict(request_id='unlink',entry_id=ability['id'],edit_token=ability['edit_token'],values={},exam_ids=[],links_revision=1))
        state=self.lab.state();archived=self.lib.archive(dict(entry_id=exam['id'],edit_token=token(state,find(state['entries'],exam['id'])),archived=True))['record']
        self.lib.archive(dict(entry_id=exam['id'],edit_token=archived['edit_token'],archived=False))
        self.lab.mutate(lambda state:visibility(state,dict(entry_id=exam['id'],field_id='language_score',hidden=True,revision=0)))
        rows=self.add_candidates(exam,{'language_score':'550'})
        self.lab.resolve_import([dict(candidate_id=rows[0]['id'],mode='replace',confirm_exam_result=True)])
        state=self.lab.state()
        self.assertEqual(current_values(state,find(state['entries'],exam['id']))['language_score'],'550')
        self.assertIn('language_score',state['profile_visibility'][exam['id']]['fields'])
        self.assertFalse(any(l['active'] for l in state['language_exam_links']))

    def test_legacy_parser_pending_result_cannot_bypass_current_contract(self):
        e=self.lib.save(dict(request_id='education',category='education',values={'school':'虚构大学'}))['record']
        rows=self.add_candidates(e,{'education_description':'旧契约新增版本旁路'})
        def legacy(state):
            imported=find(state['imports'],'fiction-import');imported.pop('parser_contract')
            imported['candidates'][0]['label']='旧教育说明'
        self.lab.mutate(legacy)
        before=state_hash(self.lab.state())
        with self.assertRaisesRegex(LabError,'旧解析契约'):
            self.lab.resolve_import([dict(candidate_id=rows[0]['id'],mode='replace')])
        self.assertEqual(state_hash(self.lab.state()),before)


if __name__=='__main__':unittest.main()
