"""Fictional language records, with a legacy model's whole-module ambiguity."""
import copy
import tempfile
import unittest
from lab import Lab, find
from application import Application
from requirements import requirement


def add_language_fixture(lab, app, sid):
    for fid, label in [('language', '语言'), ('language_proficiency', '熟练程度')]:
        if not any(f['id'] == fid for f in lab.state()['fields']):
            lab.add_field(dict(id=fid, label=label, category='language', type='text'))
    entry = lab.mutate(lambda s: lab.new_entry(s, 'language'))
    lab.save_profile([dict(entry_id=entry['id'], field_id=k, value=v) for k,v in
        {'language_name':'测试语种', 'language':'测试语种', 'language_level':'熟练',
         'language_proficiency':'熟练', 'listening':'熟练', 'speaking':'熟练',
         'reading':'熟练', 'writing':'熟练'}.items()])
    exam = lab.mutate(lambda s: lab.new_entry(s, 'language'))
    lab.save_profile([dict(entry_id=exam['id'], field_id='exam_name', value='虚构考试')])
    lab.mutate(lambda s: find(s['entries'], exam['id']).update(record_type='exam'))
    current = find(lab.state()['sessions'], sid).get('website')
    manifest = copy.deepcopy(current or dict(url='https://example.com/apply', fields=[], mappings=[]))
    mappings = manifest.pop('mappings')
    manifest['fields'].append(dict(id='languages', label='语言能力', collection=True, children=[
        dict(id='lang-name',label='语言类型',type='text'),
        *[dict(id=fid,label=label,type='select',options=['一般','良好','熟练','精通']) for fid,label in
          [('lang-level','掌握程度'),('lang-ls','听说'),('lang-rw','读写')]]]))
    mappings.append(dict(website_id='languages', category='language', status='ambiguous', field_id=None,
        reason='同义旧字段有多个候选', requirement=requirement('language_abilities'), members=[
        dict(website_id=fid,field_id=None,new_field=None) for fid in ['lang-name','lang-level','lang-ls','lang-rw']]))
    # Simulate a persisted old scan: compatibility must work without a model rerun.
    lab.mutate(lambda s: find(s['sessions'], sid).update(website={**manifest,'contract_version':2,'mappings':mappings}))
    return entry, exam, manifest, mappings


class LanguageMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.lab=Lab(self.temp.name);self.app=Application(self.lab)
        self.sid=self.lab.new_session()['id']
        self.entry,self.exam,self.manifest,self.maps=add_language_fixture(self.lab,self.app,self.sid)
    def tearDown(self):self.lab.db.close();self.temp.cleanup()
    def test_old_scan_reuses_matching_synonyms_and_exposes_combined_inputs(self):
        before=self.lab.state();plan=self.app.plan(self.sid)
        module=plan['automatic'][0]
        self.assertEqual([e['id'] for e in module['selected']],[self.entry['id']])
        self.assertEqual(module['value'][0]['language_name'],'测试语种')
        self.assertEqual(module['value'][0]['language_level'],'熟练')
        self.assertEqual({m['child_id'] for m in plan['missing']},{'lang-ls','lang-rw'})
        self.assertTrue(all(m['editable'] for m in plan['missing']))
        self.assertEqual(self.lab.state(),before,'read-only recovery preserves every stored value')
    def test_new_mapping_gets_same_validated_field_contract(self):
        self.app.install_mapping(self.sid,self.manifest,dict(mappings=self.maps))
        self.assertEqual(self.app.plan(self.sid)['website']['mappings'][0]['status'],'mapped')
    def test_combined_level_saves_session_only_and_survives_reload(self):
        before=self.lab.state()
        self.app.edit_answer(self.sid,'languages','良好','session',entry_id=self.entry['id'],child_id='lang-ls')
        plan=Application(self.lab).plan(self.sid)
        self.assertEqual({m['child_id'] for m in plan['missing']},{'lang-rw'})
        self.assertIn('良好',plan['automatic'][0]['value'][0].values())
        for key in ['entries','versions','answer_versions','files']:
            self.assertEqual(self.lab.state()[key],before[key])
    def test_conflicting_synonyms_only_need_that_field_confirmed(self):
        self.lab.save_profile([dict(entry_id=self.entry['id'],field_id='language_proficiency',value='一般')])
        missing=self.app.plan(self.sid)['missing']
        conflict=next(m for m in missing if m['child_id']=='lang-level')
        self.assertTrue(conflict['editable']);self.assertIn('不一致',conflict['message'])
        self.app.edit_answer(self.sid,'languages','良好','session',entry_id=self.entry['id'],child_id='lang-level')
        self.assertNotIn('lang-level',{m['child_id'] for m in self.app.plan(self.sid)['missing']})
    def test_unknown_scope_is_not_promoted(self):
        self.lab.mutate(lambda s:find(s['sessions'],self.sid)['website']['mappings'][0].update(requirement=None))
        self.assertFalse(self.app.plan(self.sid)['automatic'])
    def test_prose_scope_restriction_is_not_dropped(self):
        self.lab.mutate(lambda s:find(s['sessions'],self.sid)['website']['fields'][0].update(instructions='仅填写有效的商务语言能力'))
        self.assertFalse(self.app.plan(self.sid)['automatic'])
    def test_legacy_only_value_is_reused_without_writing_profile(self):
        self.lab.save_profile([dict(entry_id=self.entry['id'],field_id='language_level',value='')])
        before=self.lab.state()
        self.assertEqual(self.app.plan(self.sid)['automatic'][0]['value'][0]['language_level'],'熟练')
        self.assertEqual(self.lab.state(),before)
    def test_new_ability_record_can_be_added_and_edited(self):
        entry=self.app.add_entry(self.sid,'languages')
        self.assertEqual(entry['record_type'],'ability')
        self.app.edit_answer(self.sid,'languages','第二测试语种','session',entry_id=entry['id'],child_id='lang-name')
        self.assertIn(entry['id'],[e['id'] for e in self.app.plan(self.sid)['automatic'][0]['selected']])


if __name__ == '__main__':
    from test_product_fixture import make_fixture
    from server import make_server
    f, management, module = make_fixture()
    add_language_fixture(f.lab,f.app,f.sid)
    server=make_server(f.lab,management_app=management,management_handler=module.handler(management),browser_opener=lambda url:None)
    print(f'http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    finally:server.server_close();f.tearDown()
