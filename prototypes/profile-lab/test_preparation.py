import copy
import tempfile
import unittest
from lab import Lab, LabError
from application import Application
from preparation import Preparation
from form_analysis import save_analysis
from test_form_analysis import fixture
from requirements import requirement


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.lab=Lab(self.temp.name)
        self.app=Application(self.lab);self.prep=Preparation(self.lab,self.app)
        self.sid=save_analysis(self.lab,fixture())['id']
        self.edu=self.lab.mutate(lambda s:self.lab.new_entry(s,'education'))
        self.extra=self.lab.mutate(lambda s:self.lab.new_entry(s,'education'))
        self.lab.save_profile([dict(entry_id=self.edu['id'],field_id=k,value=v) for k,v in {'school':'虚构大学','degree':'MPAcc','graduation_date':'2027-06-30'}.items()])
        self.lab.save_profile([dict(entry_id=self.extra['id'],field_id='school',value='另一条不适用的虚构记录')])
        fields=[dict(id='edu',label='教育经历',collection=True,required=False,children=[
            dict(id='degree',label='学历',type='select',required=True,options=['硕士','本科']),
            dict(id='end',label='毕业年月',type='month',required=True)]),
            dict(id='new',label='语言程度',type='select',options=['入门','商务会话'],decision_required=True)]
        maps=[dict(website_id='edu',status='mapped',category='education',field_id=None,
                   entry_ids=[self.edu['id']],requirement=requirement('edu'),members=[
                    dict(website_id='degree',field_id='degree',transform='education_level'),
                    dict(website_id='end',field_id='graduation_date',transform='month')]),
              dict(website_id='new',status='new',category='additional',field_id=None,members=[],
                   new_field=dict(label='语言程度',category='additional',type='select'))]
        self.manifest=dict(url='https://example.com/apply',title='虚构岗位',fields=fields,execution='external')
        self.maps=dict(mappings=maps,engine='虚构语义输出')
        self.app.install_mapping(self.sid,self.manifest,self.maps)
    def test_mapping_connection_failure_preserves_diagnostics_without_resume_import_copy(self):
        from recognizer import RecognitionError
        from unittest.mock import Mock
        self.app.mapper=Mock()
        self.app.mapper.map.side_effect=RecognitionError('原文件已保留','connection_failed',{'model_catalog_failed':True})
        before=self.lab.state()
        with self.assertRaises(LabError) as ctx:self.app.scan(self.sid,self.manifest)
        self.assertIn('官网表单已读取',str(ctx.exception));self.assertNotIn('原文件',str(ctx.exception))
        self.assertEqual(ctx.exception.diagnostics,{'model_catalog_failed':True})
        self.assertEqual(self.lab.state(),before)

    def tearDown(self):
        self.lab.db.close();self.temp.cleanup()
    def complete(self):
        self.app.edit_answer(self.sid,'new','商务会话','update')
        self.prep.settings(self.sid,'')
    def test_unread_optional_sections_cannot_silently_disappear_from_readiness(self):
        self.complete()
        self.lab.mutate(lambda s:next(x for x in s['sessions'] if x['id']==self.sid)['form_analysis']['sections'].append(
            dict(id='unread-awards',label='获奖',repeatable=True,record_count=0,can_add=True,fields=[],note='')))
        content=self.prep.preview(self.sid)
        self.assertTrue(any(t['key']=='unread-sections' and '获奖' in t['message'] for t in content['tasks']))
        self.assertEqual(self.prep.start(self.sid,content['digest'])['status'],'awaiting_executor')
    def test_auto_set_excludes_unrelated_record_and_converts_without_profile_write(self):
        before=copy.deepcopy(self.lab.state()['entries'])
        p=self.app.plan(self.sid);self.assertEqual(len(p['automatic'][0]['selected']),1)
        self.assertEqual(p['automatic'][0]['value'],[{'degree':'硕士','graduation_date':'2027-06'}])
        self.assertEqual(self.lab.state()['entries'],before)
    def test_new_question_has_website_choices_and_update_creates_first_version(self):
        self.assertTrue(self.app.plan(self.sid)['missing'][0]['blocking'])
        self.complete();s=self.lab.state();field=next(f for f in s['fields'] if f['label']=='语言程度')
        self.assertEqual(field['options'],['入门','商务会话'])
        self.assertEqual(len([v for v in s['answer_versions'] if v['field_id']==field['id']]),0)
        self.assertFalse(self.prep.current(self.sid)['pending'])
    def test_preview_allows_missing_and_skips_unselected_attachment(self):
        p=self.prep.preview(self.sid);self.assertFalse(p['pending']);self.assertEqual(len(p['skipped']),2)
        execution=self.prep.start(self.sid,p['digest'])
        self.assertEqual(execution['status'],'awaiting_executor')
        self.assertIsNone(execution['confirmed_materials']['attachment'])
        self.assertFalse(any(r['website_id']=='new' for r in execution['confirmed_materials']['rows']))
        self.assertEqual(execution['confirmed_materials']['rows'][0]['records'][0]['values'][0]['value'],'硕士')
    def test_modified_material_rejects_old_preview(self):
        self.complete();p=self.prep.preview(self.sid)
        self.app.edit_answer(self.sid,'new','入门','session')
        with self.assertRaisesRegex(LabError,'材料已变化'):self.prep.start(self.sid,p['digest'])

    def test_partial_fill_excludes_invalid_required_value_and_ambiguous_collection(self):
        self.lab.save_profile([dict(entry_id=self.edu['id'],field_id='graduation_date',value='2027')])
        manifest=copy.deepcopy(self.manifest);maps=copy.deepcopy(self.maps)
        manifest['fields'].append(dict(id='languages',label='语言能力',collection=True,children=[dict(id='language-name',label='语言')]))
        maps['mappings'].append(dict(website_id='languages',status='ambiguous',reason='无法确定语言与考试分组',category=None,field_id=None,members=[]))
        self.app.install_mapping(self.sid,manifest,maps)
        before=copy.deepcopy(self.lab.state()['entries'])
        preview=self.prep.preview(self.sid)
        self.assertFalse(preview['pending'])
        self.assertTrue(any(t.get('website_id')=='languages' for t in preview['tasks']))
        self.assertTrue(any(r['website_id']=='languages' and r['value']=='' for r in preview['rows']))
        execution=self.prep.start(self.sid,preview['digest'])
        rows=execution['confirmed_materials']['rows']
        self.assertEqual(len(rows),1)
        self.assertEqual([(v['website_id'],v['value']) for v in rows[0]['records'][0]['values']],[('degree','硕士')])
        self.assertEqual(self.lab.state()['entries'],before)

    def test_unconfirmed_edit_still_requires_material_review(self):
        self.lab.mutate(lambda s:next(x for x in s['sessions'] if x['id']==self.sid).setdefault('preparation',{}).update(drafts={'fictional':{'value':'新草稿'}}))
        preview=self.prep.preview(self.sid)
        self.assertTrue(any(t['key']=='draft' for t in preview['tasks']))
        with self.assertRaises(LabError):self.prep.start(self.sid,preview['digest'])
    def test_confirm_queues_once_and_never_reports_filled(self):
        self.complete();p=self.prep.preview(self.sid)
        a=self.prep.start(self.sid,p['digest']);b=self.prep.start(self.sid,p['digest'])
        self.assertEqual(a['id'],b['id']);self.assertEqual(a['status'],'awaiting_executor')
        self.assertEqual(a['filled'],0);self.assertEqual(a['confirmed_materials']['rows'][0]['records'][0]['values'][0]['value'],'硕士')
    def test_unsaved_restoration_keeps_confirmation_and_read_only_verification(self):
        self.complete();preview=self.prep.preview(self.sid)
        self.lab.mutate(lambda s:next(x for x in s['sessions'] if x['id']==self.sid)['preparation'].update(preserve_unsaved_page=True))
        queued=self.prep.start(self.sid,preview['digest'])
        self.assertTrue(queued['confirmed_materials']['preserve_unsaved_page'])
        self.prep.pause(self.sid)
        checked=self.prep.verify(self.sid,True)
        self.assertTrue(checked['confirmed_materials']['verification_only'])
        self.assertTrue(checked['confirmed_materials']['after_reopen'])
        self.assertEqual(checked['filled'],0)
        with self.assertRaises(LabError):self.prep.verify(self.sid)
    def test_matching_schema_blocks_new_execution(self):
        self.complete()
        self.lab.mutate(lambda s:next(x for x in s['sessions'] if x['id']==self.sid)['preparation'].update(scan_status='matching'))
        preview=self.prep.preview(self.sid)
        self.assertTrue(any('表单匹配' in v for v in preview['pending']))
        with self.assertRaises(LabError):self.prep.start(self.sid,preview['digest'])
    def test_unknown_reference_and_cross_category_rejected(self):
        bad=copy.deepcopy(self.maps);bad['mappings'][0]['entry_ids']=[self.lab.state()['entries'][0]['id']]
        before=self.lab.state()
        with self.assertRaises(LabError):self.app.install_mapping(self.sid,self.manifest,bad)
        self.assertEqual(self.lab.state(),before)
        wrong={**self.manifest,'url':'https://other.example/apply'}
        with self.assertRaises(LabError):self.app.install_mapping(self.sid,wrong,self.maps)
        self.assertEqual(self.lab.state(),before)
    def test_pause_before_dispatch_and_fresh_confirmation(self):
        self.complete();p=self.prep.preview(self.sid);first=self.prep.start(self.sid,p['digest'])
        self.assertEqual(self.prep.pause(self.sid)['status'],'paused')
        second=self.prep.start(self.sid,p['digest']);self.assertNotEqual(first['id'],second['id'])
    def test_another_job_on_same_url_cannot_start_until_active_job_pauses(self):
        self.complete();p=self.prep.preview(self.sid)
        def clone(state):
            other=copy.deepcopy(next(s for s in state['sessions'] if s['id']==self.sid))
            other['id']='other-fictional-job';other['management_job_id']='job-b';state['sessions'].append(other)
        self.lab.mutate(clone)
        self.prep.start(self.sid,p['digest'])
        with self.assertRaisesRegex(LabError,'另一个岗位'):
            self.prep.start('other-fictional-job',p['digest'])
        self.prep.pause(self.sid)
        self.assertEqual(self.prep.start('other-fictional-job',p['digest'])['status'],'awaiting_executor')
    def test_imprecise_date_becomes_required_decision(self):
        self.lab.save_profile([dict(entry_id=self.edu['id'],field_id='graduation_date',value='2027')])
        self.assertTrue(any('明确的年月' in i['message'] for i in self.app.plan(self.sid)['missing']))
    def test_optional_new_child_can_be_added_without_blocking_preview(self):
        manifest=copy.deepcopy(self.manifest);maps=copy.deepcopy(self.maps)
        manifest['fields'][0]['children'].append(dict(id='advisor',label='导师',required=False))
        maps['mappings'][0]['members'].append(dict(website_id='advisor',field_id=None,new_field=dict(label='导师',category='education',type='text')))
        self.app.install_mapping(self.sid,manifest,maps);self.complete()
        item=next(i for i in self.app.plan(self.sid)['missing'] if i['child_id']=='advisor')
        self.assertTrue(item['editable']);self.assertFalse(item['blocking'])
        self.app.edit_answer(self.sid,'edu','虚构导师','session',entry_id=self.edu['id'],child_id='advisor')
        self.assertFalse(self.prep.current(self.sid)['pending'])
        self.assertTrue(any(f['label']=='导师' and f['category']=='education' for f in self.lab.state()['fields']))
    def test_answer_that_requires_records_becomes_actionable_missing(self):
        maps=copy.deepcopy(self.maps);maps['mappings'][0]['entry_ids']=[]
        maps['mappings'][0]['requires_records_when']=dict(website_id='new',equals='商务会话',message='虚构条件要求至少一条记录')
        self.app.install_mapping(self.sid,self.manifest,maps);self.complete()
        self.assertTrue(any(i['kind']=='count' and i['blocking'] for i in self.app.plan(self.sid)['missing']))

    def test_remove_blank_optional_child_and_scalar_persists_without_affecting_shared_values(self):
        manifest=copy.deepcopy(self.manifest);maps=copy.deepcopy(self.maps)
        manifest['fields'][1].pop('decision_required')
        manifest['fields'][0]['children'].append(dict(id='advisor',label='导师',required=False))
        maps['mappings'][0]['members'].append(dict(website_id='advisor',field_id=None,new_field=dict(label='导师',category='education',type='text')))
        self.app.install_mapping(self.sid,manifest,maps)
        before=copy.deepcopy(self.lab.state()['entries'])
        self.prep.settings(self.sid,'')
        for item in self.app.plan(self.sid)['missing']:
            self.assertFalse(item['blocking'])
            key=self.prep.missing_key(item)
            self.prep.remove_optional(self.sid,key)
            self.prep.remove_optional(self.sid,key)  # replay is safe
        current=self.prep.current(self.sid)
        self.assertFalse(current['pending'])
        self.assertEqual(len(current['removed_optional']),2)
        self.assertFalse(any(r['website_id']=='new' for r in current['rows']))
        self.assertFalse(any(v['website_id']=='advisor' for r in current['rows'] for e in r.get('records',[]) for v in e['values']))
        self.assertEqual(self.lab.state()['entries'],before)
        self.assertEqual(Preparation(self.lab,self.app).current(self.sid),current)
        # If the website now requires the field, an old optional deletion cannot hide it.
        manifest['fields'][0]['children'][-1]['required']=True
        self.app.install_mapping(self.sid,manifest,maps)
        self.assertTrue(self.prep.current(self.sid)['skipped'])
        required=next(i for i in self.app.plan(self.sid)['missing'] if i.get('child_id')=='advisor')
        with self.assertRaises(LabError):self.prep.remove_optional(self.sid,self.prep.missing_key(required))

    def test_remove_optional_clears_only_its_answer_draft(self):
        manifest=copy.deepcopy(self.manifest);manifest['fields'][1].pop('decision_required')
        self.app.install_mapping(self.sid,manifest,self.maps)
        item=next(i for i in self.app.plan(self.sid)['missing'] if i['website_field']['id']=='new')
        parts=(self.sid,item.get('group_id'),item.get('entry_id'),item.get('field_id') or item.get('child_id') or 'new')
        key='/'.join('undefined' if v is None else str(v) for v in parts)
        self.prep.draft(self.sid,key,'未确认的虚构编辑')
        self.prep.draft(self.sid,self.sid+'/unrelated','其他草稿')
        self.prep.remove_optional(self.sid,self.prep.missing_key(item))
        drafts=self.prep.view(self.sid)['drafts']
        self.assertIsNone(drafts[key]['value'])
        self.assertEqual(drafts[self.sid+'/unrelated']['value'],'其他草稿')
