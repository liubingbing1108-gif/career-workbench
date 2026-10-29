import copy
import json
from pathlib import Path
import tempfile
import unittest
from application import Application
from lab import Lab, LabError, category
from mapping_skill import load_bundle, map_current, BUNDLE_SHA256
from profile_library import ProfileLibrary
from profile_migration import prepare


class StubMapper:
    def __init__(self,targets):self.targets=targets;self.calls=[]
    def call(self,prompt,schema):
        request=json.loads(prompt.rsplit('\n',1)[1]);self.calls.append((prompt,schema,request));decisions=[]
        for q in request['questions']:
            fid=self.targets[q['id']];field=next(f for f in request['catalog'] if f['id']==fid)
            cat=field['category'];rt=(field['record_types'] or [''])[0]
            selector=dict(selection='all',entry_ids=[],filters=[],rank=None,required_values=[],min_items=None,max_items=None) if category(cat)[2] else None
            decisions.append(dict(question_id=q['id'],proposal_state='candidate',semantic_status='equivalent',category=cat,record_type=rt,selector=selector,
                                  sources=[dict(field_id=fid,covers=q['label'])],alternatives=[],coverage=dict(covered=[q['label']],uncovered=[],partial=False),
                                  plan=dict(kind='alias',transform=None,extracts=[]),availability=dict(status='not_evaluated',check_id=None),relation_id=None,
                                  new_attribute=None,request_expand_catalog=False,reason='虚构同义字段对应',clarification=''))
        return dict(contract_version=request['contract_version'],request_id=request['request_id'],context=request['context'],decisions=decisions),{}


class MappingSkillTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.lab=Lab(self.temp.name)
        self.lab.mutate(lambda state:state.update(prepare(state,1000)[0]));self.sid=self.lab.new_session()['id']
    def tearDown(self):self.lab.db.close();self.temp.cleanup()
    def test_actual_call_uses_pinned_rules_schema_and_active_catalog(self):
        mapper=StubMapper({'name':'name'})
        out=map_current(mapper,self.lab.state(),self.sid,dict(url='https://example.test/form',fields=[dict(id='name',label='姓名')]))
        self.assertEqual(out['mapping_skill']['bundle_sha256'],BUNDLE_SHA256)
        prompt,schema,request=mapper.calls[0]
        self.assertIn('P32已确认',prompt);self.assertIn('四档',prompt);self.assertIn('$defs',schema)
        self.assertEqual(schema['type'],'object');self.assertNotIn('$ref',schema)
        self.assertEqual(set(schema['required']),set(schema['properties']))
        self.assertNotIn('exam_date',{f['id'] for f in request['catalog']})
        self.assertEqual(out['mappings'][0]['field_id'],'name')
        self.assertEqual(out['contract_version'],2)
        self.assertEqual(request['contract_version'],'application-field-mapper/v1')
    def test_collection_keeps_all_records_and_source_types(self):
        ProfileLibrary(self.lab).save(dict(request_id='e1',category='education',values={'school':'示例大学'}))
        ProfileLibrary(self.lab).save(dict(request_id='e2',category='education',values={'school':'另一示例大学'}))
        mapper=StubMapper({'school':'school','major':'major'});app=Application(self.lab,mapper)
        website=app.scan(self.sid,dict(url='https://example.test/form',fields=[dict(id='education',label='教育经历',collection=True,children=[dict(id='school',label='学校'),dict(id='major',label='专业')])]))
        self.assertTrue(website['fields'][0]['collection']);self.assertEqual(len(website['mappings'][0]['members']),2)
        self.assertEqual(len(app.plan(self.sid)['automatic'][0]['selected']),2)
    def test_mixed_language_row_has_separate_typed_sources(self):
        mapper=StubMapper({'language':'language_name','exam':'exam_name','score':'language_score'})
        output=map_current(mapper,self.lab.state(),self.sid,dict(url='https://example.test/form',fields=[dict(id='row',label='外语情况',collection=True,children=[dict(id='language',label='语种'),dict(id='exam',label='考试名称'),dict(id='score',label='分数')])]))
        self.assertEqual(len(output['mappings']),1)
        self.assertTrue(output['mappings'][0]['multi_source'])
        self.assertEqual([m['source_mapping']['record_type'] for m in output['mappings'][0]['members']],['ability','exam','exam'])
        self.assertTrue(output['website_fields'][0]['collection'])
    def test_missing_skill_cannot_fallback(self):
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(LabError):load_bundle(Path(path))


if __name__=='__main__':unittest.main()
