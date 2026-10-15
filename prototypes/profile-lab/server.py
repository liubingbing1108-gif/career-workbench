from __future__ import annotations
import argparse
import importlib.util
import sys
from socketserver import TCPServer
import base64
import json
import mimetypes
import sqlite3
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from lab import candidate_pending, Lab, LabError, find
from recognizer import CodexRecognizer
from application import Application
from mapping import WebsiteMapper
from profile_groups import profile_groups
from form_analysis import save_analysis
from preparation import Preparation
from executor_bridge import ExecutorBridge
from site_scan import SiteScan
from job_sessions import JobSessions
from browser_launch import BrowserLaunch, open_chrome

ROOT = Path(__file__).resolve().parent


class LoopbackHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        # This service always binds literal loopback; reverse DNS is unnecessary
        # and can stall startup for tens of seconds on offline/macOS networks.
        TCPServer.server_bind(self)
        self.server_name = 'localhost'
        self.server_port = self.server_address[1]


def make_server(lab, port=0, mapper=None, management_app=None, management_handler=None, browser_opener=open_chrome):
    from profile_library import ProfileLibrary
    library = ProfileLibrary(lab)
    application = Application(lab, mapper)
    preparation = Preparation(lab, application)
    bridge = ExecutorBridge(lab, SiteScan(lab, preparation).accept)
    launcher = BrowserLaunch(lab,bridge,browser_opener)
    if management_app:
        from progress_query import ProgressQueries
        launcher.resolutions=management_app.resolutions
        launcher.progress_queries=ProgressQueries(management_app.store)
        def start_progress(jid,base):
            from store import Conflict
            try:return launcher.query_progress(jid,base)
            except LabError as error:raise Conflict(str(error))
        management_app.start_progress=start_progress
        management_app.progress_status=launcher.progress_queries.status
    job_sessions = JobSessions(lab, management_app.store, preparation) if management_app else None
    if job_sessions:
        management_app.delete_job = job_sessions.delete
        management_app.preparation_counts = job_sessions.counts
    class Handler(BaseHTTPRequestHandler):
        def management_request(self, method):
            if not self.path.startswith("/management/"):
                return False
            if management_handler is None:
                self.send(503, {"error": "管理服务尚未启动，请用统一启动入口"})
                return True
            original = self.path
            self.path = self.path[len("/management"):]
            try:
                management_handler.process(self, method)
            finally:
                self.path = original
            return True

        def do_PATCH(self):
            if not self.management_request("PATCH"):
                self.send(404, {"error": "接口不存在"})

        def do_DELETE(self):
            if not self.management_request("DELETE"):
                self.send(404, {"error": "接口不存在"})
        def local_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

        def log_message(self, format, *args):
            pass  # Do not log personal fields, file names or request bodies.

        def send(self, status, body, content_type="application/json; charset=utf-8", headers=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "frame-ancestors 'self'; object-src 'none'; base-uri 'self'")
            origin = self.headers.get('Origin')
            if self.path.startswith('/api/executor/') and bridge.allowed_origin(origin):
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.management_request("GET"):
                return
            if not self.local_host():
                return self.send(403, {'error': '仅接受本机地址'})
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/launch-relay":
                    return self.send(200,b'<meta charset="utf-8"><title>Connecting</title><p>Connecting to the filling extension. This temporary page closes automatically.</p>',"text/html; charset=utf-8")
                if parsed.path == "/api/health":
                    return self.send(200, {"ok": True, "product": "投递工作台", "management": management_app is not None})
                if parsed.path == "/api/preparation/current":
                    return self.send(200, preparation.current(parse_qs(parsed.query).get("session", [""])[0]))
                if parsed.path == "/api/preparation/bundle":
                    return self.send(200, preparation.bundle(parse_qs(parsed.query).get("session", [""])[0]))
                if parsed.path == "/api/state":
                    return self.send(200, lab.state())
                if parsed.path == "/api/profile/library":
                    return self.send(200, library.view())
                if parsed.path == "/api/profile-groups":
                    return self.send(200, profile_groups(lab.state()))
                if parsed.path == "/api/increments":
                    return self.send(200, lab.increments())
                if parsed.path == "/api/application":
                    return self.send(200, application.plan(parse_qs(parsed.query).get("session", [""])[0]))
                if parsed.path == "/api/preparation":
                    result = preparation.view(parse_qs(parsed.query).get("session", [""])[0])
                    session = next(s for s in lab.state()['sessions'] if s['id'] == parse_qs(parsed.query).get('session', [''])[0])
                    result['executor'] = bridge.status(session.get('website', {}).get('url') or session.get('target', {}).get('url'), session['id'])
                    return self.send(200, result)
                if parsed.path == '/api/executor-setup':
                    return self.send(200, bridge.setup(parse_qs(parsed.query).get('session', [None])[0]))
                if parsed.path == "/api/recognition":
                    return self.send(200, lab.recognition_status())
                if parsed.path == '/api/imports':
                    return self.send(200, [{**{k: p.get(k) for k in ('id', 'filename', 'status', 'stage', 'started_at', 'error', 'text_preview', 'converter', 'conversion_format')}, 'pending_count': sum(candidate_pending(c) for c in p['candidates'])} for p in lab.state()['imports']])
                if parsed.path == "/api/materials":
                    session_id = parse_qs(parsed.query).get("session", [""])[0]
                    return self.send(200, lab.materials(session_id))
                if parsed.path.startswith("/api/files/"):
                    file_id = parsed.path.rsplit("/", 1)[-1]
                    meta, raw = lab.file_bytes(file_id)
                    return self.send(200, raw, "application/octet-stream", {"Content-Disposition": "attachment; filename*=UTF-8''" + quote(meta["name"])})
                path = (ROOT / "web" / (parsed.path.lstrip("/") or "index.html")).resolve()
                if not path.is_relative_to(ROOT / "web") or not path.is_file():
                    return self.send(404, {"error": "页面不存在"})
                return self.send(200, path.read_bytes(), mimetypes.guess_type(path)[0] or "application/octet-stream")
            except LabError as error:
                self.send(error.status, {"error": str(error)})

        def do_OPTIONS(self):
            if not self.local_host():
                return self.send(403, {'error': '仅接受本机地址'})
            if not self.path.startswith('/api/executor/') or not bridge.allowed_origin(self.headers.get('Origin')):
                return self.send(403, {'error': '连接来源不允许'})
            return self.send(200, b'', headers={'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type'})

        def do_POST(self):
            if self.management_request("POST"):
                return
            if not self.local_host():
                return self.send(403, {'error': '仅接受本机地址'})
            try:
                # The standalone lab only accepts same-origin local UI requests.
                origin = self.headers.get("Origin")
                executor_request = self.path.startswith('/api/executor/')
                if origin and origin != "http://" + self.headers.get("Host", "") and not executor_request:
                    raise LabError("请求来源不匹配", 403)
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise LabError("需要 JSON 请求", 415)
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 12 * 1024 * 1024:
                    raise LabError("请求大小无效")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise LabError("请求格式无效")
                action = self.path
                if executor_request:
                    method=action.rsplit('/',1)[-1]
                    if method=='launch-claim':result=launcher.claim(data.get('ticket'),origin)
                    elif method=='launch-next':result=launcher.next(origin,data.get('connection'))
                    elif method=='launch-report':result=launcher.report(data.get('ticket'),origin,data.get('status'),data.get('message'))
                    elif method=='progress-report':result=launcher.progress_report(data.get('ticket'),origin,data.get('observation'))
                    elif method=='entry-report':result=launcher.inspected(data.get('ticket'),origin,data.get('observation'))
                    else:result = bridge.call(method, origin, data)
                elif action == '/api/browser-launch':
                    if job_sessions:job_sessions.validate_destination(data['session_id'])
                    result=launcher.request(data['session_id'],'http://'+self.headers['Host'],data.get('mode','prepare'),direct=data.get('direct') is True,rescan=data.get('rescan') is True,reconnect=data.get('reconnect') is True)
                elif action == '/api/entry-inspection':
                    result=launcher.inspect(data['job_id'],'http://'+self.headers['Host'],direct=data.get('direct') is True)
                elif action == "/api/form-analysis":
                    result = save_analysis(lab, data['analysis'], data.get('session_id'))
                elif action == "/api/preparation/open":
                    if job_sessions:
                        result = job_sessions.open(data)
                        if not data.get('job_id'):
                            threading.Thread(target=management_app.intake.enrich,args=(management_app.store,result['management_job_id']),daemon=True).start()
                    elif data.get('job_id'):
                        raise LabError('请从统一网站的管理岗位进入准备投递', 503)
                    else:
                        result = preparation.open_target(data["url"], data.get("title", ""),
                            requires_preference=bool(data.get("requires_preference")), source_id=data.get('source_id'))
                elif action == "/api/preparation/mapping":
                    with lab.lock:
                        session=find(lab.state()['sessions'],data['session_id'])
                        if session.get('preparation',{}).get('scan_status')=='matching':
                            raise LabError('资料仍在匹配，请等待本次匹配结束',409)
                        result = application.install_mapping(data['session_id'], data['manifest'], data['interpretation'])
                        lab.mutate(lambda state:find(state['sessions'],data['session_id']).setdefault('preparation',{}).update(scan_status='ready',scan_error=''))
                elif action == "/api/preparation/match":
                    result = preparation.match(data['session_id'])
                elif action == "/api/preparation/settings":
                    result = preparation.settings(data['session_id'], data['file_id'])
                elif action == "/api/preparation/defer":
                    result = preparation.defer(data['session_id'], data['key'], data['deferred'] is True)
                elif action == '/api/preparation/draft':
                    result = preparation.draft(data['session_id'], data['key'], data.get('value'), data.get('revision', 0))
                elif action == '/api/preparation/confirm-application':
                    if not job_sessions:raise LabError('管理服务尚未启动', 503)
                    result = job_sessions.confirm_application(data['session_id'], data.get('revision'), data.get('confirmed'))
                elif action == '/api/preparation/remove-optional':
                    result = preparation.remove_optional(data['session_id'], data['key'])
                elif action == '/api/preparation/omit-optional':
                    result = preparation.omit_optional(data['session_id'], data['key'], data.get('omitted') is True)
                elif action == "/api/preparation/preview":
                    result = preparation.preview(data['session_id'], data.get('official_draft') is True)
                elif action == "/api/preparation/start":
                    if job_sessions:job_sessions.validate_destination(data['session_id'])
                    if job_sessions:
                        session=find(lab.state()['sessions'],data['session_id'])
                        if session.get('management_job_id'):
                            job=management_app.store.get(session['management_job_id'])
                            if job.get('requires_preference'):raise LabError('该岗位需要选择志愿，请到官网人工申请')
                            if job.get('needs_review'):raise LabError('请在投递管理核对公司和具体岗位后开始填写')
                            if job.get('official_url_status')!='verified':raise LabError('官网入口尚未核验，招聘信息链接不能用于填写')
                    result = preparation.start(data['session_id'], data['digest'], data.get('official_draft') is True, retry=data.get('retry') is True)
                elif action == '/api/preparation/verify':
                    if job_sessions:job_sessions.validate_destination(data['session_id'])
                    result=preparation.verify(data['session_id'],data.get('after_reopen') is True)
                elif action == "/api/preparation/pause":
                    result = preparation.pause(data['session_id'])
                elif action == "/api/import":
                    result = lab.upload(data["filename"], base64.b64decode(data["base64"], validate=True), asynchronous=data.get('async') is True)
                elif action == "/api/import/retry":
                    result = lab.start_import(data['import_id']) if data.get('async') is True else lab.recognize_import(data["import_id"])
                elif action == "/api/import/commit":
                    result = lab.commit_import(data["import_id"], data["accepted"], data.get("edits", {}), data.get("expected_revision"))
                elif action == "/api/import/identity":
                    result = library.import_identity(data)
                elif action == "/api/import/resolve":
                    result = lab.resolve_import(data["decisions"], data.get("revisions", {}))
                elif action == "/api/default-version":
                    result = lab.set_default(data["entry_id"], data["field_id"], data["version_id"])
                elif action == "/api/website/scan":
                    result = application.scan(data["session_id"], data["manifest"])
                elif action == "/api/website/choices":
                    result = application.select_entries(data["session_id"], data["category"], data["entry_ids"], data.get("group_id"))
                elif action == "/api/website/entry":
                    result = application.add_entry(data["session_id"], data["website_id"])
                elif action == "/api/website/material-control":
                    from material_sets import MaterialSets
                    result = MaterialSets(application).control(data['session_id'], data['website_id'], data['action'], data.get('entry_id'), data.get('version_id'), data.get('included'))
                elif action == "/api/website/set-version":
                    from material_sets import MaterialSets
                    result = MaterialSets(application).select(data['session_id'], data['website_id'], data['entry_id'], data['version_id'])
                elif action == "/api/website/set-answer":
                    from material_sets import MaterialSets
                    result = MaterialSets(application).save(data['session_id'], data['website_id'], data['records'], data.get('mode', 'session'), data.get('name', ''), data.get('composition', False))
                elif action == "/api/website/composition-version":
                    from material_sets import MaterialSets
                    result = MaterialSets(application).select_composition(data['session_id'], data['website_id'], data['version_id'])
                elif action == "/api/website/version":
                    result = application.select_version(data["session_id"], data["website_id"], data["version_id"], data.get("entry_id"), data.get("field_id"), data.get("child_id"))
                elif action == "/api/website/answer":
                    result = application.edit_answer(data["session_id"], data["website_id"], data["value"], data["mode"], data.get("version_id"), data.get("expected_revision"), data.get("name", ""), data.get("entry_id"), data.get("field_id"), data.get("child_id"))
                elif action == "/api/fields":
                    result = lab.add_field(data)
                elif action == "/api/entries":
                    result = lab.mutate(lambda state: lab.new_entry(state, data["category"]))
                elif action == "/api/profile/tree":
                    result = library.tree(data)
                elif action == "/api/profile/record":
                    result = library.save(data)
                elif action == "/api/profile/draft":
                    result = library.draft(data)
                elif action == "/api/profile/archive":
                    result = library.archive(data)
                elif action == "/api/profile/field-version":
                    result = library.field_version(data)
                elif action == "/api/profile/version":
                    result = library.version(data)
                elif action == "/api/profile/record-default":
                    result = library.default(data)
                elif action == "/api/profile/attachment":
                    result = library.attachment(data)
                elif action == "/api/profile/attachment-upload":
                    result = library.upload_attachment(data["filename"],base64.b64decode(data["base64"],validate=True))
                elif action == "/api/profile":
                    result = lab.save_profile(data["values"])
                elif action == "/api/sessions":
                    result = lab.new_session(data.get("name", "新投递演练"))
                elif action == "/api/answer":
                    result = lab.answer(data["session_id"], data["field_id"], data["value"], data.get("save_to_profile", False))
                elif action == "/api/versions":
                    result = lab.edit_version(data["session_id"], data["version_id"], data["mode"], data["content"], data.get("expected_revision"), data.get("name", ""))
                elif action == "/api/versions/create":
                    result = lab.create_version(data["entry_id"], data["field_id"], data["content"], data.get("name", "手填描述"))
                elif action == "/api/select-version":
                    result = lab.select_version(data["session_id"], data["version_id"])
                else:
                    raise LabError("接口不存在", 404)
                self.send(200, result)
            except LabError as error:
                self.send(error.status, {"error": str(error)})
            except (KeyError, ValueError, TypeError):
                self.send(400, {"error": "请求字段或编码无效"})

    return LoopbackHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--data-dir")
    parser.add_argument("--management-data-dir")
    parser.add_argument("--sample-parser", action="store_true", help="仅用于离线虚构样例回归测试")
    parser.add_argument("--restore-from", help="从旧原型的 SQLite 备份恢复本次临时会话")
    args = parser.parse_args()
    temporary = None if args.data_dir else tempfile.TemporaryDirectory(prefix="profile-lab-")
    if args.restore_from:
        destination = Path(args.data_dir or temporary.name) / "lab.sqlite"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            parser.error("恢复目标已存在，拒绝覆盖")
        with sqlite3.connect(f"file:{Path(args.restore_from).resolve()}?mode=ro", uri=True) as source, sqlite3.connect(destination) as target:
            source.backup(target)
    lab = Lab(args.data_dir or temporary.name, None if args.sample_parser else CodexRecognizer())
    management_app = management_handler = None
    if args.management_data_dir:
        module_dir = ROOT.parent / "management-lab"
        sys.path.insert(0, str(module_dir))
        spec = importlib.util.spec_from_file_location("workbench_management", module_dir / "server.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        management_app = module.App(args.management_data_dir)
        management_handler = module.handler(management_app)
    server = make_server(lab, args.port, WebsiteMapper(), management_app, management_handler)
    print(f"底稿验证页：http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        lab.db.close()
        if temporary:
            temporary.cleanup()
