"""Fictional regressions for website scope, complete sets and scoped edits."""
import copy
import tempfile
import unittest
from lab import Lab, LabError
from application import Application
from requirements import requirement


def condition(fid, values, domain='text', op='in'):
    return dict(field_id=fid, values=values, domain=domain, op=op)


def mapping(website_id, fid, cat, rule=None, **extra):
    return dict(website_id=website_id, field_id=fid, category=cat, requirement=rule,
                status='mapped', reason='虚构测试的明确网站要求', members=[], new_field=None, **extra)


def education_rule(group, minimum='本科', selection='all'):
    return requirement(group, selection, filters=[condition('degree', [minimum], 'education_level', 'gte')],
                       rank=dict(field_id='degree', domain='education_level', direction='asc' if selection=='all' else 'desc'),
                       required_values=[condition('degree', [minimum], 'education_level')] if selection=='all' else [])


class Mapper:
    def __init__(self, mappings): self.mappings = mappings
    def map(self, fields, profile): return {'engine':'虚构明确要求', 'mappings':copy.deepcopy(self.mappings)}


class RequirementSetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.lab=Lab(self.temp.name)
        self.rows={}
        for level,school,major in [('高中','甲高中',''),('本科','乙大学','本科专业'),('硕士','丙大学','研究生专业')]:
            self.rows[level]=self.entry('education',school=school,degree=level,major=major)
    def tearDown(self): self.lab.db.close(); self.temp.cleanup()
    def entry(self,cat,**values):
        entry=self.lab.mutate(lambda s:self.lab.new_entry(s,cat))
        self.lab.save_profile([dict(entry_id=entry['id'],field_id=k,value=v) for k,v in values.items()]);return entry
    def start(self,fields,mappings):
        self.app=Application(self.lab,Mapper(mappings));self.sid=self.lab.new_session()['id']
        self.app.scan(self.sid,dict(url='http://localhost/fiction',fields=fields,execution='local'))
        return self.app.plan(self.sid)
    def collection(self,identifier,cat,rule,children=None):
        children=children or []
        field=dict(id=identifier,label=identifier,collection=True,required=True,children=children)
        m=mapping(identifier,None,cat,rule);m['members']=[dict(website_id=c['id'],field_id=c['id'],new_field=None) for c in children]
        return field,m
    def answer(self,p,id): return next(i['value'] for i in p['payload'] if i['website_field']['id']==id)
    def test_education_sets_and_highest_are_independent_questions(self):
        specs=[self.collection('college','education',education_rule('college')),
               self.collection('high_school','education',education_rule('high_school','高中')),
               self.collection('highest','education',education_rule('highest',selection='highest'))]
        p=self.start([s[0] for s in specs],[s[1] for s in specs])
        self.assertEqual([e['degree'] for e in self.answer(p,'college')],['本科','硕士'])
        self.assertEqual([e['degree'] for e in self.answer(p,'high_school')],['高中','本科','硕士'])
        self.assertEqual([e['degree'] for e in self.answer(p,'highest')],['硕士'])
        self.assertEqual(p['decisions'],[]);self.assertEqual(p['missing'],[])
    def test_highest_and_bachelor_scalar_locate_records_without_row_index(self):
        p=self.start([dict(id='highest',label='最高学历院校',required=True),dict(id='bachelor',label='本科院校',required=True)],
                     [mapping('highest','school','education',education_rule('highest',selection='highest')),
                      mapping('bachelor','school','education',requirement('bachelor','one',filters=[condition('degree',['本科'],'education_level')]))])
        self.assertEqual(self.answer(p,'highest'),'丙大学');self.assertEqual(self.answer(p,'bachelor'),'乙大学')
    def test_scalar_level_transform_preserves_original_education_fact(self):
        self.lab.save_profile([dict(entry_id=self.rows['硕士']['id'],field_id='degree',value='MPAcc')])
        before=copy.deepcopy(self.lab.state()['entries'])
        p=self.start([dict(id='highest',label='最高学历',required=True)],
                     [mapping('highest','degree','education',education_rule('highest',selection='highest'),transform='education_level')])
        self.assertEqual(self.answer(p,'highest'),'硕士')
        self.assertEqual(before,self.lab.state()['entries'])
    def test_unknown_scalar_transform_is_rejected(self):
        with self.assertRaisesRegex(LabError,'转换'):
            self.start([dict(id='highest',label='最高学历',required=True)],
                       [mapping('highest','degree','education',education_rule('highest',selection='highest'),transform='invent_level')])

    def test_level_conversion_uses_unique_observed_website_option(self):
        from application import website_value
        self.assertEqual(website_value('MPAcc','education_level',['本科','硕士研究生','博士研究生']),'硕士研究生')
        self.assertEqual(website_value('MPAcc','education_level',['硕士研究生','MBA']),'硕士研究生')
        self.assertEqual(website_value('MPAcc','education_level',['硕士','硕士研究生']),'硕士')
        self.assertEqual(website_value('MPAcc','education_level',['研究生(硕士)','硕士研究生']),'硕士')
        self.assertEqual(website_value('未知学历','education_level',['硕士研究生']),'未知学历')
    def test_unopened_degree_dropdown_keeps_formal_fact_and_uses_reviewed_level(self):
        m=mapping('award',None,'education',education_rule('highest',selection='highest'),transform='academic_degree_level')
        m.update(status='new',new_field=dict(label='学位',category='education',type='select'))
        self.start([dict(id='award',label='最高学位',required=True,type='select',options=[])],[m])
        result=self.app.edit_answer(self.sid,'award','管理学硕士','session')
        self.assertEqual(result['field']['type'],'text')
        self.assertEqual(self.answer(self.app.plan(self.sid),'award'),'硕士')
        self.assertFalse(any(v['field_id']==result['field']['id'] for v in self.lab.state()['answer_versions']))
    def test_degree_option_validation_uses_transformed_value(self):
        m=mapping('award',None,'education',education_rule('highest',selection='highest'),transform='academic_degree_level')
        m.update(status='new',new_field=dict(label='学位名称',category='education',type='text'))
        self.start([dict(id='award',label='最高学位',required=True,type='select',options=['学士','硕士'])],[m])
        self.app.edit_answer(self.sid,'award','管理学硕士','session')
        self.assertEqual(self.answer(self.app.plan(self.sid),'award'),'硕士')
        with self.assertRaises(LabError):self.app.edit_answer(self.sid,'award','管理学博士','session')
    def test_required_collection_empty_and_required_child_empty_block(self):
        f,m=self.collection('certs','certificates',requirement('certs'))
        p=self.start([f],[m]);self.assertFalse(p['ready']);self.assertFalse(p['payload'])
        f,m=self.collection('education','education',education_rule('education','高中'),[dict(id='major',label='专业',required=True)])
        p=self.start([f],[m]);issue=next(i for i in p['missing'] if i['field_id']=='major')
        self.assertEqual(issue['entry_id'],self.rows['高中']['id']);self.assertTrue(issue['editable']);self.assertFalse(p['ready'])
    def test_required_repeated_scalar_empty_is_not_automatic(self):
        p=self.start([dict(id='major',label='高中专业',required=True)],
                     [mapping('major','major','education',requirement('hs','one',filters=[condition('degree',['高中'],'education_level')]))])
        self.assertFalse(p['ready']);self.assertFalse(p['payload'])
    def test_default_all_respects_selection_and_explicit_coverage(self):
        f,m=self.collection('edu','education',education_rule('edu'));self.start([f],[m]);before=self.lab.state()
        self.app.select_entries(self.sid,'education',[self.rows['本科']['id']],'edu')
        plan=self.app.plan(self.sid)
        self.assertTrue(plan['ready'])
        self.assertEqual([e['degree'] for e in self.answer(plan,'edu')],['本科'])
        self.assertEqual(self.lab.state()['entries'],before['entries'])
        self.app.select_entries(self.sid,'education',[self.rows['硕士']['id']],'edu')
        plan=self.app.plan(self.sid)
        self.assertFalse(plan['ready'])
        self.assertTrue(any(i['kind']=='coverage' for i in plan['missing']))

    def test_new_project_child_reuses_existing_data_and_scoped_edits(self):
        for fid,label,kind in [('project_name','项目名称','text'),('project_started','开始日期','partial_date'),('project_description','项目描述','versioned_text')]:
            if not any(f['id']==fid for f in self.lab.state()['fields']):
                self.lab.add_field(dict(id=fid,label=label,category='projects',type=kind))
        project=self.entry('projects',project_name='虚构校园项目',project_started='2023-11')
        self.lab.create_version(project['id'],'project_description','虚构项目描述')
        children=[dict(id='name',label='项目名称',required=True),dict(id='description',label='项目描述',required=True)]
        f,m=self.collection('projects','projects',requirement('projects'),children)
        labels={f['id']:f['label'] for f in self.lab.state()['fields']}
        m['members']=[dict(website_id=c['id'],field_id=None,new_field=dict(label=labels[fid],category='projects',type='text')) for c,fid in zip(children,['project_name','project_description'])]
        p=self.start([f],[m]);self.assertTrue(p['ready'])
        self.assertEqual(self.answer(p,'projects'),[dict(project_name='虚构校园项目',project_description='虚构项目描述')])
        before=copy.deepcopy(self.lab.state()['entries'])
        self.app.edit_answer(self.sid,'projects','本次项目名称','session',entry_id=project['id'],child_id='name')
        self.app.install_mapping(self.sid,dict(url='http://localhost/fiction',fields=[f]),dict(mappings=[m]))
        self.assertEqual(self.answer(self.app.plan(self.sid),'projects')[0]['project_name'],'本次项目名称')
        self.assertEqual(self.lab.state()['entries'],before)

    def test_new_child_ambiguous_label_does_not_guess_a_field(self):
        if not any(f['id']=='project_name' for f in self.lab.state()['fields']):
            if not any(f['id']=='project_name' for f in self.lab.state()['fields']): self.lab.add_field(dict(id='project_name',label='项目名称',category='projects',type='text'))
        if not any(f['id']=='project_other_name' for f in self.lab.state()['fields']): self.lab.add_field(dict(id='project_other_name',label='第二名称',category='projects',type='text'))
        self.lab.mutate(lambda s:next(f for f in s['fields'] if f['id']=='project_other_name').update(aliases=['项目名称']))
        self.entry('projects',project_name='虚构项目')
        f,m=self.collection('projects','projects',requirement('projects'),[dict(id='name',label='项目名称',required=True)])
        m['members']=[dict(website_id='name',field_id=None,new_field=dict(label='项目名称',category='projects',type='text'))]
        with self.assertRaisesRegex(LabError,'多个资料位置'):
            self.start([f],[m])
    def test_default_scalar_version_reused_without_decision(self):
        if not any(f['id']=='travel' for f in self.lab.state()['fields']): self.lab.add_field(dict(id='travel',label='接受出差',category='preferences',type='text'))
        entry=self.entry('preferences',travel='是');self.lab.create_version(entry['id'],'travel','接受出差')
        p=self.start([dict(id='travel',label='是否接受出差',required=True)],[mapping('travel','travel','preferences',requirement('intent','one'))])
        self.assertEqual(p['decisions'],[]);self.assertEqual(self.answer(p,'travel'),'是')
    def test_full_time_scope_does_not_include_internships_or_need_choice(self):
        self.entry('employment',company='实习单位',employment_type='实习')
        self.entry('employment',company='全职单位',employment_type='全职')
        f,m=self.collection('work','employment',requirement('work',filters=[condition('employment_type',['full_time'],'employment_type')]))
        p=self.start([f],[m]);self.assertEqual([v['company'] for v in self.answer(p,'work')],['全职单位']);self.assertFalse(p['decisions'])
    def test_unknown_scope_fact_is_not_silently_excluded(self):
        unknown=self.entry('employment',company='性质未知单位')
        f,m=self.collection('work','employment',requirement('work',filters=[condition('employment_type',['full_time'],'employment_type')]))
        p=self.start([f],[m]);self.assertTrue(any(i['entry_id']==unknown['id'] and i['field_id']=='employment_type' for i in p['missing']))
        self.app.edit_answer(self.sid,'work','实习','session',entry_id=unknown['id'],field_id='employment_type')
        p=self.app.plan(self.sid);self.assertFalse(any(i['kind']=='scope' for i in p['missing']))
        self.assertNotIn('employment_type',next(e for e in self.lab.state()['entries'] if e['id']==unknown['id'])['values'])
    def test_missing_high_school_is_detected_and_can_be_added_in_place(self):
        self.lab.mutate(lambda s:s['entries'].remove(next(e for e in s['entries'] if e['id']==self.rows['高中']['id'])))
        f,m=self.collection('edu','education',education_rule('edu','高中'),[dict(id='school',label='学校',required=True),dict(id='degree',label='学历',required=True)])
        p=self.start([f],[m]);self.assertTrue(any(i['kind']=='coverage' for i in p['missing']))
        entry=self.app.add_entry(self.sid,'edu')
        self.app.edit_answer(self.sid,'edu','补充高中','update',entry_id=entry['id'],child_id='school')
        self.app.edit_answer(self.sid,'edu','高中','update',entry_id=entry['id'],child_id='degree')
        p=self.app.plan(self.sid);self.assertTrue(p['ready']);self.assertEqual(len(self.answer(p,'edu')),3)
    def test_two_curated_sets_and_their_versions_are_independent(self):
        first=self.entry('employment',company='甲');second=self.entry('employment',company='乙')
        v=self.lab.create_version(first['id'],'description','默认描述');alt=self.lab.create_version(first['id'],'description','另一版')
        specs=[self.collection(group,'employment',requirement(group,'choose')) for group in ['a','b']]
        self.start([s[0] for s in specs],[s[1] for s in specs])
        self.app.select_entries(self.sid,'employment',[first['id']],'a');self.app.select_entries(self.sid,'employment',[second['id'],first['id']],'b')
        self.app.select_version(self.sid,'a',alt['id'],first['id'],'description')
        p=self.app.plan(self.sid);self.assertEqual(self.answer(p,'a')[0]['description'],'另一版')
        self.assertEqual([e['company'] for e in self.answer(p,'b')],['乙','甲']);self.assertEqual(self.answer(p,'b')[1]['description'],'默认描述')
        with self.assertRaises(LabError):self.app.select_entries(self.sid,'employment',[first['id']])
    def test_scoped_scalar_temporary_edit_does_not_change_other_question(self):
        specs=[(dict(id=g,label='本科院校'),mapping(g,'school','education',requirement(g,'one',filters=[condition('degree',['本科'],'education_level')]))) for g in ['a','b']]
        self.start([s[0] for s in specs],[s[1] for s in specs]);self.app.edit_answer(self.sid,'a','英文校名','session')
        p=self.app.plan(self.sid);self.assertEqual(self.answer(p,'a'),'英文校名');self.assertEqual(self.answer(p,'b'),'乙大学')
    def test_new_mentor_field_attaches_to_master_and_rejects_wrong_record(self):
        m=mapping('mentor',None,'education',requirement('master','one',filters=[condition('degree',['硕士'],'education_level')]))
        m.update(status='new',new_field=dict(label='导师',category='education',type='text'))
        self.start([dict(id='mentor',label='研究生导师',required=True)],[m])
        with self.assertRaises(LabError):self.app.edit_answer(self.sid,'mentor','甲老师','update',entry_id=self.rows['本科']['id'])
        result=self.app.edit_answer(self.sid,'mentor','甲老师','update');fid=result['field']['id']
        state=self.lab.state();self.assertEqual(result['entry_id'],self.rows['硕士']['id'])
        self.assertNotIn(fid,next(e for e in state['entries'] if e['id']==self.rows['硕士']['id'])['values'])
        self.assertEqual(self.answer(self.app.plan(self.sid),'mentor'),'甲老师')
        self.assertNotIn(fid,next(e for e in state['entries'] if e['id']==self.rows['本科']['id'])['values'])
        self.assertTrue(self.app.plan(self.sid)['ready'])
    def test_new_child_field_and_session_only_value_do_not_leak(self):
        f,m=self.collection('edu','education',education_rule('edu',selection='highest'),[dict(id='mentor',label='导师',required=True)])
        m['members']=[dict(website_id='mentor',field_id=None,new_field=dict(label='导师',category='education',type='text'))]
        self.start([f],[m]);result=self.app.edit_answer(self.sid,'edu','本次导师','session',entry_id=self.rows['硕士']['id'],child_id='mentor')
        fid=result['field']['id'];p=self.app.plan(self.sid);self.assertTrue(p['ready']);self.assertEqual(self.answer(p,'edu')[0][fid],'本次导师')
        self.assertFalse(any(v['field_id']==fid for v in self.lab.state()['answer_versions']))
    def test_selected_version_cannot_come_from_another_record(self):
        f,m=self.collection('edu','education',education_rule('edu'));self.start([f],[m])
        wrong=next(v for v in self.lab.state()['answer_versions'] if v['entry_id']==self.rows['硕士']['id'] and v['field_id']=='school')
        with self.assertRaises(LabError):self.app.select_version(self.sid,'edu',wrong['id'],self.rows['本科']['id'],'school')
    def test_complete_set_over_limit_is_reported_not_truncated(self):
        f,m=self.collection('edu','education',education_rule('edu'));m['requirement']['max_items']=1
        p=self.start([f],[m]);self.assertFalse(p['ready']);self.assertFalse(p['payload']);self.assertEqual(len(p['automatic'][0]['selected']),2)
    def test_scope_change_invalidates_only_affected_selection(self):
        intern=self.entry('employment',company='实习单位',employment_type='实习');full=self.entry('employment',company='全职单位',employment_type='全职')
        f,m=self.collection('work','employment',requirement('work','choose'));self.start([f],[m]);self.app.select_entries(self.sid,'employment',[intern['id']],'work')
        m['requirement']=requirement('work',filters=[condition('employment_type',['full_time'],'employment_type')]);self.app.mapper=Mapper([m])
        self.app.scan(self.sid,dict(url='http://localhost/fiction',fields=[f]))
        plan=self.app.plan(self.sid)
        self.assertFalse(plan['ready'])
        self.assertTrue(any(i['kind']=='selection' for i in plan['missing']))
        self.app.select_entries(self.sid,'employment',[full['id']],'work')
        self.assertEqual(self.answer(self.app.plan(self.sid),'work')[0]['company'],'全职单位')
    def test_obtained_highest_uses_explicit_completion_status(self):
        if not any(f['id']=='education_status' for f in self.lab.state()['fields']): self.lab.add_field(dict(id='education_status',label='就读状态',category='education',type='text'))
        self.lab.save_profile([dict(entry_id=e['id'],field_id='education_status',value='在读' if level=='硕士' else '已毕业') for level,e in self.rows.items()])
        rule=education_rule('completed',selection='highest');rule['filters'].append(condition('education_status',['completed'],'study_status'))
        p=self.start([dict(id='school',label='已取得最高学历院校',required=True)],[mapping('school','school','education',rule)])
        self.assertEqual(self.answer(p,'school'),'乙大学')
    def test_contact_fields_are_bound_to_same_person(self):
        for fid,label in [('person_name','联系人'),('relation','关系'),('person_phone','联系人手机')]:self.lab.add_field(dict(id=fid,label=label,category='family',type='text'))
        self.entry('family',person_name='甲',relation='父亲',person_phone='100');self.entry('family',person_name='乙',relation='母亲',person_phone='200')
        rule=requirement('emergency','one',filters=[condition('relation',['母亲'])])
        p=self.start([dict(id='n',label='母亲姓名'),dict(id='p',label='母亲电话')],[mapping('n','person_name','family',rule),mapping('p','person_phone','family',rule)])
        self.assertEqual((self.answer(p,'n'),self.answer(p,'p')),('乙','200'))
    def test_conditional_child_required_and_optional_collection_validation(self):
        for fid,label in [('has_award','是否获奖'),('award_detail','获奖说明')]:self.lab.add_field(dict(id=fid,label=label,category='education',type='text'))
        master=self.rows['硕士'];self.lab.save_profile([dict(entry_id=master['id'],field_id='has_award',value='是')])
        f,m=self.collection('edu','education',education_rule('edu',selection='highest'),[dict(id='award_detail',label='获奖说明',required=False)])
        f['required']=False;m['members'][0]['required_when']=[condition('has_award',['是'])]
        p=self.start([f],[m]);self.assertFalse(p['ready']);self.assertEqual(p['missing'][0]['field_id'],'award_detail')
        self.app.edit_answer(self.sid,'edu','否','session',entry_id=master['id'],field_id='has_award')
        self.assertTrue(self.app.plan(self.sid)['ready'])
    def test_contact_ambiguity_can_be_resolved_without_mixing_people(self):
        # Family fields are predeclared by the approved profile contract.
        first=self.entry('family',family_name='甲',family_phone='100');second=self.entry('family',family_name='乙',family_phone='200')
        rule=requirement('contact','one',max_items=1)
        p=self.start([dict(id='name',label='紧急联系人姓名',required=True),dict(id='phone',label='紧急联系人电话',required=True)],
                     [mapping('name','family_name','family',rule),mapping('phone','family_phone','family',rule)])
        self.assertFalse(p['ready']);self.assertTrue(p['decisions'])
        self.app.select_entries(self.sid,'family',[second['id']],'contact');p=self.app.plan(self.sid)
        self.assertTrue(p['ready']);self.assertEqual((self.answer(p,'name'),self.answer(p,'phone')),('乙','200'))
    def test_language_records_are_not_versions_or_forced_choices(self):
        if not any(f['id']=='language_name' for f in self.lab.state()['fields']): self.lab.add_field(dict(id='language_name',label='考试',category='language',type='text'))
        self.entry('language',language_name='CET4');self.entry('language',language_name='CET6')
        f,m=self.collection('all','language',requirement('languages'))
        p=self.start([f,dict(id='cet6',label='六级考试')],[m,mapping('cet6','language_name','language',requirement('cet6','one',filters=[condition('language_name',['CET6'])]))])
        self.assertEqual(len(self.answer(p,'all')),2);self.assertEqual(self.answer(p,'cet6'),'CET6');self.assertFalse(p['decisions'])
    def test_project_choice_depends_on_website_requirement(self):
        if not any(f['id']=='project_name' for f in self.lab.state()['fields']): self.lab.add_field(dict(id='project_name',label='项目',category='projects',type='text'))
        first=self.entry('projects',project_name='项目甲');second=self.entry('projects',project_name='项目乙')
        specs=[self.collection('all','projects',requirement('all')),self.collection('representative','projects',requirement('representative','choose',max_items=1))]
        p=self.start([f for f,m in specs],[m for f,m in specs]);self.assertEqual(len(self.answer(p,'all')),2);self.assertEqual(len(p['decisions']),1)
        self.app.select_entries(self.sid,'projects',[second['id']],'representative');p=self.app.plan(self.sid)
        self.assertEqual(self.answer(p,'representative')[0]['project_name'],'项目乙');self.assertEqual(len(self.answer(p,'all')),2)
    def test_date_scope_respects_precision_instead_of_guessing(self):
        entry=self.entry('employment',company='虚构单位',started='2023')
        f,m=self.collection('work','employment',requirement('work',filters=[condition('started',['2023-07'],'date','gte')]))
        p=self.start([f],[m]);self.assertFalse(p['ready']);self.assertTrue(any(i['field_id']=='started' for i in p['missing']))
        self.app.edit_answer(self.sid,'work','2023-08','session',entry_id=entry['id'],field_id='started')
        self.assertTrue(self.app.plan(self.sid)['ready'])
    def test_legacy_session_requires_rescan_and_retains_temporary_answer(self):
        person=next(e for e in self.lab.state()['entries'] if e['category']=='basic')
        self.lab.save_profile([dict(entry_id=person['id'],field_id='name',value='默认称呼')]);sid=self.lab.new_session()['id']
        field=dict(id='name',label='名字',required=True);m=mapping('name','name','basic')
        def old(s):
            session=next(x for x in s['sessions'] if x['id']==sid);session['website']=dict(fields=[field],mappings=[m]);session['overrides']['name']='旧会话本次称呼'
        self.lab.mutate(old);app=Application(self.lab,Mapper([m]));self.assertFalse(app.plan(sid)['ready'])
        app.scan(sid,dict(url='http://localhost/fiction',fields=[field]));self.assertEqual(self.answer(app.plan(sid),'name'),'旧会话本次称呼')
    def test_invalid_scope_is_rejected_without_state_write(self):
        f,m=self.collection('edu','education',requirement('edu',filters=[condition('not_a_field',['x'])]));before=self.lab.state()
        app=Application(self.lab,Mapper([m]));sid=self.lab.new_session()['id'];before=self.lab.state()
        with self.assertRaises(LabError):app.scan(sid,dict(url='http://localhost/fiction',fields=[f]))
        self.assertEqual(self.lab.state(),before)

if __name__=='__main__':unittest.main()
