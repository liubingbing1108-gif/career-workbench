"""Disposable UI test server. Uses only fictional data and cannot refresh Feishu."""
import tempfile
from http.server import ThreadingHTTPServer
import feishu
from server import App, handler
from test_http import fixture

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='management-ui-disposable-') as directory:
        feishu.save_snapshot(fixture(),directory)
        app=App(directory,config='/nonexistent/fixture-no-live-feishu.json')
        server=ThreadingHTTPServer(('127.0.0.1',8771),handler(app))
        print('虚构数据验证: http://127.0.0.1:8771',flush=True)
        try:server.serve_forever()
        finally:server.server_close()
