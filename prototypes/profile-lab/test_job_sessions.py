"""Fictional jobs only: ownership, deletion and late browser/model responses."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from lab import Lab, LabError
from application import Application
from preparation import Preparation
from executor_bridge import ExecutorBridge
from site_scan import SiteScan
from server import make_server
from job_sessions import JobSessions
from test_unified import snapshot

mdir = Path(__file__).resolve().parents[1] / 'management-lab'
sys.path.insert(0, str(mdir))
spec = importlib.util.spec_from_file_location('job_ownership_management', mdir / 'server.py')
management = importlib.util.module_from_spec(spec)
spec.loader.exec_module(management)
from store import Conflict, Invalid


class JobSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lab = Lab(Path(self.tmp.name) / 'profile')
        self.app = management.App(Path(self.tmp.name) / 'management')
        self.prep = Preparation(self.lab, Application(self.lab))
        self.jobs = JobSessions(self.lab, self.app.store, self.prep)
        preview = self.app.store.preview_text('虚构公司 | 岗位甲 | https://example.com/apply\n虚构公司 | 岗位乙 | https://example.com/apply')
        for row in preview['candidates']:
            row.update(official_url_status='verified',official_entry={'url':row['url'],'verification':'fictional_fixture'})
        ids = self.app.store.import_selected(preview['candidates'], [{'id': '0'}, {'id': '1'}], 'fictional-request', {})['ids']
        self.a, self.b = ids
        self.sa = self.jobs.open({'job_id': self.a})
        self.sb = self.jobs.open({'job_id': self.b})
        self.origin = 'chrome-extension://' + 'a' * 32
        self.url = 'https://example.com/apply'

    def tearDown(self):
        self.lab.db.close()
        self.tmp.cleanup()

    def connect(self, bridge, sid):
        code = bridge.setup(sid)['code']
        token = bridge.call('connect', self.origin, {'code': code, 'url': self.url})['connection']
        return {'connection': token, 'url': self.url}

    def queued(self, sid, job_id):
        self.lab.mutate(lambda s: next(x for x in s['sessions'] if x['id'] == sid)['preparation'].update(
            execution={'id': job_id, 'status': 'awaiting_executor', 'confirmed_materials': {'url': self.url, 'rows': []}}))

    def test_job_source_and_direct_link_are_distinct_and_reopening_preserves_choices(self):
        self.lab.mutate(lambda s: s['sessions'][0]['overrides'].update(answer='甲本次答案'))
        reopened = self.jobs.open({'job_id': self.a, 'url': 'https://evil.example', 'title': '过期标题'})
        direct = self.prep.open_target(self.url)
        source = self.prep.open_target(self.url, source_id='applications:fixture')
        other_source = self.prep.open_target(self.url, source_id='opportunities:fixture')
        self.assertEqual(reopened['id'], self.sa['id'])
        self.assertEqual(reopened['name'], '岗位甲')
        self.assertEqual(reopened['overrides']['answer'], '甲本次答案')
        self.assertEqual(len({x['id'] for x in [reopened, self.sb, direct, source, other_source]}), 5)
        self.assertNotIn('management_job_id', source)
        self.assertEqual(self.prep.open_target(self.url)['id'], direct['id'])
        with self.assertRaises(LabError):
            self.prep.open_target(self.url, job_id=self.a, source_id='invalid-combined-scope')

    def test_connection_scan_and_poll_only_target_the_chosen_job(self):
        received = []
        bridge = ExecutorBridge(self.lab, lambda url, scan, sid: received.append(sid))
        base = self.connect(bridge, self.sb['id'])
        bridge.call('scan', self.origin, {**base, 'snapshot': snapshot()})
        self.assertEqual(received, [self.sb['id']])
        self.assertFalse(bridge.status(self.url, self.sa['id'])['connected'])
        self.assertTrue(bridge.status(self.url, self.sb['id'])['connected'])
        self.queued(self.sa['id'], 'fill-a')
        self.assertIsNone(bridge.call('poll', self.origin, base)['job'])
        self.queued(self.sb['id'], 'fill-b')
        self.assertEqual(bridge.call('poll', self.origin, base)['job']['id'], 'fill-b')
        with self.assertRaises(LabError):
            bridge.call('report', self.origin, {**base, 'job_id': 'fill-a', 'status': 'complete', 'filled': 1, 'verified': 1, 'message': 'wrong job'})

    def test_observed_application_url_keeps_public_role_and_rejects_other_role_or_site(self):
        preview=self.app.store.preview_text('虚构公司 | 岗位丙 | https://example.com/detail?jobAdId=fictional-role')
        row=preview['candidates'][0]
        row.update(official_url_status='verified',official_entry={'verification':'browser'})
        jid=self.app.store.import_selected([row],[{'id':'0'}],'fictional-browser-form',{})['ids'][0]
        good='https://example.com/form?jobAdId=fictional-role&userId=fictional-user'
        s=self.jobs.open({'job_id':jid,'application_url':good})
        self.assertEqual(s['target']['url'],good)
        self.assertEqual(self.app.store.get(jid)['url'],row['url'])
        for bad in ['https://other.example/form?jobAdId=fictional-role','https://example.com/form?jobAdId=other-role','https://example.com/login?jobAdId=fictional-role']:
            with self.assertRaises(LabError):self.jobs.open({'job_id':jid,'application_url':bad})

    def test_unscoped_connection_and_scan_refuse_ambiguous_url(self):
        bridge = ExecutorBridge(self.lab)
        with self.assertRaisesRegex(LabError, '多个岗位'):
            bridge.call('connect', self.origin, {'code': bridge.code, 'url': self.url})
        with self.assertRaisesRegex(LabError, '不能按链接'):
            SiteScan(self.lab, self.prep).accept(self.url, snapshot())

    def test_busy_url_refuses_reconnection_to_another_job(self):
        bridge = ExecutorBridge(self.lab)
        base = self.connect(bridge, self.sa['id'])
        self.queued(self.sa['id'], 'fill-a')
        bridge.call('poll', self.origin, base)
        with self.assertRaisesRegex(LabError, '先暂停'):
            self.connect(bridge, self.sb['id'])

    def test_delete_removes_only_bound_sessions_and_rejects_stale_open(self):
        raw = self.lab.upload('fictional.txt', b'fictional disposable file')
        source = self.prep.open_target(self.url, source_id='opportunities:fixture')
        self.queued(self.sa['id'], 'fill-a')
        before = self.lab.state()
        result = self.jobs.delete(self.a, 1, True)
        after = self.lab.state()
        self.assertEqual(result['preparations_deleted'], 1)
        self.assertEqual({k: v for k, v in before.items() if k != 'sessions'}, {k: v for k, v in after.items() if k != 'sessions'})
        self.assertEqual([s['id'] for s in after['sessions']], [self.sb['id'], source['id']])
        self.assertEqual(self.lab.file_bytes(raw['file_id'])[1], b'fictional disposable file')
        self.assertEqual(self.app.store.get(self.b)['role'], '岗位乙')
        with self.assertRaises(LabError) as error:
            self.jobs.open({'job_id': self.a})
        self.assertEqual(error.exception.status, 404)
        self.assertEqual(after, self.lab.state())

    def test_delete_requires_confirmation_and_current_revision(self):
        before = self.lab.state()
        for revision, confirmed, kind in [(1, False, Invalid), (2, True, Conflict)]:
            with self.assertRaises(kind):
                self.jobs.delete(self.a, revision, confirmed)
            self.assertEqual(before, self.lab.state())
            self.assertEqual(self.app.store.get(self.a)['revision'], 1)

    def test_cross_database_failure_rolls_back_preparations_and_job(self):
        before = self.lab.state()
        with self.app.store.connect() as db:
            db.execute("CREATE TRIGGER refuse_fixture_delete BEFORE DELETE ON jobs BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        with self.assertRaises(Exception):
            self.jobs.delete(self.a, 1, True)
        self.assertEqual(before, self.lab.state())
        self.assertEqual(self.app.store.get(self.a)['revision'], 1)

    def test_wal_mode_refuses_cross_database_delete_without_changing_records(self):
        for target in ('profile', 'management'):
            with self.subTest(target=target):
                db = self.lab.db if target == 'profile' else self.app.store.connect()
                try:
                    db.execute('PRAGMA journal_mode=WAL')
                    before = self.lab.state()
                    with self.assertRaisesRegex(LabError, '事务模式'):
                        self.jobs.delete(self.a, 1, True)
                    self.assertEqual(before, self.lab.state())
                    self.assertEqual(self.app.store.get(self.a)['revision'], 1)
                finally:
                    if target == 'profile':
                        db.execute('PRAGMA journal_mode=DELETE')
                    else:
                        db.close()

    def test_late_executor_reports_and_scans_stop_without_recreating_deleted_job(self):
        bridge = ExecutorBridge(self.lab)
        base = self.connect(bridge, self.sa['id'])
        self.queued(self.sa['id'], 'fill-a')
        bridge.call('poll', self.origin, base)
        self.jobs.delete(self.a, 1, True)
        before = self.lab.state()
        self.assertTrue(bridge.call('poll', self.origin, base)['stop'])
        report = bridge.call('report', self.origin, {**base, 'job_id': 'fill-a', 'status': 'complete', 'filled': 99})
        self.assertFalse(report['accepted']); self.assertTrue(report['stop'])
        with self.assertRaises(LabError):
            bridge.call('scan', self.origin, {**base, 'snapshot': snapshot()})
        self.assertEqual(before, self.lab.state())

    def test_delayed_model_result_does_not_recreate_deleted_preparation(self):
        entered, released = threading.Event(), threading.Event()
        class Mapper:
            def map(self, fields, profile):
                entered.set(); released.wait(3)
                return {'mappings': [{'website_id': 'education', 'status': 'mapped', 'category': 'education',
                    'field_id': None, 'members': [{'website_id': 'education[].school', 'field_id': 'school'}]}]}
        scan = SiteScan(self.lab, Preparation(self.lab, Application(self.lab, Mapper())))
        scan.accept(self.url, snapshot(), self.sa['id'])
        self.assertTrue(entered.wait(3))
        self.jobs.delete(self.a, 1, True)
        before = self.lab.state()
        released.set()
        for thread in scan.threads:
            thread.join(3); self.assertFalse(thread.is_alive())
        self.assertEqual(before, self.lab.state())

    def test_direct_link_default_import_is_idempotent_and_invalid_link_has_no_side_effect(self):
        before=self.lab.state();jobs=self.app.store.list_jobs()
        for url in ['http://example.com','https://user:secret@example.com','javascript:alert(1)']:
            with self.assertRaises(LabError):self.jobs.open({'url':url,'request_id':'fixture-invalid-link'})
        self.assertEqual(before,self.lab.state());self.assertEqual(jobs,self.app.store.list_jobs())
        data={'url':self.url,'request_id':'fixture-direct-default-save'}
        session=self.jobs.open(data);again=self.jobs.open(data)
        self.assertEqual(session['id'],again['id']);self.assertEqual(len(self.app.store.list_jobs()),3)
        self.assertTrue(self.app.store.get(session['management_job_id'])['needs_review'])
        self.assertNotIn('execution',session['preparation'])

    def test_http_launch_uses_saved_job_and_does_not_fill(self):
        from urllib.parse import urlsplit,parse_qs
        opened=[];self.app.intake.enrich=lambda *args:None
        server=make_server(self.lab,management_app=self.app,management_handler=management.handler(self.app),browser_opener=opened.append)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
        def post(path,body,origin=base):
            return json.load(urlopen(Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':origin})))
        try:
            session=post('/api/preparation/open',{'url':'https://example.com/new-job','request_id':'fictional-http-link-request'})
            self.assertEqual(self.app.store.get(session['management_job_id'])['url'],'https://example.com/new-job')
            with self.assertRaises(HTTPError) as unresolved:
                post('/api/browser-launch',{'session_id':session['id']})
            self.assertEqual(unresolved.exception.code,400);self.assertEqual(opened,[])
            job=self.app.store.get(session['management_job_id'])
            job=self.app.store.update(job['id'],job['revision'],{'company':'虚构公司','role':'示例岗位'},None)
            target='https://example.com/new-job'
            self.app.store.set_official(job['id'],job['revision'],{'company':job['company'],'role':job['role'],'url':target,'company_url':'https://example.com/','recruitment_url':target,'verification':'browser','evidence':[{'url':target,'quote':'示例岗位'}]})
            post('/api/browser-launch',{'session_id':session['id']});self.assertEqual(len(opened),1)
            ticket=parse_qs(urlsplit(opened[0]).query)['launch'][0]
            claim=post('/api/executor/launch-claim',{'ticket':ticket},self.origin)
            self.assertEqual(claim['session_id'],session['id']);self.assertEqual(claim['url'],'https://example.com/new-job')
            with self.assertRaises(HTTPError) as blocked:
                post('/api/preparation/start',{'session_id':session['id'],'digest':'unconfirmed'})
            self.assertEqual(blocked.exception.code,400)
            self.assertFalse(any(s.get('preparation',{}).get('execution') for s in self.lab.state()['sessions']))
        finally:server.shutdown();server.server_close();thread.join()

    def test_http_delete_counts_and_missing_job_are_consistent(self):
        server = make_server(self.lab, management_app=self.app, management_handler=management.handler(self.app))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            self.queued(self.sa['id'], 'fill-a')
            bootstrap = json.load(urlopen(base + '/management/api/bootstrap'))
            job = next(j for j in bootstrap['jobs'] if j['id'] == self.a)
            self.assertEqual((job['preparation_count'], job['execution_count']), (1, 1))
            headers = {'Content-Type': 'application/json', 'X-Management-Token': bootstrap['token'], 'Origin': base}
            body = json.dumps({'revision': 1, 'confirmed': True}).encode()
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + '/management/api/jobs/' + self.a, data=body, headers={**headers, 'X-Management-Token': 'invalid'}, method='DELETE'))
            self.assertEqual(error.exception.code, 403)
            self.assertEqual(len(self.lab.state()['sessions']), 2)
            result = json.load(urlopen(Request(base + '/management/api/jobs/' + self.a, data=body, headers=headers, method='DELETE')))
            self.assertEqual(result['preparations_deleted'], 1)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + '/api/preparation/open', data=json.dumps({'job_id': self.a}).encode(), headers=headers))
            self.assertEqual(error.exception.code, 404)
            self.assertEqual(len(self.lab.state()['sessions']), 1)
        finally:
            server.shutdown(); server.server_close(); thread.join()
