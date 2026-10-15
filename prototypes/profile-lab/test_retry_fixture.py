"""D95 isolated retry UI fixture, no real browser or model connections."""
import signal
from test_product_fixture import make_fixture
from server import make_server
from preparation import Preparation

if __name__ == '__main__':
    f, app, module = make_fixture()
    prep=Preparation(f.lab,f.app)
    preview=prep.preview(f.sid)
    execution=prep.start(f.sid,preview['digest'])
    def stop(state):
        session=next(s for s in state['sessions'] if s['id']==f.sid)
        session['preparation']['execution'].update(status='failed',filled=2,message='执行超时，已停止后续动作')
    f.lab.mutate(stop)
    server=make_server(f.lab,management_app=app,management_handler=module.handler(app),browser_opener=lambda url:None)
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    print(f'http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();f.tearDown()
