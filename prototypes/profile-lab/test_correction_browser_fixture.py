"""Local correction fixture, fictional materials and no website opener."""
import signal
import test_corrections
from server import make_server

if __name__=='__main__':
    case=test_corrections.CorrectionTests();case.setUp();case.failed_attempt()
    server=make_server(case.lab,browser_opener=lambda url:None)
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    print(f'http://127.0.0.1:{server.server_port}/#practice/{case.sid}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();case.tearDown()
