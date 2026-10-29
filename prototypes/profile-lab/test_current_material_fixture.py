"""Fictional material UI with a deterministic mapper; no external calls."""
import signal
import tempfile
from lab import Lab,find
from profile_migration import prepare
from profile_library import ProfileLibrary,token
from application import Application
from server import make_server
from test_mapping_skill import StubMapper

class MaterialMapper(StubMapper):
    def call(self,prompt,schema):
        output,usage=super().call(prompt,schema)
        for d in output['decisions']:
            if d['question_id']=='combined':d.update(semantic_status='compose',sources=[dict(field_id='surname',covers='姓'),dict(field_id='given_name',covers='名')],plan=dict(kind='compose',transform=None,extracts=[]))
        return output,usage

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as directory:
        lab=Lab(directory);lab.mutate(lambda s:s.update(prepare(s,1000)[0]));library=ProfileLibrary(lab)
        state=lab.state();basic=next(e for e in state['entries'] if e['category']=='basic')
        library.save(dict(request_id='basic',entry_id=basic['id'],edit_token=token(state,basic),values={'name':'林晓','surname':'林','given_name':'晓'}))
        exam=library.save(dict(request_id='exam',category='language',record_type='exam',values={'exam_name':'示例考试','language_score':'500','exam_language':'英语'}))['record']
        library.save(dict(request_id='ability',category='language',record_type='ability',values={'language_name':'英语'},exam_ids=[exam['id']],links_revision=0))
        mapper=MaterialMapper({'name':'name','language':'language_name','exam':'exam_name','score':'language_score','combined':'surname'})
        app=Application(lab,mapper);sid=lab.new_session()['id']
        app.scan(sid,dict(url='https://fictional.example/form',title='虚构材料表单',fields=[dict(id='name',label='姓名'),dict(id='row',label='外语情况',collection=True,children=[dict(id='language',label='语种'),dict(id='exam',label='考试名称'),dict(id='score',label='分数')]),dict(id='combined',label='姓与名')]))
        lab.mutate(lambda s:find(s['sessions'],sid).update(form_analysis=dict(url='https://fictional.example/form',title='虚构材料表单',sections=[])))
        server=make_server(lab,mapper=mapper,browser_opener=lambda url:None)
        signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
        print(f'http://127.0.0.1:{server.server_port}/#practice/{sid}',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close();lab.db.close()
