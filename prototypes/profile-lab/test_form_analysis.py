import copy
import tempfile
import unittest
from lab import Lab, LabError
from form_analysis import save_analysis


def fixture():
    return dict(schema_version=1,url='https://example.com/apply',title='虚构岗位',
        scanned_at='2026-10-10T00:00:00Z',source='虚构页面',sections=[dict(id='education',label='教育经历',
        repeatable=True,record_count=2,can_add=True,fields=[dict(id='education[].school',label='学校',
        type='text',required=True,executor_field_ids=['education[0].school','education[1].school'])])],
        attention=[],limits=['只完成解析'])


class FormAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.lab=Lab(self.temp.name)
    def tearDown(self):
        self.lab.db.close();self.temp.cleanup()
    def test_analysis_creates_session_without_answers_or_execution_plan(self):
        before=self.lab.state();s=save_analysis(self.lab,fixture());after=self.lab.state()
        self.assertEqual(s['form_analysis']['sections'][0]['fields'][0]['label'],'学校')
        self.assertNotIn('website',s);self.assertEqual(s['overrides'],{})
        self.assertEqual({k:v for k,v in before.items() if k!='sessions'},{k:v for k,v in after.items() if k!='sessions'})
    def test_existing_answers_are_rejected_not_imported(self):
        a=fixture();a['sections'][0]['fields'][0]['currentValue']='虚构网页值'
        before=self.lab.state()
        with self.assertRaises(LabError):save_analysis(self.lab,a)
        self.assertEqual(self.lab.state(),before)
    def test_rejects_non_web_urls_and_plans(self):
        for mutate in [lambda a:a.update(url='javascript:alert(1)'),lambda a:a.update(assignments=[]),lambda a:a['sections'][0]['fields'].append(copy.deepcopy(a['sections'][0]['fields'][0]))]:
            a=fixture();mutate(a)
            with self.assertRaises(LabError):save_analysis(self.lab,a)
    def test_does_not_replace_existing_material_plan(self):
        s=self.lab.new_session();self.lab.mutate(lambda state:state['sessions'][0].update(website={'fields':[]}))
        before=self.lab.state()
        with self.assertRaises(LabError):save_analysis(self.lab,fixture(),s['id'])
        self.assertEqual(self.lab.state(),before)
