import copy
import tempfile
import unittest
from lab import Lab
from application import Application
from profile_groups import profile_groups
from test_requirement_sets import Mapper, mapping


class ProfileGroupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.lab = Lab(self.temp.name)
        self.ids = {}
        for level, school in [('本科', '虚构本科大学'), ('MPAcc', '虚构硕士大学')]:
            e = self.lab.mutate(lambda s: self.lab.new_entry(s, 'education'))
            self.lab.save_profile([dict(entry_id=e['id'], field_id=k, value=v)
                for k,v in dict(degree=level, school=school).items()])
            self.ids[level] = e['id']

    def tearDown(self):
        self.lab.db.close()
        self.temp.cleanup()

    def group(self):
        return next(g for g in profile_groups(self.lab.state()) if g['category']=='education')

    def test_visible_sets_reference_same_records_and_report_missing_high_school(self):
        before = self.lab.state()
        college, high = self.group()['sets']
        self.assertEqual(college['entry_ids'], list(self.ids.values()))
        self.assertEqual(high['entry_ids'], college['entry_ids'])
        self.assertEqual(college['composition'], '本科＋硕士')
        self.assertFalse(college['issues'])
        self.assertEqual(high['issues'][0]['kind'], 'coverage')
        self.assertEqual(self.lab.state(), before)

    def test_profile_preset_and_application_select_identical_ids(self):
        group = self.group()
        fields = [dict(id=s['id'],label=s['label'],collection=True,children=[]) for s in group['sets']]
        mappings = [mapping(s['id'],None,'education',s['requirement']) for s in group['sets']]
        app = Application(self.lab,Mapper(mappings))
        sid = self.lab.new_session()['id']
        app.scan(sid,dict(url='http://localhost/fiction',fields=fields,execution='local'))
        plan = app.plan(sid)
        self.assertFalse(plan['decisions'])
        for item, preset in zip(plan['automatic'], group['sets']):
            self.assertEqual([e['id'] for e in item['selected']],preset['entry_ids'])

    def test_changing_default_rebuilds_both_sets_without_copying_versions(self):
        before = self.lab.state()
        version = self.lab.create_version(self.ids['本科'],'degree','高中','学历更正版')
        self.assertEqual(self.group()['sets'][0]['entry_ids'],list(self.ids.values()))
        self.lab.set_default(self.ids['本科'],'degree',version['id'])
        college,high = self.group()['sets']
        self.assertEqual(college['entry_ids'],[self.ids['MPAcc']])
        self.assertEqual(high['composition'],'高中＋硕士')
        self.assertFalse(high['issues'])
        after = self.lab.state()
        self.assertEqual(len(before['entries']),len(after['entries']))
        self.assertEqual(len(before['answer_versions'])+1,len(after['answer_versions']))

    def test_unknown_education_remains_visible_as_unassigned(self):
        e=self.lab.mutate(lambda s:self.lab.new_entry(s,'education'))
        self.lab.save_profile([dict(entry_id=e['id'],field_id='school',value='虚构待补学校')])
        group=self.group()
        self.assertEqual(group['unassigned_ids'],[e['id']])
        self.assertTrue(all(any(i['kind']=='scope' for i in s['issues']) for s in group['sets']))
        self.assertTrue(all(e['id'] not in s['entry_ids'] for s in group['sets']))

    def test_empty_profile_has_sets_without_fabricated_members(self):
        state=copy.deepcopy(self.lab.state())
        state['entries']=[]
        group=next(g for g in profile_groups(state) if g['category']=='education')
        self.assertEqual(len(group['sets']),2)
        self.assertTrue(all(not s['entry_ids'] and s['issues'] for s in group['sets']))


if __name__=='__main__':
    unittest.main()
