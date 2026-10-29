"""Disposable new-contract UI; all people and content are fictional."""
import signal
import tempfile
from lab import Lab
from profile_migration import prepare
from profile_library import ProfileLibrary, token
from server import make_server


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as directory:
        lab=Lab(directory)
        lab.mutate(lambda state:state['entries'].append(dict(id='legacy_exam',category='language',record_type='unknown',values={'exam_name':'迁移虚构考试','language_score':'520','exam_level':'优秀'},default_versions={},sources={})))
        lab.mutate(lambda state:state.update(prepare(state,1000)[0]))
        lab.mutate(lambda state:state['profile_drafts'].update({'legacy-draft':dict(body=dict(category='education',values={'school':'旧版独立草稿大学'}),revision=1)}))
        lab.mutate(lambda state:state['imports'].append(dict(id='legacy-import',filename='legacy-fiction.txt',status='待确认',revision=1,candidates=[dict(id='legacy-candidate',category='education',field_id='school',label='学校名称',value='旧解析虚构学校',group='education:0',type='text',selected=True,source={},status='新增')],warnings=[])))
        library=ProfileLibrary(lab)
        for n,cat,values in [(1,'employment',{'company':'示例甲科技','employment_type':'实习','description':'完整原文，不得跨版补齐。','responsibilities':'分析需求','achievements':'形成报告'}),
                             (2,'employment',{'company':'示例乙科技','employment_type':'全职','description':'第二段虚构经历'}),
                             (3,'education',{'school':'示例大学','degree':'本科'})]:
            library.save(dict(request_id=str(n),category=cat,values=values))
        exam=library.save(dict(request_id='exam',category='language',record_type='exam',values={'exam_name':'示例考试','exam_language':'英语','language_score':'500'}))['record']
        ability=library.save(dict(request_id='ability',category='language',record_type='ability',values={'language_name':'英语','language_level':'熟练'}))['record']
        library.save(dict(request_id='link',entry_id=ability['id'],edit_token=ability['edit_token'],values={},exam_ids=[exam['id']],links_revision=0))
        server=make_server(lab,browser_opener=lambda url:None)
        signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
        print(f'http://127.0.0.1:{server.server_port}/',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close();lab.db.close()
