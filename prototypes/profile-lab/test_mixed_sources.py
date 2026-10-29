import copy
import tempfile
import unittest
from lab import Lab,LabError,find
from application import Application
from preparation import Preparation
from profile_library import ProfileLibrary
from profile_current import link_exams
from profile_migration import prepare
from test_mapping_skill import StubMapper


class MixedSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name)
        self.lab.mutate(lambda s:s.update(prepare(s,1000)[0]));self.sid=self.lab.new_session()['id']
        lib=ProfileLibrary(self.lab);self.abilities=[];self.exams=[]
        for i,(language,exam,score) in enumerate([('英语','CET6','520'),('日语','JLPT N1','150')]):
            ability=lib.save(dict(request_id=f'a{i}',category='language',record_type='ability',values={'language_name':language}))['record']
            result=lib.save(dict(request_id=f'e{i}',category='language',record_type='exam',values={'exam_name':exam,'exam_language':language,'language_score':score}))['record']
            self.abilities.append(ability['id']);self.exams.append(result['id'])
            self.lab.mutate(lambda s:link_exams(s,find(s['entries'],ability['id']),[result['id']],expected_revision=0))
        self.manifest=dict(url='https://example.test/form',title='虚构外语表单',fields=[dict(id='row',label='外语情况',collection=True,children=[dict(id='language',label='语种'),dict(id='exam',label='考试名称'),dict(id='score',label='分数')])])
        self.app=Application(self.lab,StubMapper({'language':'language_name','exam':'exam_name','score':'language_score'}))
        self.app.scan(self.sid,self.manifest)
        self.lab.mutate(lambda s:find(s['sessions'],self.sid).update(form_analysis={'sections':[]}))
    def tearDown(self):self.lab.db.close();self.tmp.cleanup()
    def test_two_rows_read_linked_objects_and_preserve_actual_source(self):
        item=self.app.plan(self.sid)['automatic'][0]
        self.assertEqual([e['id'] for e in item['catalog']],self.exams)
        self.assertEqual(item['value'],[{'language_name':'英语','exam_name':'CET6','language_score':'520'},{'language_name':'日语','exam_name':'JLPT N1','language_score':'150'}])
        rows=Preparation(self.lab,self.app).current(self.sid)['rows'][0]['records']
        for i,row in enumerate(rows):
            self.assertEqual(row['entry_id'],self.exams[i])
            self.assertEqual([v['source_ref']['entry_id'] for v in row['values']],[self.abilities[i],self.exams[i],self.exams[i]])
    def test_session_edit_targets_ability_and_does_not_touch_shared_objects(self):
        before=self.lab.state()
        self.app.edit_answer(self.sid,'row','本次英语名称','session',entry_id=self.abilities[0],field_id='language_name',child_id='language')
        self.assertEqual(self.app.plan(self.sid)['automatic'][0]['value'][0]['language_name'],'本次英语名称')
        self.assertEqual(self.lab.state()['entries'],before['entries'])
        self.assertEqual(self.lab.state()['answer_versions'],before['answer_versions'])
        # A missing-value editor uses the visible exam row; resolve through its link.
        self.app.edit_answer(self.sid,'row','英文','session',entry_id=self.exams[0],field_id='language_name',child_id='language')
        self.assertEqual(self.app.plan(self.sid)['automatic'][0]['value'][0]['language_name'],'英文')
    def test_missing_link_leaves_only_that_cell_pending_and_rejects_edit(self):
        self.lab.mutate(lambda s:link_exams(s,find(s['entries'],self.abilities[0]),[],expected_revision=1))
        item=self.app.plan(self.sid)['automatic'][0]
        self.assertEqual(item['value'][0],{'language_name':'','exam_name':'CET6','language_score':'520'})
        rows=Preparation(self.lab,self.app).current(self.sid)['rows'][0]['records']
        self.assertTrue(rows[0]['values'][0]['pending']);self.assertFalse(rows[1]['values'][0]['pending'])
        with self.assertRaises(LabError):self.app.edit_answer(self.sid,'row','英语','session',entry_id=self.abilities[0],field_id='language_name',child_id='language')
    def test_different_exam_selectors_do_not_merge_sittings(self):
        class DifferentScope(StubMapper):
            def call(inner,prompt,schema):
                out,usage=super().call(prompt,schema)
                out['decisions'][2]['selector']['selection']='one'
                return out,usage
        from mapping_skill import map_current
        result=map_current(DifferentScope({'language':'language_name','exam':'exam_name','score':'language_score'}),self.lab.state(),self.sid,self.manifest)
        self.assertEqual(len(result['mappings']),3)
        self.assertFalse(any(m.get('multi_source') for m in result['mappings']))


if __name__=='__main__':unittest.main()
