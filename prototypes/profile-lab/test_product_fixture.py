"""Disposable, offline fixture for manually exercising the unified UI."""
import copy
import importlib.util
from pathlib import Path
import signal
import sys
from server import make_server
from test_preparation import PreparationTests
from test_requirement_sets import mapping, requirement


def make_fixture():
    f = PreparationTests(); f.setUp()
    mdir = Path(__file__).resolve().parents[1] / 'management-lab'
    sys.path.insert(0, str(mdir))
    spec = importlib.util.spec_from_file_location('product_ui_fixture_management', mdir / 'server.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    app = m.App(Path(f.temp.name) / 'management', config='/nonexistent/test-config.json')
    from intake import JobIntake
    class FixtureModel:
        def call(self,prompt,schema):
            return {'jobs':[{'company':'示例公司','role':'产品经理','url':'https://example.com/new-job','evidence':'示例公司 产品经理','requires_preference':False}]},{}
    app.intake=JobIntake(FixtureModel(),lambda u:('示例公司 产品经理',[]))
    app.official.reader=lambda u:{'body':'示例公司 产品经理 岗位职责','links':[],'final_url':u}
    preview = app.store.preview_text('示例公司 | 产品岗位甲 | https://example.com/apply\n示例公司 | 产品岗位乙 | https://example.com/apply')
    for row in preview['candidates']:
        row.update(official_url_status='verified',official_entry={'url':row['url'],'verification':'fictional_fixture'})
    ids = app.store.import_selected(preview['candidates'], [{'id': '0'}, {'id': '1'}], 'offline-ui-fixture', {})['ids']
    interns = []
    for index, company in enumerate(['示例甲科技', '示例乙科技', '示例丙科技']):
        entry = f.lab.mutate(lambda state: f.lab.new_entry(state, 'employment'))
        values = {'company': company, 'role': '产品实习', 'started': f'202{index + 3}-01',
                  'ended': f'202{index + 3}-06', 'employment_type': '实习'}
        f.lab.save_profile([{'entry_id': entry['id'], 'field_id': key, 'value': value} for key, value in values.items()])
        f.lab.create_version(entry['id'], 'description', f'示例经历 {index + 1}：完成虚构功能设计。', '简洁版')
        f.lab.create_version(entry['id'], 'description', f'示例经历 {index + 1}：完成虚构功能设计和用户测试。', '详细版')
        interns.append(entry['id'])
    manifest, maps = copy.deepcopy(f.manifest), copy.deepcopy(f.maps)
    children = [dict(id=key, label=label, required=True) for key, label in
                [('company', '公司'), ('role', '职位'), ('started', '开始年月'), ('ended', '结束年月'), ('description', '描述')]]
    manifest['title'] = '产品岗位甲'
    manifest['fields'].append(dict(id='internships', label='实习经历', collection=True, children=children))
    item = mapping('internships', None, 'employment', requirement('internships', 'choose', summary='选择本次实习组合、顺序和每段版本'))
    item['members'] = [dict(website_id=child['id'], field_id=child['id']) for child in children]
    maps['mappings'].append(item)
    f.app.install_mapping(f.sid, manifest, maps)
    f.app.select_entries(f.sid, 'employment', interns[:2], 'internships')
    def sessions(state):
        first = next(s for s in state['sessions'] if s['id'] == f.sid)
        first.update(name='产品岗位甲', management_job_id=ids[0])
        first['form_analysis']['title'] = '产品岗位甲'
        other = copy.deepcopy(first); other.update(id='session_fixture_b', name='产品岗位乙', management_job_id=ids[1])
        other['form_analysis']['title'] = other['website']['title'] = '产品岗位乙'
        state['sessions'].append(other)
    f.lab.mutate(sessions)
    return f, app, m


if __name__ == '__main__':
    fixture, app, module = make_fixture()
    server = make_server(fixture.lab, management_app=app, management_handler=module.handler(app),browser_opener=lambda url: None)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    print(f'http://127.0.0.1:{server.server_port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close(); fixture.tearDown()
