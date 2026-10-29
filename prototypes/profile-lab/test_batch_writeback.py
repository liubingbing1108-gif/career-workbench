import copy
import tempfile
import unittest
from application import Application
from application_current import sync_preview
from lab import Lab,LabError,find
from material_sets import MaterialSets
from profile_contract import current_values
from profile_library import ProfileLibrary,token
from profile_migration import prepare,state_hash
from test_mapping_skill import StubMapper


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name)
        self.lab.mutate(lambda s:s.update(prepare(s,1000)[0]));self.sid=self.lab.new_session()['id']
        self.eid=ProfileLibrary(self.lab).save(dict(request_id='edu',category='education',values={'school':'虚构原学校','major':'原专业'}))['record']['id']
        self.app=Application(self.lab,StubMapper({'school':'school','major':'major'}));self.sets=MaterialSets(self.app)
        self.app.scan(self.sid,dict(url='https://fictional.example/form',fields=[dict(id='edu',label='教育',collection=True,children=[dict(id='school',label='学校'),dict(id='major',label='专业')])]))
    def tearDown(self):self.lab.db.close();self.tmp.cleanup()
    def record(self,**values):
        plan=self.app.plan(self.sid);item=next(i for i in plan['automatic']+plan['decisions'] if i['website_field']['id']=='edu');entry=next(e for e in item['selected'] if e['id']==self.eid)
        return dict(entry_id=self.eid,values={**entry['values'],**values},expected_values=copy.deepcopy(entry['values']))
    def reviewed(self,record,selected,relations=None,confirmed=None):
        shown=sync_preview(self.app,self.lab.state(),dict(session_id=self.sid,website_id='edu',records=[record]))['records'][0]
        return {**record,**{k:shown[k] for k in ('edit_token','sync_token')},'selected_fields':selected,'relations':relations or [],'confirmed_field_ids':confirmed or []},shown
    def save(self,record):return self.sets.save(self.sid,'edu',[record],mode='update',request_id='batch')
    def add_local(self):
        def add(s):
            website=find(s['sessions'],self.sid)['website'];website['fields'][0]['children'].append(dict(id='note',label='虚构补充属性'))
            website['mappings'][0]['members'].append(dict(website_id='note',field_id=None,new_field=dict(label='虚构补充属性',category='education',type='text'),transform=None))
        self.lab.mutate(add)
        return self.app.edit_answer(self.sid,'edu','仅本次属性答案','session',entry_id=self.eid,child_id='note')['field']['id']
    def test_selected_answers_and_relation_share_transaction_with_replay(self):
        record,shown=self.reviewed(self.record(school='新学校',major='未选专业'),['school'],[dict(question_id='school',scope='general',confirmed=True)])
        self.assertEqual(len(shown['relation_candidates']),2)
        result=self.save(record);after=self.lab.state()
        self.assertEqual(current_values(after,find(after['entries'],self.eid))['school'],'新学校');self.assertEqual(current_values(after,find(after['entries'],self.eid))['major'],'原专业')
        self.assertEqual(after['profile_relations'][0]['field_ids'],['school']);stable=state_hash(after)
        self.assertEqual(self.save(record),result);self.assertEqual(state_hash(self.lab.state()),stable)
    def test_relation_can_be_saved_without_shared_answer_write(self):
        record,_=self.reviewed(self.record(school='仅本次不同学校'),[],[dict(question_id='school',scope='general',confirmed=True)])
        before=self.lab.state();self.save(record);after=self.lab.state()
        for key in ('entries','answer_versions','fields'):self.assertEqual(before[key],after[key])
        self.assertEqual(len(after['profile_relations']),1)
    def test_new_attribute_requires_definition_and_answer_and_relation_rolls_back_on_failure(self):
        fid=self.add_local();record,shown=self.reviewed(self.record(),[fid],[dict(question_id='note',scope='general',confirmed=True)])
        self.assertTrue(next(d for d in shown['differences'] if d['field_id']==fid)['new_definition']);stable=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.save(record)
        self.assertEqual(state_hash(self.lab.state()),stable)
        record['confirmed_field_ids']=[fid];record['relations'][0]['scope']='site'
        with self.assertRaises(LabError):self.save(record)
        self.assertEqual(state_hash(self.lab.state()),stable)
        record['relations'][0]['scope']='general';self.save(record)
        state=self.lab.state();self.assertEqual(find(state['fields'],fid)['entry_id'],self.eid)
        self.assertEqual(current_values(state,find(state['entries'],self.eid))[fid],'仅本次属性答案');self.assertEqual(state['profile_relations'][0]['field_ids'],[fid])
    def test_temporary_attribute_relation_cannot_be_saved_alone(self):
        fid=self.add_local();record,_=self.reviewed(self.record(),[],[dict(question_id='note',scope='general',confirmed=True)])
        stable=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.save(record)
        self.assertEqual(state_hash(self.lab.state()),stable)
    def test_stale_relation_revision_or_answer_rejects_all_selected_changes(self):
        record,_=self.reviewed(self.record(school='新学校'),['school'])
        self.lab.mutate(lambda s:s.update(profile_relation_revision=100))
        stable=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.save(record)
        self.assertEqual(state_hash(self.lab.state()),stable)
    def test_blank_unselected_value_does_not_clear_and_wrong_question_rolls_back(self):
        record,_=self.reviewed(self.record(school='新学校',major=''),['school'],[dict(question_id='foreign',scope='general',confirmed=True)])
        stable=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.save(record)
        self.assertEqual(state_hash(self.lab.state()),stable)
        record['relations']=[];self.save(record)
        self.assertEqual(current_values(self.lab.state(),find(self.lab.state()['entries'],self.eid))['major'],'原专业')


if __name__=='__main__':unittest.main()
