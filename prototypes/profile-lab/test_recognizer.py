import copy
import tempfile
import unittest
from lab import Lab, LabError, initial_state, validate_value
from recognizer import grounded_candidates, RecognitionError


def field(fid,label,value,quote=None,block=0,kind='text'):
    return {'field_id':fid,'label':label,'type':kind,'value':value,'evidence':[{'block':block,'quote':quote or value}]}

def sample(description='参与整理样例项目资料。',email='example@example.invalid'):
    text=f'陈示例 {email}\n样例大学 数学 本科 2020/09-2024/06\n样例公司 研究部门 分析实习 2023/07-至今\n{description}'
    entries=[
        {'category':'basic','title':'身份','fields':[field('name','姓名','陈示例')]},
        {'category':'contact','title':'联系方式','fields':[field('email','邮箱',email)]},
        {'category':'education','title':'样例大学','fields':[field('school','学校','样例大学'),field('major','专业','数学'),field('degree','学历','本科'),field('education_started','入学日期','2020-09','2020/09',kind='partial_date'),field('graduation_date','毕业日期','2024-06','2024/06',kind='partial_date')]},
        {'category':'employment','title':'样例公司','fields':[field('company','公司','样例公司'),field('role','职位','分析实习'),field('department','部门','研究部门'),field('started','开始日期','2023-07','2023/07',kind='partial_date'),field('ended','结束日期','至今',kind='partial_date'),field('description','经历描述',description,kind='versioned_text')]}
    ]
    return text, {'entries':entries,'warnings':[]}


class FakeRecognizer:
    name='模型接口替身（离线测试）'
    def __init__(self,results):self.results=iter(results)
    def status(self):return {'engine':self.name,'available':True}
    def extract(self,fields,blocks):
        result=next(self.results)
        if isinstance(result,Exception):raise result
        return copy.deepcopy(result),{'input_tokens':0,'output_tokens':0}


class RecognitionTests(unittest.TestCase):
    def setUp(self):self.directory=tempfile.TemporaryDirectory()
    def tearDown(self):
        if hasattr(self,'lab'):self.lab.db.close()
        self.directory.cleanup()
    def make_lab(self,results):
        self.lab=Lab(self.directory.name,FakeRecognizer(results));return self.lab
    def upload(self,name,text):return self.lab.upload(name,text.encode())
    def accept(self,preview):
        fresh=next(p for p in self.lab.state()['imports'] if p['id']==preview['id'])
        return self.lab.commit_import(fresh['id'],[c['id'] for c in fresh['candidates'] if c['selected']],{},fresh['revision'])

    def test_unlabelled_text_maps_and_proposed_fields_commit_only_on_selection(self):
        text,result=sample();self.make_lab([result]);preview=self.upload('unlabelled.txt',text)
        self.assertEqual(len(preview['candidates']),13)
        self.assertFalse(any(f['id']=='department' for f in self.lab.state()['fields']))
        self.assertFalse(self.lab.state()['versions'])
        self.accept(preview)
        state=self.lab.state();self.assertTrue(any(f['id']=='department' for f in state['fields']))
        self.assertEqual(next(e for e in state['entries'] if e['category']=='employment')['values']['started'],'2023-07')
        self.assertEqual(state['versions'][0]['content'],'参与整理样例项目资料。')

    def test_hallucinated_value_and_fake_evidence_are_rejected(self):
        text,result=sample();result['entries'][0]['fields'].extend([field('birthplace','出生地','不存在的城市','陈示例'),field('age','年龄','24','不存在的原文')])
        state=initial_state()
        for f in state['fields']:
            if f['type']=='date':f['type']='partial_date'
        candidates,rejected=grounded_candidates(state,[{'text':text,'location':'文本'}],'test.txt',result)
        self.assertEqual(len(rejected),2)
        self.assertFalse(any(c['field_id'] in {'age','birthplace'} for c in candidates))

    def test_pending_versions_align_without_duplicating_experience(self):
        text,a=sample();other,b=sample('整理另一版样例材料。')
        self.make_lab([a,b]);p=self.upload('a.txt',text);q=self.upload('b.txt',other)
        self.accept(p);self.accept(q)
        state=self.lab.state()
        self.assertEqual(sum(e['category']=='education' for e in state['entries']),1)
        self.assertEqual(sum(e['category']=='employment' for e in state['entries']),1)
        # A second description is unchecked for review, then explicitly selected.
        fresh=next(x for x in state['imports'] if x['id']==q['id'])
        c=next(c for c in fresh['candidates'] if c['field_id']=='description')
        self.assertEqual(c['status'],'描述待检查');self.assertFalse(c['selected'])
        self.lab.commit_import(q['id'],[c['id']],{},fresh['revision'])
        self.assertEqual(len(self.lab.state()['versions']),2)

    def test_cross_file_fact_conflict_is_unchecked_and_not_automatically_filled(self):
        text,a=sample();other,b=sample(email='other@example.invalid')
        self.make_lab([a,b]);p=self.upload('a.txt',text);self.upload('b.txt',other)
        for preview in self.lab.state()['imports']:
            c=next(c for c in preview['candidates'] if c['field_id']=='email')
            self.assertEqual(c['status'],'事实冲突');self.assertFalse(c['selected'])
        self.accept(p)
        self.assertEqual(self.lab.materials(self.lab.new_session()['id'])['values']['email'],'')

    def test_stale_preview_cannot_overwrite_after_another_file_changes_it(self):
        text,a=sample();other,b=sample(email='other@example.invalid')
        self.make_lab([a,b]);p=self.upload('a.txt',text);self.upload('b.txt',other)
        with self.assertRaises(LabError) as error:self.lab.commit_import(p['id'],[p['candidates'][0]['id']],{},p['revision'])
        self.assertEqual(error.exception.status,409)

    def test_failure_retains_original_and_retry_reuses_file(self):
        text,result=sample();self.make_lab([RecognitionError('识别超时'),result])
        with self.assertRaises(LabError):self.upload('failure.txt',text)
        state=self.lab.state();self.assertEqual(len(state['files']),1);self.assertEqual(state['imports'][0]['status'],'失败')
        self.assertEqual(self.lab.file_bytes(state['files'][0]['id'])[1],text.encode())
        retried=self.lab.recognize_import(state['imports'][0]['id'])
        self.assertEqual(retried['status'],'完成');self.assertEqual(len(self.lab.state()['files']),1)

    def test_partial_date_never_invents_day(self):
        f={'label':'日期','type':'partial_date'}
        for value in ['2027','2027-06','2027-06-01','至今']:self.assertEqual(validate_value(f,value),value)
        for value in ['2027-13','2027-02-30','2027/06']:
            with self.assertRaises(LabError):validate_value(f,value)

    def test_complete_description_across_paragraphs_is_verified(self):
        blocks=[{'text':'第一段：分析需求。','location':'段落1'},{'text':'第二段：实现方案。','location':'段落2'},{'text':'第三段：验证结果。','location':'段落3'}]
        content='\n'.join(b['text'] for b in blocks)
        item=field('description','经历描述',content,blocks[0]['text'],kind='versioned_text')
        item['evidence'].append({'block':2,'quote':blocks[2]['text']})
        result={'entries':[{'category':'employment','title':'样例经历','fields':[item]}]}
        candidates,rejected=grounded_candidates(initial_state(),blocks,'test.docx',result)
        self.assertFalse(rejected);self.assertEqual(candidates[0]['value'],content)


if __name__=='__main__':unittest.main()
