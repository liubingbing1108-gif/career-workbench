import tempfile
import unittest
from pathlib import Path
from lab import Lab, LabError, default_version
from application import Application
from requirements import requirement
from test_recognizer import FakeRecognizer, sample

class FixtureMapper:
    def __init__(self,mapping):self.mapping=mapping
    def map(self,fields,profile):
        result = {'engine':'离线虚构夹具映射','mappings':[{'website_id':f['id'],'field_id':self.mapping.get(f['id'],(None,None))[0],'category':self.mapping.get(f['id'],(None,None))[1],'status':'mapped' if f['id'] in self.mapping else 'new','reason':'测试契约'} for f in fields]}
        for m in result['mappings']:
            if m['category'] in {'education','employment','certificates','family'}:
                m['requirement']=requirement(m['website_id'],'choose' if m['category']=='employment' else 'all')
        return result

class IncrementApplicationTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.lab=Lab(self.temp.name)
    def tearDown(self):self.lab.db.close();self.temp.cleanup()
    def resolve(self,ids=None,mode='new',**extra):
        inc=self.lab.increments();return self.lab.resolve_import([{'candidate_id':c['id'],'mode':mode,**extra} for c in inc['candidates'] if ids is None or c['id'] in ids],inc['revisions'])
    def import_semantic(self,text,result):
        self.lab.recognizer=FakeRecognizer([result]);return self.lab.upload('fiction.txt',text.encode())
    def test_confirmed_identical_fields_and_description_are_not_pending(self):
        text,result=sample();self.import_semantic(text,result);self.resolve()
        before=self.lab.state();self.import_semantic(text,result)
        self.assertEqual(self.lab.increments()['candidates'],[])
        self.assertEqual(len(self.lab.state()['versions']),len(before['versions']))
        self.assertEqual(len(self.lab.state()['answer_versions']),len(before['answer_versions']))
    def test_pending_identical_across_files_has_one_decision_and_multiple_sources(self):
        text,result=sample();self.import_semantic(text,result);self.import_semantic(text,result)
        inc=self.lab.increments();self.assertEqual(len(inc['candidates']),13);self.assertEqual(inc['merged'],13)
        self.assertTrue(all(len(c['other_sources'])==1 for c in inc['candidates']))
        self.resolve();self.assertFalse(self.lab.increments()['candidates'])
    def test_only_changed_content_is_pending_ignore_and_reupload_stays_ignored(self):
        text,result=sample();self.import_semantic(text,result);self.resolve()
        text,result=sample('新增版描述。');self.import_semantic(text,result)
        inc=self.lab.increments();self.assertEqual([c['field_id'] for c in inc['candidates']],['description'])
        self.resolve(mode='ignore');self.import_semantic(text,result);self.assertFalse(self.lab.increments()['candidates'])
        self.assertEqual(self.lab.state()['versions'][0]['content'],'参与整理样例项目资料。')
    def test_replace_new_and_default_are_distinct_and_bytes_unchanged(self):
        text,result=sample();preview=self.import_semantic(text,result);self.resolve()
        old=self.lab.state()['versions'][0]
        text2,result2=sample('第二版描述。');self.import_semantic(text2,result2);self.resolve()
        state=self.lab.state();self.assertEqual(len(state['versions']),2)
        entry=next(e for e in state['entries'] if e['category']=='employment')
        self.assertEqual(default_version(state,entry,'description')['id'],old['id'])
        self.lab.set_default(entry['id'],'description',state['versions'][1]['id'])
        text3,result3=sample('替换默认描述。');self.import_semantic(text3,result3);self.resolve(mode='replace')
        self.assertEqual(len(self.lab.state()['versions']),2)
        self.assertEqual(default_version(self.lab.state(),next(e for e in self.lab.state()['entries'] if e['id']==entry['id']),'description')['content'],'替换默认描述。')
        self.assertEqual(self.lab.file_bytes(preview['file_id'])[1],text.encode())
    def test_old_consistent_preview_does_not_reappear_after_user_replaces_version(self):
        text,result=sample();self.import_semantic(text,result);self.resolve();self.import_semantic(text,result)
        text,result=sample('替换后的新文本。');self.import_semantic(text,result);self.resolve(mode='replace')
        self.assertFalse(self.lab.increments()['candidates'])

    def test_scalar_alternative_does_not_replace_default_without_explicit_replace(self):
        self.lab.upload('a.txt',b'Name: A');self.resolve();self.lab.upload('b.txt',b'Name: B');self.resolve()
        state=self.lab.state();entry=next(e for e in state['entries'] if e['category']=='basic')
        self.assertEqual(entry['values']['name'],'A');self.assertEqual(len(state['answer_versions']),2)
        self.lab.upload('c.txt',b'Name: C');self.resolve(mode='replace');self.assertEqual(self.lab.state()['entries'][0]['values']['name'],'C')
    def app(self):
        app=Application(self.lab,FixtureMapper({'a':('name','basic'),'b':(None,'employment')}));session=self.lab.new_session()['id']
        app.scan(session,{'url':'http://localhost/test','execution':'local','fields':[{'id':'a','label':'名字','required':True},{'id':'b','label':'工作经历','collection':True,'required':True},{'id':'f','label':'新增问题F','required':True,'type':'text'}]})
        return app,session
    def test_website_first_choices_multiple_entries_exact_versions_and_order(self):
        self.lab.save_profile([{'entry_id':self.lab.state()['entries'][0]['id'],'field_id':'name','value':'虚构姓名'}])
        entries=[]
        for name in ['甲','乙','丙']:
            e=self.lab.mutate(lambda s:self.lab.new_entry(s,'employment'));entries.append(e)
            self.lab.save_profile([{'entry_id':e['id'],'field_id':'company','value':name}])
            self.lab.create_version(e['id'],'description',name+'默认');self.lab.create_version(e['id'],'description',name+'新版本')
        app,sid=self.app();app.select_entries(sid,'employment',[entries[1]['id'],entries[0]['id']])
        second=next(v for v in self.lab.state()['versions'] if v['entry_id']==entries[1]['id'] and v['content']=='乙新版本');app.select_version(sid,'b',second['id'],entries[1]['id'],'description')
        plan=app.plan(sid);self.assertEqual(len(plan['decisions']),1)
        self.assertEqual(plan['automatic'][0]['value'],'虚构姓名')
        chosen=plan['payload'][1]['value'];self.assertEqual([r['company'] for r in chosen],['乙','甲']);self.assertEqual([r['description'] for r in chosen],['乙新版本','甲默认'])
        self.assertNotIn('丙',str(chosen))
        app.select_entries(sid,'employment',[]);self.assertTrue(any(i['website_field']['id']=='b' for i in app.plan(sid)['missing']))
    def test_materials_keeps_multiple_entries_as_arrays_instead_of_first(self):
        for value in ['甲公司','乙公司']:
            e=self.lab.mutate(lambda s:self.lab.new_entry(s,'employment'))
            self.lab.save_profile([{'entry_id':e['id'],'field_id':'company','value':value}])
        materials=self.lab.materials(self.lab.new_session()['id'])
        self.assertNotIn('company',materials['values'])
        self.assertEqual([e['values']['company'] for e in materials['entries']['employment']],['甲公司','乙公司'])

    def test_new_website_field_update_creates_first_version_and_reuses_later(self):
        app,sid=self.app();result=app.edit_answer(sid,'f','新答案','update')
        fid=result['field']['id'];state=self.lab.state();self.assertTrue(any(f['id']==fid for f in state['fields']))
        self.assertEqual(len([v for v in state['answer_versions'] if v['field_id']==fid]),0)
        item=next(i for i in app.plan(sid)['payload'] if i['website_field']['id']=='f');self.assertEqual(item['value'],'新答案')
        later=self.lab.new_session()['id'];app.mapper=FixtureMapper({'f':(fid,'additional')});app.scan(later,{'url':'http://localhost/later','fields':[{'id':'f','label':'新增问题F'}]})
        self.assertNotIn('新答案',str(app.plan(later)['payload']))
    def test_session_answer_creates_definition_but_not_shared_answer(self):
        app,sid=self.app();result=app.edit_answer(sid,'f','仅本次','session');fid=result['field']['id']
        self.assertEqual(next(i for i in app.plan(sid)['payload'] if i['website_field']['id']=='f')['value'],'仅本次')
        self.assertFalse(any(v['field_id']==fid for v in self.lab.state()['answer_versions']))
        self.assertNotIn('仅本次',str([e['values'] for e in self.lab.state()['entries']]))
    def test_new_field_session_then_update_clears_temporary_override(self):
        app,sid=self.app();result=app.edit_answer(sid,'f','临时答案','session')
        app.edit_answer(sid,'f','正式答案','update')
        self.assertEqual(next(i for i in app.plan(sid)['payload'] if i['website_field']['id']=='f')['value'],'正式答案')
        self.assertFalse(any(v['field_id']==result['field']['id'] for v in self.lab.state()['answer_versions']))

    def test_scalar_legacy_save_modes_remain_session_only(self):
        app,sid=self.app();before=self.lab.state()['entries']
        for mode in ['session','update','new']:
            res=app.edit_answer(sid,'f',mode+'本次值',mode)
            self.assertEqual(next(i for i in app.plan(sid)['payload'] if i['website_field']['id']=='f')['value'],mode+'本次值')
            self.assertFalse(any(v['field_id']==res['field']['id'] for v in self.lab.state()['answer_versions']))
        self.assertEqual(self.lab.state()['entries'],before)
    def test_basic_multiple_versions_reuse_default_without_reconfirmation(self):
        self.lab.upload('a.txt',b'Name: A');self.resolve();self.lab.upload('b.txt',b'Name: B');self.resolve()
        app,sid=self.app();self.assertFalse(any(i['website_field']['id']=='a' for i in app.plan(sid)['decisions']))
        self.assertEqual(next(i for i in app.plan(sid)['automatic'] if i['website_field']['id']=='a')['value'],'A')

    def test_invalid_semantic_field_position_rejected_without_state_write(self):
        app=Application(self.lab,FixtureMapper({'x':('nonexistent','basic')}));sid=self.lab.new_session()['id'];before=self.lab.state()
        with self.assertRaises(LabError):app.scan(sid,{'url':'http://localhost/test','fields':[{'id':'x','label':'名字'}]})
        self.assertEqual(self.lab.state(),before)

    def test_website_length_limit_applies_to_edit_of_existing_version(self):
        app,sid=self.app();res=app.edit_answer(sid,'f','短文','update');fid=res['field']['id']
        self.lab.mutate(lambda s:next(f for f in next(x for x in s['sessions'] if x['id']==sid)['website']['fields'] if f['id']=='f').update(maxLength=3))
        before=self.lab.state()
        with self.assertRaises(LabError):app.edit_answer(sid,'f','超过三个字','update')
        self.assertEqual(before,self.lab.state())

    def test_bad_mapper_and_old_revision_cannot_mutate(self):
        self.lab.upload('a.txt',b'Name: A');inc=self.lab.increments();self.lab.upload('b.txt',b'Name: B');before=self.lab.state()
        with self.assertRaises(LabError):self.lab.resolve_import([{'candidate_id':inc['candidates'][0]['id'],'mode':'replace'}],inc['revisions'])
        self.assertEqual(before,self.lab.state())

if __name__=='__main__':unittest.main()
