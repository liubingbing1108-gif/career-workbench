import copy
import unittest
from material_sets import MaterialSets, record_versions
from lab import LabError, find
from test_product_fixture import make_fixture

class MaterialSetTests(unittest.TestCase):
    def setUp(self):
        self.f, self.management, _ = make_fixture()
        self.lab, self.app, self.sid = self.f.lab, self.f.app, self.f.sid
        self.sets = MaterialSets(self.app)
    def tearDown(self):
        self.f.tearDown()
    def item(self):
        return next(i for i in self.app.plan(self.sid)['decisions'] if i['website_field']['id']=='internships')
    def record(self, entry, **values):
        return dict(entry_id=entry['id'],values={**entry['values'],**values},expected_values=entry['values'],
                    revisions={c['field']['id']:c['selected']['revision'] if c['selected'] else None for c in entry['choices']})
    def test_full_set_includes_nonwebsite_fields_and_atomic_selection(self):
        entry=self.item()['selected'][0];before=self.lab.state();record=self.record(entry,company='虚构新版本公司',description='',employment_type='')
        self.sets.save(self.sid,'internships',[record],'new','空字段版')
        changed=find(self.lab.state()['entries'],entry['id']);version=changed['set_versions'][-1]
        self.assertEqual(set(version['field_versions']),set(entry['values']))
        self.assertEqual(changed['default_versions'],find(before['entries'],entry['id'])['default_versions'])
        material=next(e for e in self.item()['catalog'] if e['id']==entry['id'])
        self.assertEqual(material['values']['description'],'')
        self.assertEqual(material['values']['employment_type'],'')
        self.sets.select(self.sid,'internships',entry['id'],'default')
        restored=next(e for e in self.item()['catalog'] if e['id']==entry['id'])
        self.assertEqual(restored['values'],entry['values'])
    def test_session_full_set_does_not_modify_shared_profile_or_other_job(self):
        entry=self.item()['selected'][0];before=self.lab.state()
        self.sets.save(self.sid,'internships',[self.record(entry,employment_type='实习',description='本次虚构内容')])
        after=self.lab.state()
        for key in ['entries','versions','answer_versions','files']:
            self.assertEqual(after[key],before[key])
        self.assertEqual(after['sessions'][1],before['sessions'][1])
        preview=self.f.prep.current(self.sid)
        row=next(r for r in preview['rows'] if r['website_id']=='internships')
        self.assertIn('本次虚构内容',str(row))
        self.assertNotIn('employment_type',str(row))
    def test_invalid_later_record_rolls_back_whole_module(self):
        entries=self.item()['selected'];records=[self.record(e) for e in entries]
        records[1]['values']['started']='not-a-date';before=self.lab.state()
        with self.assertRaises(LabError):self.sets.save(self.sid,'internships',records,'new','完整组合',True)
        self.assertEqual(self.lab.state(),before)
    def test_stale_set_and_foreign_field_rejected_without_partial_write(self):
        entry=self.item()['selected'][0];record=self.record(entry);record['expected_values']['role']='旧值';before=self.lab.state()
        with self.assertRaises(LabError):self.sets.save(self.sid,'internships',[record],'new')
        self.assertEqual(self.lab.state(),before)
        record=self.record(self.item()['selected'][0]);record['values']['school']='错误对象'
        with self.assertRaises(LabError):self.sets.save(self.sid,'internships',[record],'new')
        self.assertEqual(self.lab.state(),before)
    def test_saved_composition_restores_order_values_and_survives_reopen(self):
        entries=self.item()['selected'];self.sets.save(self.sid,'internships',[self.record(e) for e in entries],'new','组合一',True)
        version=self.item()['composition_versions'][0]
        self.app.select_entries(self.sid,'employment',[entries[1]['id']],'internships')
        self.sets.select_composition(self.sid,'internships',version['id'])
        self.assertEqual([e['id'] for e in self.item()['selected']],[e['id'] for e in entries])
        from lab import Lab
        reopened=Lab(self.f.temp.name)
        try:self.assertEqual(reopened.state()['sessions'],self.lab.state()['sessions'])
        finally:reopened.db.close()
    def test_education_module_keeps_website_scope_and_exposes_complete_fields(self):
        edu=next(i for i in self.app.plan(self.sid)['automatic'] if i['website_field']['id']=='edu')
        entry=edu['selected'][0]
        self.assertIn('school',entry['values'])
        self.sets.save(self.sid,'edu',[self.record(entry)],'new','教育版',True)
        self.assertEqual(len(next(i for i in self.app.plan(self.sid)['automatic'] if i['website_field']['id']=='edu')['selected']),1)

    def test_all_blank_version_remains_visible_with_skipped_answers(self):
        entry=self.item()['selected'][0]
        blank={fid:'' for fid in entry['values']}
        self.sets.save(self.sid,'internships',[self.record(entry,**blank)],'new','空白组',True)
        item=self.item();version=item['composition_versions'][-1]
        self.assertTrue(any(e['id']==entry['id'] for e in item['catalog']))
        self.assertTrue(self.f.prep.current(self.sid)['skipped'])
        self.sets.select(self.sid,'internships',entry['id'],'default')
        self.sets.select_composition(self.sid,'internships',version['id'])
        restored=next(e for e in self.item()['catalog'] if e['id']==entry['id'])
        self.assertTrue(all(v=='' for v in restored['values'].values()))

    def test_known_field_version_is_accessible_as_a_record_variant(self):
        entry=self.item()['selected'][0]
        field=find(self.lab.state()['fields'],'role')
        from lab import put_answer
        version=self.lab.mutate(lambda state:put_answer(state,find(state['entries'],entry['id']),field,'另一个虚构岗位'))
        self.sets.select(self.sid,'internships',entry['id'],'field:'+version['id'])
        selected=next(e for e in self.item()['catalog'] if e['id']==entry['id'])
        self.assertEqual(selected['values']['role'],'另一个虚构岗位')

