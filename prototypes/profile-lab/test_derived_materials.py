import tempfile
import unittest
from lab import Lab,LabError,find
from application import Application
from profile_library import ProfileLibrary,token
from profile_migration import prepare
from test_mapping_skill import StubMapper
from derived_materials import preview,confirm,request_excerpt

class ComposeMapper(StubMapper):
    def call(self,prompt,schema):
        output,usage=super().call(prompt,schema)
        d=output['decisions'][0];d.update(semantic_status='compose',sources=[dict(field_id='surname',covers='姓'),dict(field_id='given_name',covers='名')],plan=dict(kind='compose',transform=None,extracts=[]))
        return output,usage

class ExcerptMapper(StubMapper):
    def call(self,prompt,schema):
        output,usage=super().call(prompt,schema);req=self.calls[-1][2];d=output['decisions'][0]
        if not req['source_spans']:
            d.update(semantic_status='unresolved',plan=dict(kind='none',transform=None,extracts=[]),clarification='需选取最小原文核对')
        else:
            span=req['source_spans'][0]
            d.update(semantic_status='extract_candidate',plan=dict(kind='extract',transform=None,extracts=[dict(span_id=span['id'],start=0,end=len(span['text']),covers='所需内容')]),availability=dict(status='draft_required',check_id=None))
        return output,usage

class DerivedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name);self.lab.mutate(lambda s:s.update(prepare(s,1000)[0]));self.sid=self.lab.new_session()['id'];self.library=ProfileLibrary(self.lab)
        state=self.lab.state();self.basic=next(e for e in state['entries'] if e['category']=='basic')
        self.library.save(dict(request_id='base',entry_id=self.basic['id'],edit_token=token(state,self.basic),values={'surname':'林','given_name':'晓'}))
        self.app=Application(self.lab,ComposeMapper({'full':'surname'}));self.app.scan(self.sid,dict(url='https://fictional.example/form',fields=[dict(id='full',label='姓与名')]))
    def tearDown(self):self.lab.db.close();self.tmp.cleanup()
    def test_composed_draft_needs_confirmation_and_never_writes_profile(self):
        self.assertFalse(self.app.plan(self.sid)['payload'])
        p=preview(self.app,self.lab.state(),self.sid,'full');self.assertEqual(p['suggestion'],'林\n晓')
        args=dict(session_id=self.sid,website_id='full',entry_ids=p['selected_ids'],token=p['token'],value='林 晓',confirmed=True)
        before=self.lab.state();self.lab.mutate(lambda s:confirm(self.app,s,args));after=self.lab.state()
        for key in ('fields','entries','versions','answer_versions','files'):self.assertEqual(before[key],after[key])
        self.assertEqual(self.app.plan(self.sid)['payload'][0]['value'],'林 晓')
    def test_source_changes_invalidate_old_confirmation_but_keep_draft(self):
        p=preview(self.app,self.lab.state(),self.sid,'full');args=dict(session_id=self.sid,website_id='full',entry_ids=p['selected_ids'],token=p['token'],value='林 晓',confirmed=True)
        self.lab.mutate(lambda s:confirm(self.app,s,args));state=self.lab.state();e=find(state['entries'],self.basic['id'])
        self.library.save(dict(request_id='changed',entry_id=e['id'],edit_token=token(state,e),values={'given_name':'新'}))
        self.assertFalse(self.app.plan(self.sid)['payload']);self.assertEqual(find(self.lab.state()['sessions'],self.sid)['derived_answers']['full']['value'],'林 晓')
        with self.assertRaises(LabError):self.lab.mutate(lambda s:confirm(self.app,s,args))
    def test_only_selected_excerpt_reaches_mapper_and_override_invalidates_it(self):
        state=self.lab.state();e=find(state['entries'],self.basic['id'])
        self.library.save(dict(request_id='fictional-text',entry_id=e['id'],edit_token=token(state,e),values={'given_name':'未发送甲需要摘取的句子未发送乙'}))
        mapper=ExcerptMapper({'excerpt':'given_name'});app=Application(self.lab,mapper)
        app.scan(self.sid,dict(url='https://fictional.example/form',fields=[dict(id='excerpt',label='需要摘取的内容')]))
        p=preview(app,self.lab.state(),self.sid,'excerpt');self.assertTrue(p['needs_excerpt'])
        args=dict(session_id=self.sid,website_id='excerpt',entry_ids=p['selected_ids'],entry_id=e['id'],field_id='given_name',token=p['token'],start=4,end=11,confirmed_excerpt=True)
        with self.assertRaises(LabError):request_excerpt(app,{**args,'confirmed_excerpt':False})
        self.assertEqual(len(mapper.calls),1)
        request_excerpt(app,args);sent=mapper.calls[-1][0]
        self.assertNotIn('未发送甲',sent);self.assertNotIn('未发送乙',sent);self.assertIn('需要摘取的句子',sent)
        p=preview(app,self.lab.state(),self.sid,'excerpt');self.assertEqual(p['suggestion'],'需要摘取的句子');self.assertFalse(p['needs_excerpt'])
        self.assertFalse(app.plan(self.sid)['payload'])
        self.lab.mutate(lambda s:confirm(app,s,dict(session_id=self.sid,website_id='excerpt',entry_ids=p['selected_ids'],token=p['token'],value=p['suggestion'],confirmed=True)))
        self.assertEqual(app.plan(self.sid)['payload'][0]['value'],'需要摘取的句子')
        def override(state):
            session=find(state['sessions'],self.sid);session.setdefault('scoped_overrides',{}).setdefault('excerpt',{})[e['id']+'/given_name']='后来修改的本次文字'
        self.lab.mutate(override)
        self.assertFalse(app.plan(self.sid)['payload'])

if __name__=='__main__':unittest.main()
