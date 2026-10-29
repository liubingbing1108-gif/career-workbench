import copy
import tempfile
import unittest
from lab import Lab,LabError,find
from profile_migration import prepare,state_hash
from profile_contract import current_values
from profile_pending import resolve,view


class ExamMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name);old=self.lab.state()
        entry=dict(id='fiction_exam',category='language',record_type='exam',values={'exam_name':'示例考试'},default_versions={},sources={})
        old['entries'].append(entry)
        for index,values in enumerate([{'language_score':'520','exam_date':'2023-06','exam_level':'优秀','exam_subscores':'听力180'},{'language_score':'580','exam_date':'2024-06'}]):
            refs={}
            for fid,value in values.items():
                vid=f'{index}_{fid}';refs[fid]=vid
                old['answer_versions'].append(dict(id=vid,entry_id=entry['id'],field_id=fid,content=value,revision=1,name='旧值',source={}))
            version=dict(id=f'old{index}',name=f'第{index+1}次结果',field_versions=refs)
            if index==0:entry['profile_base_version']=version;entry['default_versions']=copy.deepcopy(refs)
            else:entry['set_versions']=[version]
        self.old=copy.deepcopy(old);self.lab.mutate(lambda s:s.update(prepare(old,1000)[0]))
    def tearDown(self):self.lab.db.close();self.tmp.cleanup()
    def test_results_stay_together_and_unknown_new_semantics_stay_blank(self):
        state=self.lab.state();entry=find(state['entries'],'fiction_exam');values=current_values(state,entry)
        self.assertEqual(values['language_score'],'');self.assertEqual(values['exam_level'],'')
        item=next(p for p in view(state) if p['kind']=='exam_sitting')
        self.assertEqual(len(item['bundles']),2)
        self.assertFalse(any(p.get('field_id') in {'language_score','exam_level'} and p['kind']=='current_choice' for p in state['profile_pending']))
        args=dict(request_id='choose-sitting',id=item['id'],edit_token=item['edit_token'],confirmed=True,bundle_id='old1')
        self.lab.mutate(lambda s:resolve(s,args));state=self.lab.state();values=current_values(state,find(state['entries'],'fiction_exam'))
        self.assertEqual(values['language_score'],'580');self.assertEqual(values['obtained_date'],'');self.assertEqual(values['exam_components'],'');self.assertEqual(values['exam_level'],'')
        self.assertEqual(state['profile_legacy_evidence']['entries'],self.old['entries'])
    def test_semantics_require_explicit_values_and_invalid_choice_rolls_back(self):
        item=next(p for p in view(self.lab.state()) if p['kind']=='exam_sitting')
        args=dict(request_id='choose',id=item['id'],edit_token=item['edit_token'],confirmed=True,bundle_id='old0',values={'obtained_date':'2023-08'})
        before=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.lab.mutate(lambda s:resolve(s,{**args,'values':{'obtained_date':'unknown date'}}))
        self.assertEqual(state_hash(self.lab.state()),before)
        self.lab.mutate(lambda s:resolve(s,args));state=self.lab.state();values=current_values(state,find(state['entries'],'fiction_exam'))
        self.assertEqual(values['language_score'],'520');self.assertEqual(values['obtained_date'],'2023-08');self.assertEqual(values['exam_level'],'')


if __name__=='__main__':unittest.main()
