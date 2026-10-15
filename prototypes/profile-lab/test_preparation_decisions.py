import copy
import unittest
import test_preparation
from lab import LabError
from mapping import WebsiteMapper, mapping_schema

class DecisionTests(unittest.TestCase):
    setUp = test_preparation.PreparationTests.setUp
    tearDown = test_preparation.PreparationTests.tearDown
    complete = test_preparation.PreparationTests.complete
    def test_model_contract_allows_semantic_conversions(self):
        mapping=mapping_schema()['properties']['mappings']['items']['properties']
        self.assertIn('education_level',mapping['members']['items']['properties']['transform']['enum'])
        self.assertIn('academic_degree_level',mapping['transform']['enum'])

    def test_empty_optional_collection_allows_fill_without_disposition(self):
        self.complete()
        manifest=copy.deepcopy(self.manifest);maps=copy.deepcopy(self.maps)
        manifest['fields'].append(dict(id='project',label='项目经历',collection=True,required=False,children=[dict(id='project-name',label='项目名称',required=False)]))
        from requirements import requirement
        maps['mappings'].append(dict(website_id='project',status='mapped',category='projects',field_id=None,requirement=requirement('projects'),members=[dict(website_id='project-name',field_id=None,new_field=dict(label='项目名称',category='projects',type='text'))]))
        self.app.install_mapping(self.sid,manifest,maps)
        self.complete()
        missing=next(i for i in self.app.plan(self.sid)['missing'] if i['website_field']['id']=='project')
        self.assertEqual(missing['kind'],'count');self.assertFalse(missing['blocking'])
        self.assertTrue(self.prep.current(self.sid)['skipped'])
        self.prep.omit_optional(self.sid,self.prep.missing_key(missing),True)
        self.assertFalse(self.prep.current(self.sid)['pending'])

    def test_explicit_manual_completion_does_not_emit_invalid_value(self):
        self.lab.save_profile([dict(entry_id=self.edu['id'],field_id='graduation_date',value='2027')]);self.complete()
        missing=next(i for i in self.app.plan(self.sid)['missing'] if i.get('child_id')=='end')
        self.prep.defer(self.sid,self.prep.missing_key(missing),True);preview=self.prep.preview(self.sid)
        self.assertFalse(preview['pending']);self.assertEqual(len(preview['manual']),1)
        answer=preview['rows'][0]['records'][0]['values'][1]
        self.assertEqual(answer['value'],'');self.assertTrue(answer['manual'])
        self.assertEqual(self.prep.start(self.sid,preview['digest'])['status'],'awaiting_executor');self.prep.pause(self.sid)
        self.prep.defer(self.sid,self.prep.missing_key(missing),False);self.assertTrue(self.prep.current(self.sid)['skipped'])

    def test_cannot_defer_unknown_scope(self):
        maps=copy.deepcopy(self.maps);maps['mappings'][0]['requirement']['min_items']=2;self.app.install_mapping(self.sid,self.manifest,maps)
        item=next(i for i in self.app.plan(self.sid)['missing'] if i['kind']=='count')
        with self.assertRaises(LabError):self.prep.defer(self.sid,self.prep.missing_key(item),True)

    def test_reworded_group_keeps_choices_versions_and_session_answers(self):
        def configure(s):
            x=next(x for x in s['sessions'] if x['id']==self.sid)
            x['group_choices']={'edu':[self.edu['id']]};x['scoped_overrides']={'edu':{self.edu['id']+'/school':'本次学校'}}
        self.lab.mutate(configure)
        maps=copy.deepcopy(self.maps);maps['mappings'][0]['requirement'].update(group='education_history',summary='新的解释');self.app.install_mapping(self.sid,self.manifest,maps)
        session=self.app.plan(self.sid)['session'];self.assertEqual(session['group_choices']['edu'],[self.edu['id']]);self.assertEqual(session['scoped_overrides']['edu'][self.edu['id']+'/school'],'本次学校')
        manifest=copy.deepcopy(self.manifest);manifest['fields'][0]['id']='rebuilt-education'
        maps['mappings'][0]['website_id']='rebuilt-education';maps['mappings'][0]['requirement']['group']='rebuilt-group'
        self.app.install_mapping(self.sid,manifest,maps)
        session=self.app.plan(self.sid)['session']
        self.assertEqual(session['website']['mappings'][0]['requirement']['group'],'edu')
        self.assertEqual(session['group_choices']['edu'],[self.edu['id']])
        self.assertEqual(session['scoped_overrides']['edu'][self.edu['id']+'/school'],'本次学校')

    def test_previous_confirmed_answer_is_offered_not_implicitly_saved(self):
        self.complete();preview=self.prep.preview(self.sid);self.prep.start(self.sid,preview['digest']);self.prep.pause(self.sid)
        other=self.lab.new_session('另一个虚构申请')['id'];self.app.install_mapping(other,self.manifest,self.maps)
        field=next(f for f in self.lab.state()['fields'] if f['label']=='语言程度');entry=next(e for e in self.lab.state()['entries'] if e['category']=='additional')
        self.lab.save_profile([dict(entry_id=entry['id'],field_id=field['id'],value='')])
        maps=copy.deepcopy(self.maps);maps['mappings'][1].update(field_id=field['id'],status='mapped',new_field=None);self.app.install_mapping(other,self.manifest,maps)
        item=next(i for i in self.app.plan(other)['missing'] if i['website_field']['id']=='new')
        self.assertEqual(item.get('previous_answer'),'商务会话');self.assertTrue(item['blocking']);self.assertNotIn('scoped_overrides',self.app.plan(other)['session'])

    def test_mixed_section_split_reuses_only_original_child_ids(self):
        class Fake(WebsiteMapper):
            def call(self,prompt,schema):
                self.prompts=getattr(self,'prompts',[])+[prompt]
                return ({'mappings':[],'ungrouped_sections':['mixed']} if len(self.prompts)==1 else {'mappings':[],'ungrouped_sections':[]}),{}
        mapper=Fake();result=mapper.map([{'id':'mixed','label':'附加信息','collection':True,'children':[{'id':'language','label':'语言能力'},{'id':'skills','label':'软件技能'}]}],[])
        self.assertEqual([f['id'] for f in result['website_fields']],['language','skills']);self.assertEqual(len(mapper.prompts),2)
        for prompt in mapper.prompts:
            self.assertIn('"profile_categories"',prompt)
            self.assertIn('"id": "honors", "label": "荣誉与奖励", "repeatable": true',prompt)
            self.assertIn('"id": "subjective", "label": "个人陈述", "repeatable": true',prompt)

if __name__=='__main__':unittest.main()
