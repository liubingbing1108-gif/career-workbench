"""D93: isolated partial-fill UI fixture, with no website or model calls."""
import copy
import signal
from test_product_fixture import make_fixture
from server import make_server

if __name__ == '__main__':
    fixture, app, module = make_fixture()
    session=fixture.app.plan(fixture.sid)['session']
    manifest=copy.deepcopy(session['website'])
    mappings=copy.deepcopy(manifest['mappings'])
    manifest['fields'].append(dict(id='languages',label='语言能力',collection=True,required=False,children=[dict(id='language-name',label='语言名称')]))
    mappings.append(dict(website_id='languages',status='ambiguous',reason='语言与考试的对应尚不明确，本次留空',category=None,field_id=None,members=[]))
    fixture.app.install_mapping(fixture.sid,manifest,{'mappings':mappings,'engine':'虚构测试映射'})
    server=make_server(fixture.lab,management_app=app,management_handler=module.handler(app),browser_opener=lambda url:None)
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    print(f'http://127.0.0.1:{server.server_port}/',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();fixture.tearDown()
