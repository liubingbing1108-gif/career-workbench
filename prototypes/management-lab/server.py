from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import feishu
from store import Store, STAGES, Invalid, Conflict, Missing
from intake import JobIntake
from official import OfficialLookup
from resolution import ResolutionTasks

STATIC = Path(__file__).parent / "web"


class App:
    def __init__(self, data_dir, config=feishu.DEFAULT_CONFIG):
        self.store = Store(data_dir)
        self.config = config
        self.token = secrets.token_urlsafe(32)
        self.delete_job = self.store.delete
        self.preparation_counts = lambda: {}
        self.intake = JobIntake()
        self.official = OfficialLookup(known_entries=lambda:[j['official_entry'] for j in self.store.list_jobs() if j.get('official_url_status')=='verified' and j.get('official_entry')])
        self.resolutions = ResolutionTasks(self.store,lambda:self.official)

    def jobs(self):
        counts = self.preparation_counts()
        return [self.enrich(job, counts) for job in self.store.list_jobs()]

    def enrich(self, job, counts=None):
        extra = (self.preparation_counts() if counts is None else counts).get(job['id'], {})
        return {**job, 'preparation_count': extra.get('preparation_count', 0),
                'execution_count': job['execution_count'] + extra.get('execution_count', 0)}



def handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, payload, mime="application/json; charset=utf-8"):
            raw = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def process(self, method):
            try:
                host = self.headers.get("Host", "")
                expected = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
                if host not in expected:
                    return self.send(403, {"error": "仅允许本机界面访问"})
                body = {}
                if method != "GET":
                    origin = self.headers.get("Origin")
                    if origin and origin not in {"http://" + h for h in expected}:
                        return self.send(403, {"error": "请求来源不符"})
                    if not secrets.compare_digest(self.headers.get("X-Management-Token", ""), app.token):
                        return self.send(403, {"error": "本机连接已改变，请刷新页面"})
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= size <= 1_000_000:
                        return self.send(413, {"error": "请求内容过大"})
                    body = json.loads(self.rfile.read(size) or b"{}")
                    if not isinstance(body, dict):
                        raise Invalid("请求内容无效")
                path = urlsplit(self.path).path
                # Also works when the unified host strips this prefix before dispatch.
                if path == "/management":
                    self.send_response(302)
                    self.send_header("Location", "/management/" + ("?" + urlsplit(self.path).query if urlsplit(self.path).query else ""))
                    self.end_headers()
                    return
                if path.startswith("/management/"):
                    path = path[len("/management"):]
                if method == "GET" and path == "/api/bootstrap":
                    return self.send(200, {"token": app.token, "stages": STAGES, "jobs": app.jobs(),
                                           "remote_write_enabled": False, "official_query_enabled": False})
                if method == "GET" and path == "/api/jobs":
                    return self.send(200, {"jobs": app.jobs()})
                if method == "POST" and path == "/api/preview/text":
                    return self.send(200, app.store.save_preview(app.intake.preview(body.get("text"))))
                if method == 'POST' and path == '/api/jobs/from-link':
                    return self.send(200, app.store.create_link(body.get('url'),body.get('request_id')))
                if method == "POST" and path == "/api/preview/split":
                    if body.get("batch_id"):
                        rows = app.store.preview(body["batch_id"])
                    else:
                        raise Invalid('请先生成录入预览')
                    original = next((r for r in rows if r["id"] == body.get("candidate_id")), None)
                    if not original:
                        raise Missing("原候选不存在")
                    roles = body.get("roles")
                    if not isinstance(roles, list) or not 1 <= len(roles) <= 100 or any(not isinstance(r, str) or not r.strip() for r in roles):
                        raise Invalid("请每行填写一个具体岗位名称")
                    split = [{**original, "id": secrets.token_hex(16), "role": role.strip(), "role_summary": False,
                              "recruitment_stage": "", "mapping_notes": original.get("mapping_notes", []) + ["用户核对拆分；旧汇总招聘进度未分配"]} for role in roles]
                    preview = app.store.save_preview(split)
                    preview["label"] = "拆分岗位预览"
                    return self.send(200, preview)
                if method == "POST" and path == "/api/import":
                    if body.get("source") == "text":
                        rows = app.store.preview(body.get("batch_id"))
                    else:
                        raise Invalid("请先生成候选预览")
                    return self.send(200, app.store.import_selected(rows, body.get("selections"), body.get("request_id"), body))
                parts = path.split("/")
                if len(parts) >= 4 and parts[1:3] == ["api", "jobs"]:
                    jid = parts[3]
                    if method == "GET" and len(parts) == 4:
                        return self.send(200, app.enrich(app.store.get(jid)))
                    if method == "PATCH" and len(parts) == 4:
                        return self.send(200, app.store.update(jid, body.get("revision"), body.get("patch", {}), body.get("timeline")))
                    if method == "DELETE" and len(parts) == 4:
                        return self.send(200, app.delete_job(jid, body.get("revision"), body.get("confirmed")))
                    if method == "POST" and len(parts) == 5 and parts[4] == "query":
                        app.store.get(jid)
                        # No browser connection exists yet. Never fabricate a query result.
                        return self.send(200, {"status": "unavailable", "changed": False, "message": "官网进度查询尚未接通，已保留原招聘进度。请打开官网查看后人工记录。"})
                    if method=='POST' and len(parts)==5 and parts[4]=='resolution-choice':
                        return self.send(200,app.resolutions.choose(jid,body.get('url'),body.get('confirm_role') is True))
                    if method in ('GET','POST') and len(parts)==5 and parts[4]=='resolution':
                        return self.send(200,app.resolutions.status(jid,start=method=='POST',retry=body.get('retry') is True))
                    if method == 'POST' and len(parts)==5 and parts[4]=='source-analysis':
                        return self.send(200,app.official.source_summary(app.store.get(jid)))
                    if method == 'POST' and len(parts)==5 and parts[4]=='resolve':
                        job=app.store.get(jid)
                        result=app.official.lookup(job)
                        if result['status']=='ready':
                            result['job']=job if job.get('official_url_status')=='verified' and job.get('official_url')==result['entry']['url'] else app.store.set_official(jid,job['revision'],result['entry'])
                        return self.send(200,result)
                    if method == 'POST' and len(parts)==5 and parts[4]=='official':
                        return self.send(200,app.store.set_official(jid,body.get('revision'),body.get('entry')))
                if method == "GET" and not path.startswith("/api/"):
                    filename = {"/": "index.html", "/app.js": "app.js", "/integration.js": "integration.js", "/style.css": "style.css"}.get(path)
                    if filename:
                        mime = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "integration.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8"}[filename]
                        return self.send(200, (STATIC / filename).read_bytes(), mime)
                self.send(404, {"error": "入口不存在"})
            except Invalid as exc:
                self.send(400, {"error": str(exc)})
            except Conflict as exc:
                self.send(409, {"error": str(exc)})
            except Missing as exc:
                self.send(404, {"error": str(exc)})
            except feishu.FeishuError as exc:
                self.send(502, {"error": str(exc)})
            except (ValueError, TypeError, KeyError):
                self.send(400, {"error": "请求格式无效"})
            except Exception:
                self.send(500, {"error": "本次操作未完成，请重试"})

        def do_GET(self): self.process("GET")
        def do_POST(self): self.process("POST")
        def do_PATCH(self): self.process("PATCH")
        def do_DELETE(self): self.process("DELETE")
    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--feishu-config", default=str(feishu.DEFAULT_CONFIG))
    args = parser.parse_args()
    app = App(args.data_dir, args.feishu_config)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(app))
    print(f"投递管理: http://127.0.0.1:{args.port}  数据目录: {args.data_dir}", flush=True)
    server.serve_forever()