class MaterialControlTests(unittest.TestCase):
    setUp = MaterialSetTests.setUp
    tearDown = MaterialSetTests.tearDown
    item = MaterialSetTests.item
    record = MaterialSetTests.record
    def test_record_remove_restore_is_local_and_persistent(self):
        entry=self.item()['selected'][0];before=self.lab.state()
        self.sets.control(self.sid,'internships','remove-record',entry['id'])
        self.assertNotIn(entry['id'],[e['id'] for e in self.item()['catalog']])
        self.assertNotIn('removed_records',self.item())
        self.assertNotIn(entry['id'],str(self.f.prep.current(self.sid)['rows']))
        self.sets.control(self.sid,'internships','restore-record',entry['id'])
        self.app.select_entries(self.sid,'employment',[entry['id']],'internships')
        self.assertEqual(self.item()['selected'][0]['values'],entry['values'])
        after=self.lab.state()
        for key in ['entries','versions','answer_versions','files']:
            self.assertEqual(after[key],before[key])
        self.assertEqual(after['sessions'][1],before['sessions'][1])

    def test_omitted_module_never_reaches_execution_materials(self):
        self.f.complete();before=self.lab.state();original=self.f.prep.preview(self.sid)
        self.sets.control(self.sid,'internships','remove-module')
        content=self.f.prep.current(self.sid)
        self.assertFalse(any(r['website_id']=='internships' for r in content['rows']))
        self.assertFalse(any(r['website_id']=='internships' for r in content['omitted_materials']))
        with self.assertRaises(LabError):self.f.prep.start(self.sid,original['digest'])
        content=self.f.prep.preview(self.sid);queued=self.f.prep.start(self.sid,content['digest'])
        self.assertNotIn('internships',[r['website_id'] for r in queued['confirmed_materials']['rows']])
        self.f.prep.pause(self.sid)
        self.sets.control(self.sid,'internships','include',included=True)
        self.assertFalse(self.item()['removed']);self.assertTrue(self.item()['included'])
        self.assertEqual(len(self.item()['selected']),2)

    def test_empty_scalar_controls_and_required_removal_stay_visible(self):
        self.sets.control(self.sid,'new','remove-module')
        plan=self.app.plan(self.sid)
        scalar=next(i for i in plan['material_items'] if i['website_field']['id']=='new')
        self.assertTrue(scalar['removed']);self.assertFalse(scalar['included'])
        self.assertTrue(any(i['website_field']['id']=='new' and i['blocking'] for i in plan['missing']))
        self.sets.control(self.sid,'new','restore-module');self.f.complete()
        self.sets.control(self.sid,'new','include',included=False)
        self.assertTrue(self.f.prep.current(self.sid)['skipped'])

    def test_blank_optional_scalar_can_be_omitted_and_restored(self):
        self.lab.mutate(lambda state:find(find(state['sessions'],self.sid)['website']['fields'],'new').update(decision_required=False))
        self.f.prep.settings(self.sid,'')
        self.sets.control(self.sid,'new','include',included=False)
        content=self.f.prep.current(self.sid)
        self.assertFalse(content['pending'])
        self.assertFalse(any(r['website_id']=='new' for r in content['rows']))
        self.sets.control(self.sid,'new','include',included=True)
        self.assertTrue(self.f.prep.current(self.sid)['skipped'])

    def test_versions_are_hidden_locally_and_can_be_restored(self):
        entries=self.item()['selected']
        self.sets.save(self.sid,'internships',[self.record(e) for e in entries],'new','保留组合',True)
        item=self.item();version=item['composition_versions'][0];entry=item['selected'][0];vid=entry['selected_set'];before=self.lab.state()
        self.sets.control(self.sid,'internships','remove-version',entry['id'],vid)
        self.assertNotIn(vid,[v['id'] for v in self.item()['selected'][0]['set_versions']])
        self.sets.control(self.sid,'internships','restore-versions',entry['id'])
        self.assertIn(vid,[v['id'] for v in self.item()['selected'][0]['set_versions']])
        self.sets.select(self.sid,'internships',entry['id'],'default')
        self.sets.control(self.sid,'internships','remove-version',entry['id'],'default')
        self.assertNotIn('default',[v['id'] for v in self.item()['selected'][0]['set_versions']])
        self.sets.control(self.sid,'internships','restore-versions',entry['id'])
        self.sets.control(self.sid,'internships','remove-composition',version_id=version['id'])
        self.assertEqual(self.item()['composition_versions'],[])
        self.sets.control(self.sid,'internships','restore-compositions')
        self.assertEqual(self.item()['composition_versions'],[version])
        after=self.lab.state()
        for key in ['entries','versions','answer_versions','files']:
            self.assertEqual(after[key],before[key])
        self.assertEqual(find(after['sessions'],self.sid)['composition_versions'],find(before['sessions'],self.sid)['composition_versions'])

if __name__=='__main__':unittest.main()
